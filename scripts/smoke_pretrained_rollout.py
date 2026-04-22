"""H2 smoke test: run one pretrained BC-RNN rollout on NutAssemblySquare.

Acceptance: completes one episode (success or fail), writes an mp4 of the
frontview camera frames, and prints the success flag.

We bypass robomimic.utils.env_utils.create_env_from_metadata because robomimic
0.3.0's env_robosuite adapter still imports the legacy `mujoco_py` package,
which is dead on macOS arm64 / Python 3.12. The checkpoint's env_kwargs give
us everything needed to build the env via robosuite directly — and the obs
keys NutAssemblySquare emits already match the policy's expected shape spec
(object, robot0_eef_pos, robot0_eef_quat, robot0_gripper_qpos).
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

from src.sim.pretrained import RobomimicPolicy  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
CHECKPOINT = REPO_ROOT / "artifacts" / "checkpoints" / "square_ph_low_dim.pth"
OUT_DIR = REPO_ROOT / "artifacts" / "smoke"
OUT_MP4 = OUT_DIR / "pretrained_rollout.mp4"

CAMERA = "frontview"
RENDER_W, RENDER_H = 512, 512
MAX_STEPS = 400  # NutAssemblySquare horizon in robomimic configs is 400
RENDER_FPS = 20  # matches control_freq from the checkpoint's env_kwargs


def main() -> int:
    if not CHECKPOINT.exists():
        print(f"ERR  checkpoint missing at {CHECKPOINT} — run scripts/fetch_checkpoints.py")
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    policy = RobomimicPolicy(CHECKPOINT)

    env_kwargs = policy.env_kwargs_for_robosuite()
    # Override training-time renderer settings: we need offscreen frames at
    # demo resolution, not the 84x84 the policy was trained on.
    env_kwargs["has_offscreen_renderer"] = True
    env_kwargs["camera_names"] = CAMERA
    env_kwargs["camera_heights"] = RENDER_H
    env_kwargs["camera_widths"] = RENDER_W

    env = suite.make(env_name=policy.env_name, **env_kwargs)
    obs = env.reset()
    policy.reset()

    frames: list[np.ndarray] = []
    success = False
    steps = 0
    for step in range(1, MAX_STEPS + 1):
        steps = step
        action = policy.act(obs)
        obs, _reward, _done, _info = env.step(action)

        # Direct sim.render avoids needing a public render() (robosuite envs
        # only expose render() for the on-screen viewer). Frame is RGB but
        # vertically flipped (OpenGL bottom-left origin).
        frame = env.sim.render(camera_name=CAMERA, width=RENDER_W, height=RENDER_H)
        frames.append(frame[::-1])

        if env._check_success():
            success = True
            break

    imageio.mimsave(OUT_MP4, frames, fps=RENDER_FPS)

    print(
        f"OK  steps={steps}  success={success}  frames={len(frames)}  "
        f"path={OUT_MP4.relative_to(REPO_ROOT)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
