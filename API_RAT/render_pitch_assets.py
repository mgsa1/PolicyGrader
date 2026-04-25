"""Render the three sign-off stills used by the Remotion pitch video.

Output:
    robotics_pitch/public/api_rat/cheese.png
    robotics_pitch/public/api_rat/robot.png
    robotics_pitch/public/api_rat/rat.png

Run from the repo root with the project venv:
    MUJOCO_GL=glfw .venv/bin/python -m API_RAT.render_pitch_assets

The offscreen `mujoco.Renderer` is happy under regular `python` — `mjpython`
is only required for `mujoco.viewer.launch_passive` (which we don't use).
If glfw fails on this machine, fall back to MUJOCO_GL=osmesa per the
project convention in scripts/smoke_render.py.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# GL backend must be picked before mujoco imports.
os.environ.setdefault("MUJOCO_GL", "glfw")

import imageio.v3 as iio  # noqa: E402
import mujoco  # noqa: E402
import numpy as np  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
SCENE_PATH = Path(__file__).resolve().parent / "scene.xml"
OUT_DIR = REPO_ROOT / "robotics_pitch" / "public" / "api_rat"

WIDTH, HEIGHT = 1920, 1080


def _load_scene() -> tuple[mujoco.MjModel, mujoco.MjData]:
    """Load scene.xml, reset to the start keyframe, pin the broom to the hand.

    Mirrors API_RAT/main.py lines 82-95 — broom is a mocap body that the
    game pins to the Franka hand each step. We do the same once before
    rendering so the broom shows up in the robot shot.
    """
    model = mujoco.MjModel.from_xml_path(str(SCENE_PATH))
    data = mujoco.MjData(model)

    start_key = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_KEY, "start")
    mujoco.mj_resetDataKeyframe(model, data, start_key)
    data.ctrl[:] = model.key_ctrl[start_key]
    mujoco.mj_forward(model, data)

    hand_body = model.body("hand").id
    broom_body = model.body("broom").id
    broom_mocap_id = int(model.body_mocapid[broom_body])
    data.mocap_pos[broom_mocap_id] = data.xpos[hand_body]
    data.mocap_quat[broom_mocap_id] = data.xquat[hand_body]
    mujoco.mj_forward(model, data)

    return model, data


def _make_options(*, with_site_label: bool) -> mujoco.MjvOption:
    """Visual options matching the in-game viewer setup (main.py 165-187).

    `with_site_label=True` enables the ANTHROPIC_API_KEY label above the
    cheese — there is exactly one site in the model so that's the only
    text that renders.
    """
    opt = mujoco.MjvOption()
    if with_site_label:
        opt.label = mujoco.mjtLabel.mjLABEL_SITE
    else:
        opt.label = mujoco.mjtLabel.mjLABEL_NONE
    for flag in (
        mujoco.mjtVisFlag.mjVIS_INERTIA,
        mujoco.mjtVisFlag.mjVIS_JOINT,
        mujoco.mjtVisFlag.mjVIS_ACTUATOR,
        mujoco.mjtVisFlag.mjVIS_CONTACTPOINT,
        mujoco.mjtVisFlag.mjVIS_CONTACTFORCE,
        mujoco.mjtVisFlag.mjVIS_TRANSPARENT,
        mujoco.mjtVisFlag.mjVIS_AUTOCONNECT,
        mujoco.mjtVisFlag.mjVIS_COM,
        mujoco.mjtVisFlag.mjVIS_PERTFORCE,
        mujoco.mjtVisFlag.mjVIS_PERTOBJ,
    ):
        opt.flags[flag] = 0
    # Hide collision-only geom groups (Franka collision meshes are 3).
    for g in range(3, 6):
        opt.geomgroup[g] = 0
    return opt


def _free_camera(
    *,
    lookat: np.ndarray,
    distance: float,
    azimuth: float,
    elevation: float,
) -> mujoco.MjvCamera:
    cam = mujoco.MjvCamera()
    cam.type = mujoco.mjtCamera.mjCAMERA_FREE
    cam.lookat[:] = lookat
    cam.distance = distance
    cam.azimuth = azimuth
    cam.elevation = elevation
    return cam


def _fixed_camera(model: mujoco.MjModel, name: str) -> mujoco.MjvCamera:
    """Use a named camera defined in scene.xml verbatim — preserves
    `mode="targetbody"` tracking that the free camera can't replicate."""
    cam = mujoco.MjvCamera()
    cam.type = mujoco.mjtCamera.mjCAMERA_FIXED
    cam.fixedcamid = model.camera(name).id
    return cam


def _render(
    renderer: mujoco.Renderer,
    data: mujoco.MjData,
    cam: mujoco.MjvCamera,
    opt: mujoco.MjvOption,
    out_path: Path,
) -> None:
    renderer.update_scene(data, camera=cam, scene_option=opt)
    pixels = renderer.render()
    iio.imwrite(out_path, pixels)


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    model, data = _load_scene()

    # scene.xml caps the offscreen framebuffer at 1280x720 for in-game render
    # cost; override here so we can render the pitch stills at 1080p without
    # touching the XML.
    model.vis.global_.offwidth = WIDTH
    model.vis.global_.offheight = HEIGHT

    cheese_body = model.body("key_cheese").id
    rat_body = model.body("rat").id

    cheese_pos = np.array(data.xpos[cheese_body], copy=True)
    rat_pos = np.array(data.xpos[rat_body], copy=True)

    renderer = mujoco.Renderer(model, height=HEIGHT, width=WIDTH)

    # Beat 1 — cheese hero. Low-angle three-quarter so the wedge silhouette
    # reads and the floating ANTHROPIC_API_KEY label sits clearly above.
    cheese_cam = _free_camera(
        lookat=np.array([cheese_pos[0], cheese_pos[1], cheese_pos[2] + 0.18]),
        distance=0.7,
        azimuth=110.0,
        elevation=-12.0,
    )
    cheese_path = OUT_DIR / "cheese.png"
    _render(renderer, data, cheese_cam, _make_options(with_site_label=True), cheese_path)

    # Beat 2 — robot + broom. Three-quarter so we see the gripper wrapped
    # around the broom handle and the bristles sweeping out at the bottom.
    robot_cam = _free_camera(
        lookat=np.array([0.0, 0.0, 0.55]),
        distance=1.55,
        azimuth=135.0,
        elevation=-10.0,
    )
    robot_path = OUT_DIR / "robot.png"
    _render(renderer, data, robot_cam, _make_options(with_site_label=False), robot_path)

    # Beat 3 — meet the rat. The intro_cam in scene.xml is the exact shot
    # the game uses for its "this is your rat" reveal — use it directly so
    # the targetbody tracking stays intact.
    rat_cam = _fixed_camera(model, "intro_cam")
    rat_path = OUT_DIR / "rat.png"
    _render(renderer, data, rat_cam, _make_options(with_site_label=False), rat_path)

    print(f"OK  cheese  {cheese_path}")
    print(f"OK  robot   {robot_path}")
    print(f"OK  rat     {rat_path}  (rat at {rat_pos.tolist()})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
