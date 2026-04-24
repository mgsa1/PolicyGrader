"""H2b smoke: run one scripted Lift rollout (no failures injected) and check it lifts.

Acceptance: cube z-coordinate rises above the lift threshold (env._check_success())
within the horizon, and an mp4 of the frontview camera is written to artifacts/smoke.

This is the clean-config baseline. The injected-failure variants are exercised by
tests/test_scripted_failure_injection.py — here we only verify the nominal state
machine actually picks the cube up.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.constants import MUJOCO_GL_ENV_KEY  # noqa: E402

os.environ.setdefault(MUJOCO_GL_ENV_KEY, "glfw")

import imageio  # noqa: E402
import numpy as np  # noqa: E402
import robosuite as suite  # noqa: E402
from robosuite.controllers import load_controller_config  # noqa: E402

from src.sim.scripted import InjectedFailures, ScriptedLiftPolicy  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "artifacts" / "smoke"
OUT_MP4 = OUT_DIR / "scripted_rollout.mp4"

CAMERA = "frontview"
RENDER_W, RENDER_H = 512, 512
HORIZON = 250
RENDER_FPS = 20


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    controller_cfg = load_controller_config(default_controller="OSC_POSE")
    env = suite.make(
        env_name="Lift",
        robots="Panda",
        controller_configs=controller_cfg,
        has_renderer=False,
        has_offscreen_renderer=True,
        use_camera_obs=False,
        control_freq=20,
        horizon=HORIZON,
        camera_names=CAMERA,
        camera_heights=RENDER_H,
        camera_widths=RENDER_W,
    )

    policy = ScriptedLiftPolicy(InjectedFailures(), seed=0)

    obs = env.reset()
    policy.reset()

    frames: list[np.ndarray] = []
    success = False
    steps = 0
    for step in range(1, HORIZON + 1):
        steps = step
        action = policy.act(obs)
        obs, _reward, _done, _info = env.step(action)

        frame = env.sim.render(camera_name=CAMERA, width=RENDER_W, height=RENDER_H)
        frames.append(frame[::-1])

        if env._check_success():
            success = True
            break

    imageio.mimsave(OUT_MP4, frames, fps=RENDER_FPS)

    final_cube_z = float(np.asarray(obs["cube_pos"])[2])
    print(
        f"OK  steps={steps}  success={success}  cube_z={final_cube_z:.3f}  "
        f"phase={policy._state.phase}  path={OUT_MP4.relative_to(REPO_ROOT)}"
    )
    return 0 if success else 2


if __name__ == "__main__":
    sys.exit(main())
