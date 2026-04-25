"""Render the 9-second sign-off flythrough used by the Remotion pitch video.

A scripted camera dolly sweeps cheese → broom-shaking robot → rat reveal.
The Franka arm is driven directly (no RobotController) so we can choreograph
a victory broom-shake while the camera holds on it.

Output:
    robotics_pitch/public/api_rat/flythrough.mp4

Run from the repo root with the project venv:
    MUJOCO_GL=glfw .venv/bin/python -m API_RAT.render_pitch_video
"""

from __future__ import annotations

import math
import os
import sys
from dataclasses import dataclass
from pathlib import Path

os.environ.setdefault("MUJOCO_GL", "glfw")

import imageio.v3 as iio  # noqa: E402
import mujoco  # noqa: E402
import numpy as np  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
SCENE_PATH = Path(__file__).resolve().parent / "scene.xml"
OUT_PATH = REPO_ROOT / "robotics_pitch" / "public" / "api_rat" / "flythrough.mp4"

WIDTH, HEIGHT = 1920, 1080
FPS = 30
DURATION_S = 9.0
N_FRAMES = int(DURATION_S * FPS)

# Franka home joint targets. Lifted from API_RAT/robot_controller.py — kept
# local so the flythrough script doesn't need to import the controller.
HOME_J2 = 0.0
HOME_J4 = -math.pi / 2
HOME_J6 = math.pi / 2
HOME_J7 = -math.pi / 4

# Victory pose: shoulder rolls back (J2 negative), elbow opens (J4 less
# bent), wrist tucks. This raises the broom into a triumphant high-guard
# stance so the side-to-side wag at J1 reads cleanly across the cheese-row.
VICTORY_J2 = -0.5
VICTORY_J4 = -math.pi / 2 + 0.55

# Broom-shake parameters during the robot beat.
SHAKE_HZ = 1.4
SHAKE_AMP_RAD = 0.55  # ±31° of base yaw — broom tip sweeps ~0.6 m
SHAKE_RAMP_S = 0.5  # ramp-in / ramp-out so the wag doesn't snap on/off

# Beat boundaries on the timeline.
T_ROBOT_IN = 2.7
T_ROBOT_OUT = 6.5


@dataclass(frozen=True)
class CamKey:
    """Camera waypoint. Azimuth is left as a continuous float — no wrap —
    so a sweep from 110° → 30° actually orbits via 70° instead of going
    the long way around."""
    t: float
    lookat: tuple[float, float, float]
    distance: float
    azimuth: float
    elevation: float


def _ease(x: float) -> float:
    """Smoothstep — matches the Easing.bezier(0.22, 1, 0.36, 1) feel used
    on the Remotion side, so the in-video and overlay motion vocabularies
    don't fight each other."""
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


def _interp_camera(keys: list[CamKey], t: float) -> tuple[np.ndarray, float, float, float]:
    if t <= keys[0].t:
        k = keys[0]
        return np.array(k.lookat), k.distance, k.azimuth, k.elevation
    if t >= keys[-1].t:
        k = keys[-1]
        return np.array(k.lookat), k.distance, k.azimuth, k.elevation
    for a, b in zip(keys, keys[1:]):
        if a.t <= t <= b.t:
            u = _ease((t - a.t) / (b.t - a.t))
            lookat = (1 - u) * np.array(a.lookat) + u * np.array(b.lookat)
            return (
                lookat,
                (1 - u) * a.distance + u * b.distance,
                (1 - u) * a.azimuth + u * b.azimuth,
                (1 - u) * a.elevation + u * b.elevation,
            )
    raise RuntimeError("unreachable: t outside keyframe range")


def _camera_path(cheese_pos: np.ndarray, rat_pos: np.ndarray) -> list[CamKey]:
    """Three-act dolly:

    Act 1 (0–2.7 s) — close-orbit on the cheese, label visible above.
    Act 2 (2.7–6.5 s) — pull back and rise to frame the Franka, with the
        camera drifting around so the broom-shake reads from the side.
    Act 3 (6.5–9.0 s) — long arc out and down to land near intro_cam,
        looking back over the rat at the (still-shaking) Franka.
    """
    cheese_lookat = (
        float(cheese_pos[0]),
        float(cheese_pos[1]),
        float(cheese_pos[2]) + 0.18,
    )
    rat_lookat = (float(rat_pos[0]), float(rat_pos[1]), 0.18)
    return [
        CamKey(0.0, cheese_lookat, 0.55, 110.0, -10.0),
        CamKey(2.0, cheese_lookat, 0.85, 70.0, -16.0),
        CamKey(2.7, (0.20, 0.0, 0.45), 1.30, 55.0, -14.0),
        CamKey(4.5, (0.0, 0.0, 0.65), 1.80, 25.0, -10.0),
        CamKey(6.0, (0.0, 0.0, 0.65), 2.10, 0.0, -8.0),
        CamKey(7.0, (-1.5, -1.5, 0.40), 3.20, 25.0, -12.0),
        CamKey(8.5, rat_lookat, 1.85, 45.0, -16.0),
        CamKey(9.0, rat_lookat, 1.65, 45.0, -16.0),
    ]


def _shake_amplitude(t: float) -> float:
    """Ramp the broom-shake in over SHAKE_RAMP_S as the robot beat opens
    and ramp it out as the camera pulls away. Holds full amplitude across
    the dwell so the wag is unmistakable on screen."""
    if t < T_ROBOT_IN - SHAKE_RAMP_S:
        return 0.0
    if t < T_ROBOT_IN:
        return _ease((t - (T_ROBOT_IN - SHAKE_RAMP_S)) / SHAKE_RAMP_S)
    if t < T_ROBOT_OUT:
        return 1.0
    if t < T_ROBOT_OUT + SHAKE_RAMP_S:
        return _ease(1.0 - (t - T_ROBOT_OUT) / SHAKE_RAMP_S)
    return 0.0


