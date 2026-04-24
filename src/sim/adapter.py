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
from robosuite.controllers import load_composite_controller_config  # noqa: E402

from src.schemas import RolloutConfig, RolloutResult  # noqa: E402
from src.sim.policies import Policy  # noqa: E402
from src.sim.pretrained import RobomimicPolicy  # noqa: E402
from src.sim.scripted import ScriptedLiftPolicy  # noqa: E402

# After success, keep stepping for ~1 s so the recorded video shows the cube
# clearly held aloft over an empty table. Without this, the rollout cuts the
# instant success triggers and Pass-1 mistakes the ambiguous final frames for
# a failure. Does not affect steps_taken, which still reflects success step.
POST_SUCCESS_HOLD_STEPS = 20


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
    controller_cfg = load_composite_controller_config(controller="BASIC", robot="Panda")
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


def run_rollout(config: RolloutConfig, video_out: Path | None = None) -> RolloutResult:
    """Run one scenario end-to-end and return its result.

    If `video_out` is provided, an mp4 of the configured camera is written there.
    Pass None to skip rendering (useful for parallel sweeps where only the
    success/label outcome matters).
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

    record_video = video_out is not None
    frames: list[np.ndarray[Any, Any]] = []
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

        if not success:
            steps = step
            if env._check_success():
                success = True
                hold_remaining = POST_SUCCESS_HOLD_STEPS
        else:
            hold_remaining -= 1
            if hold_remaining <= 0:
                break

    if record_video and video_out is not None and frames:
        video_out.parent.mkdir(parents=True, exist_ok=True)
        imageio.mimsave(video_out, list(frames), fps=config.render.fps)

    return RolloutResult(
        rollout_id=config.rollout_id,
        success=success,
        steps_taken=steps,
        video_path=video_out if record_video else None,
        ground_truth_label=config.ground_truth_label,
        env_name=config.env_name,
        policy_kind=config.policy_kind,
        seed=config.seed,
    )
