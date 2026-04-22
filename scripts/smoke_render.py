"""H1 smoke test: render one offscreen frame from a robosuite Lift env.

Acceptance: a PNG appears at artifacts/smoke/frame_000.png with shape (H, W, 3).
Default GL backend is glfw (macOS native); override via MUJOCO_GL=osmesa if it fails.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Make `src.*` importable when invoked as `python scripts/smoke_render.py`
# (per CLAUDE.md §10) without a project install.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.constants import MUJOCO_GL_ENV_KEY  # noqa: E402

# Set GL backend before robosuite imports MuJoCo. macOS Apple Silicon has no
# real EGL — glfw is the right first attempt; osmesa is the documented
# fallback (requires `brew install mesa`).
os.environ.setdefault(MUJOCO_GL_ENV_KEY, "glfw")

import imageio.v3 as iio  # noqa: E402
import numpy as np  # noqa: E402
import robosuite as suite  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "artifacts" / "smoke"
OUT_PATH = OUT_DIR / "frame_000.png"

ENV_NAME = "Lift"
ROBOT = "Panda"
CAMERA = "frontview"
WIDTH, HEIGHT = 512, 512


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    env = suite.make(
        env_name=ENV_NAME,
        robots=ROBOT,
        has_renderer=False,
        has_offscreen_renderer=True,
        use_camera_obs=True,
        camera_names=CAMERA,
        camera_widths=WIDTH,
        camera_heights=HEIGHT,
    )
    try:
        obs = env.reset()
        # robosuite returns RGB but vertically flipped (OpenGL origin is bottom-left).
        frame: np.ndarray = obs[f"{CAMERA}_image"][::-1]
    finally:
        env.close()

    iio.imwrite(OUT_PATH, frame)

    backend = os.environ[MUJOCO_GL_ENV_KEY]
    print(
        f"OK  backend={backend}  env={ENV_NAME}  shape={frame.shape}  "
        f"dtype={frame.dtype}  path={OUT_PATH.relative_to(REPO_ROOT)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