def _drive_franka(
    data: mujoco.MjData,
    t: float,
    actuators: dict[str, int],
) -> None:
    """Override RobotController. Holds the rest pose, ramps into a victory
    posture during the robot beat, and oscillates J1 so the broom wags
    side-to-side. The lift on J2/J4 also persists into act 3 so the
    distant Franka in the rat shot still looks triumphant."""
    posture = _ease(min(1.0, max(0.0, (t - (T_ROBOT_IN - 0.4)) / 0.8)))

    j2 = HOME_J2 + posture * (VICTORY_J2 - HOME_J2)
    j4 = HOME_J4 + posture * (VICTORY_J4 - HOME_J4)

    amp = _shake_amplitude(t) * SHAKE_AMP_RAD
    j1 = math.sin(2 * math.pi * SHAKE_HZ * t) * amp

    data.ctrl[actuators["j1"]] = j1
    data.ctrl[actuators["j2"]] = j2
    data.ctrl[actuators["j3"]] = 0.0
    data.ctrl[actuators["j4"]] = j4
    data.ctrl[actuators["j5"]] = 0.0
    data.ctrl[actuators["j6"]] = HOME_J6
    data.ctrl[actuators["j7"]] = HOME_J7
    data.ctrl[actuators["grip"]] = 255.0


def _make_options() -> mujoco.MjvOption:
    opt = mujoco.MjvOption()
    # Site label is the ANTHROPIC_API_KEY tag above the cheese — the only
    # site in the model so no other text renders.
    opt.label = mujoco.mjtLabel.mjLABEL_SITE
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
    for g in range(3, 6):
        opt.geomgroup[g] = 0
    return opt


def main() -> int:
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    model = mujoco.MjModel.from_xml_path(str(SCENE_PATH))
    data = mujoco.MjData(model)

    # Override scene's offscreen framebuffer cap — set in the XML for
    # in-game render cost — without touching scene.xml.
    model.vis.global_.offwidth = WIDTH
    model.vis.global_.offheight = HEIGHT

    # Crank J1 force ceiling the same way RobotController does, so the
    # shake-amplitude actually resolves under the high inertia of the arm.
    j1_actuator = model.actuator("actuator1").id
    model.actuator_forcerange[j1_actuator] = [-1200.0, 1200.0]
    model.actuator_gainprm[j1_actuator, 0] = 18000.0
    model.actuator_biasprm[j1_actuator, 1] = -18000.0
    model.actuator_biasprm[j1_actuator, 2] = -700.0

    start_key = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_KEY, "start")
    mujoco.mj_resetDataKeyframe(model, data, start_key)
    data.ctrl[:] = model.key_ctrl[start_key]
    mujoco.mj_forward(model, data)

    cheese_pos = np.array(data.xpos[model.body("key_cheese").id], copy=True)
    rat_pos = np.array(data.xpos[model.body("rat").id], copy=True)

    hand_body = model.body("hand").id
    broom_mocap_id = int(model.body_mocapid[model.body("broom").id])
    data.mocap_pos[broom_mocap_id] = data.xpos[hand_body]
    data.mocap_quat[broom_mocap_id] = data.xquat[hand_body]

    actuators = {f"j{i}": model.actuator(f"actuator{i}").id for i in range(1, 8)}
    actuators["grip"] = model.actuator("actuator8").id

    # Pin the rat actuators to zero — we don't want the rat sliding across
    # the floor while the camera dollies. The rat does drift slightly under
    # damping but at 9 s of sim time it's invisible.
    rat_actuators = [
        model.actuator("rat_fx").id,
        model.actuator("rat_fy").id,
        model.actuator("rat_vyaw").id,
    ]

    keys = _camera_path(cheese_pos, rat_pos)

    sim_dt = float(model.opt.timestep)
    steps_per_frame = max(1, int(round((1.0 / FPS) / sim_dt)))

    renderer = mujoco.Renderer(model, height=HEIGHT, width=WIDTH)
    opt = _make_options()
    cam = mujoco.MjvCamera()
    cam.type = mujoco.mjtCamera.mjCAMERA_FREE

    frames: list[np.ndarray] = []
    for f in range(N_FRAMES):
        t = f / FPS
        _drive_franka(data, t, actuators)
        for a in rat_actuators:
            data.ctrl[a] = 0.0

        for _ in range(steps_per_frame):
            mujoco.mj_step(model, data)
            data.mocap_pos[broom_mocap_id] = data.xpos[hand_body]
            data.mocap_quat[broom_mocap_id] = data.xquat[hand_body]

        lookat, dist, az, el = _interp_camera(keys, t)
        cam.lookat[:] = lookat
        cam.distance = float(dist)
        cam.azimuth = float(az)
        cam.elevation = float(el)

        renderer.update_scene(data, camera=cam, scene_option=opt)
        frames.append(renderer.render().copy())

    iio.imwrite(
        OUT_PATH,
        np.stack(frames),
        fps=FPS,
        plugin="FFMPEG",
        codec="libx264",
        # yuv420p so QuickTime / Safari / Chromium all play it cleanly.
        output_params=["-pix_fmt", "yuv420p"],
    )

    size_mb = OUT_PATH.stat().st_size / 1e6
    print(f"OK  {OUT_PATH}  {N_FRAMES} frames @ {FPS} fps  {size_mb:.1f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
