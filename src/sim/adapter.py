"""Single boundary into the sim layer: `run_rollout(config) -> RolloutResult`.

The orchestrator (and Plan-B callable agents, if access is granted) only ever
talk to this function. It owns env construction, policy construction, the step
loop, video encoding, and result packaging. It NEVER returns dicts — only
schemas — so swapping the underlying sim (cf. CLAUDE.md sec 12 pivot) is a
local change here.

Both pretrained (robomimic BC-RNN on Lift) and scripted (state machine on Lift)
cases route through one code path; the only difference is which Policy and
which env_kwargs are built. Deployment rollouts on the pretrained policy may
widen the cube xy placement range via config.cube_xy_jitter_m — that's the
single-axis stress lever that makes the BC-RNN fail under perturbed initial
conditions (see docs/eval_methodology.md).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from src.constants import MUJOCO_GL_ENV_KEY

# MUJOCO_GL must be set BEFORE robosuite/mujoco import. Callers running through
# this adapter therefore do not need to set it themselves.
os.environ.setdefault(MUJOCO_GL_ENV_KEY, "glfw")

import imageio  # noqa: E402
import numpy as np  # noqa: E402
import robosuite as suite  # noqa: E402
from robosuite.controllers import load_controller_config  # noqa: E402

from src.schemas import RolloutConfig, RolloutResult, RolloutTelemetry, TelemetryRow  # noqa: E402
from src.sim.policies import Policy  # noqa: E402
from src.sim.pretrained import RobomimicPolicy  # noqa: E402
from src.sim.scripted import ScriptedLiftPolicy  # noqa: E402

# After success triggers, keep stepping for ~1 s so we can re-verify the cube
# is still aloft at the end of the hold — this is what demotes failed_grip
# rollouts (cube rises above the success threshold mid-slip, then falls back)
# from false-success to failure. Also gives the recorded video clean "cube held
# aloft" final frames on clean successes.
POST_SUCCESS_HOLD_STEPS = 20

# Sum of the two Panda finger joint qpos values when fully open. Used to
# normalize gripper aperture to [0, 1] for the judge's telemetry table.
# Each finger ranges roughly [0, 0.04]; sum tops out near 0.08 m.
PANDA_GRIPPER_FULL_OPEN_M = 0.08

# If the cube's final z is within this margin of its initial z, it clearly
# fell back to the table — the failed_grip signature. A held cube sits
# ~20 cm above its initial z (LIFT_HEIGHT_M in scripted.py); a successful
# BC-RNN rollout likewise keeps the cube well above this margin. 3 cm is
# conservative enough that physics jitter around a legitimately-held cube
# never trips it.
CUBE_FELL_BACK_MARGIN_M = 0.03


def _build_pretrained(config: RolloutConfig) -> tuple[Policy, dict[str, Any], str]:
    assert config.checkpoint_path is not None  # invariant from RolloutConfig
    policy = RobomimicPolicy(config.checkpoint_path)
    env_kwargs = policy.env_kwargs_for_robosuite()
    env_kwargs["has_offscreen_renderer"] = True
    env_kwargs["camera_names"] = config.render.camera
    env_kwargs["camera_heights"] = config.render.height
    env_kwargs["camera_widths"] = config.render.width
    return policy, env_kwargs, policy.env_name


def _build_scripted(config: RolloutConfig) -> tuple[Policy, dict[str, Any], str]:
    assert config.injected_failures is not None  # invariant from RolloutConfig
    policy = ScriptedLiftPolicy(config.injected_failures, seed=config.seed)
    controller_cfg = load_controller_config(default_controller="OSC_POSE")
    env_kwargs: dict[str, Any] = {
        "robots": "Panda",
        "controller_configs": controller_cfg,
        "has_renderer": False,
        "has_offscreen_renderer": True,
        "use_camera_obs": False,
        "control_freq": 20,
        "horizon": config.max_steps,
        "camera_names": config.render.camera,
        "camera_heights": config.render.height,
        "camera_widths": config.render.width,
    }
    return policy, env_kwargs, config.env_name


def _apply_cube_xy_jitter(env: Any, jitter_m: float) -> None:
    """Widen Lift's UniformRandomSampler xy bounds in-place before the first reset.

    The sampler is built inside robosuite's Lift._load_model() as an attribute
    on the env (env.placement_initializer) with default x_range=y_range=(-0.03, 0.03).
    We overwrite the ranges before env.reset() samples the cube — the sampler
    re-reads x_range/y_range on every sample() call, so mutation is sufficient.
    See robosuite/environments/manipulation/lift.py:325 for the default.
    """
    sampler = env.placement_initializer
    sampler.x_range = (-jitter_m, jitter_m)
    sampler.y_range = (-jitter_m, jitter_m)


def _extract_telemetry_row(
    env: Any,
    obs: dict[str, Any],
    step_index: int,
    initial_cube_pos: np.ndarray[Any, Any],
) -> TelemetryRow:
    """Pull the five disambiguating scalars for one step from the env + obs.

    Aligned 1:1 with the rendered frame for the same step — the judge slices
    rows by sampled-frame index and the lookup is identity (frame i ↔ step i).
    """
    cube = np.asarray(obs["cube_pos"], dtype=np.float64)
    eef = np.asarray(obs["robot0_eef_pos"], dtype=np.float64)
    grip = np.asarray(obs["robot0_gripper_qpos"], dtype=np.float64)

    aperture = float(np.clip(grip.sum() / PANDA_GRIPPER_FULL_OPEN_M, 0.0, 1.0))
    ee_to_cube = float(np.linalg.norm(eef - cube))
    cube_z_above = float(cube[2] - initial_cube_pos[2])
    cube_xy_drift = float(np.linalg.norm(cube[:2] - initial_cube_pos[:2]))
    contact = bool(env.check_contact(env.robots[0].gripper, env.cube))

    return TelemetryRow(
        step_index=step_index,
        gripper_aperture=aperture,
        ee_to_cube_m=ee_to_cube,
        cube_z_above_table_m=cube_z_above,
        cube_xy_drift_m=cube_xy_drift,
        contact_flag=contact,
    )


def _telemetry_path_for(video_out: Path) -> Path:
    """Sidecar path next to the mp4: <id>.mp4 → <id>.telemetry.json."""
    return video_out.with_suffix(".telemetry.json")


def run_rollout(config: RolloutConfig, video_out: Path | None = None) -> RolloutResult:
    """Run one scenario end-to-end and return its result.

    If `video_out` is provided, an mp4 of the configured camera is written there
    along with a `<id>.telemetry.json` sidecar of per-step sim telemetry. Pass
    None to skip both (useful for parallel sweeps where only the success/label
    outcome matters).
    """
    if config.policy_kind == "pretrained":
        policy, env_kwargs, env_name = _build_pretrained(config)
    else:
        policy, env_kwargs, env_name = _build_scripted(config)

    env = suite.make(env_name=env_name, **env_kwargs)
    if config.cube_xy_jitter_m > 0.0:
        _apply_cube_xy_jitter(env, config.cube_xy_jitter_m)

    obs = env.reset()
    policy.reset()
    render_camera = config.render.camera
    initial_cube_pos = np.asarray(obs["cube_pos"], dtype=np.float64).copy()

    record_video = video_out is not None
    frames: list[np.ndarray[Any, Any]] = []
    telemetry_rows: list[TelemetryRow] = []
    success = False
    steps = 0
    hold_remaining = 0
    for step in range(1, config.max_steps + 1):
        action = policy.act(obs)
        obs, _reward, _done, _info = env.step(action)

        if record_video:
            frame = env.sim.render(
                camera_name=render_camera,
                width=config.render.width,
                height=config.render.height,
            )
            frames.append(frame[::-1])
            telemetry_rows.append(_extract_telemetry_row(env, obs, step - 1, initial_cube_pos))

        steps = step
        if not success:
            if env._check_success():
                success = True
                hold_remaining = POST_SUCCESS_HOLD_STEPS
        else:
            hold_remaining -= 1
            if hold_remaining <= 0:
                break

    # Demote transient success only when the cube has clearly returned to the
    # table — the failed_grip signature. A stricter `env._check_success()`
    # re-check here over-penalizes BC-RNN rollouts whose held cube briefly
    # dips below the success threshold while the policy continues issuing
    # actions post-success (the policy wasn't trained on post-success
    # behavior). Anchoring to the cube's initial z, not the success
    # threshold, cleanly separates "dropped back to the table" from "still
    # held, jiggling".
    if success:
        current_cube_z = float(np.asarray(obs["cube_pos"], dtype=np.float64)[2])
        cube_dropped_back_to_table = current_cube_z - initial_cube_pos[2] < CUBE_FELL_BACK_MARGIN_M
        if cube_dropped_back_to_table:
            success = False

    telemetry_out: Path | None = None
    if record_video and video_out is not None and frames:
        video_out.parent.mkdir(parents=True, exist_ok=True)
        imageio.mimsave(video_out, list(frames), fps=config.render.fps)
        telemetry_out = _telemetry_path_for(video_out)
        telemetry = RolloutTelemetry(
            rollout_id=config.rollout_id,
            fps=config.render.fps,
            rows=telemetry_rows,
        )
        telemetry_out.write_text(telemetry.model_dump_json())

    return RolloutResult(
        rollout_id=config.rollout_id,
        success=success,
        steps_taken=steps,
        video_path=video_out if record_video else None,
        env_name=config.env_name,
        policy_kind=config.policy_kind,
        seed=config.seed,
        telemetry_path=telemetry_out,
    )
