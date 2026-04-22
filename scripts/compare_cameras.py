"""Render NutAssemblySquare from several cameras so the user can pick one.

One-off exploratory tool — not part of the pipeline. Renders the post-reset
state (nut + peg + arm visible) from a handful of robosuite's stock cameras
and writes one PNG per camera to artifacts/smoke/camera_compare/.

Also renders synthesized variants by editing the model camera pose AFTER
env.reset() (writing before reset gets clobbered when robosuite reinitializes
the model). Specifically:
  - frontview_elevated: frontview lifted +35 cm and pitched down 15°
  - midpoint_front_agent: world-pose midpoint of frontview and agentview
    (linear lerp on position, slerp on orientation)
"""

from __future__ import annotations

import math
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.constants import MUJOCO_GL_ENV_KEY  # noqa: E402

os.environ.setdefault(MUJOCO_GL_ENV_KEY, "glfw")

import imageio.v2 as imageio  # noqa: E402
import numpy as np  # noqa: E402
import robosuite as suite  # noqa: E402
from robosuite.controllers import load_composite_controller_config  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "artifacts" / "smoke" / "camera_compare"

STOCK_CAMERAS = ["frontview", "agentview", "sideview", "birdview"]
RENDER_W, RENDER_H = 512, 512
WARMUP_STEPS = 40  # run no-op steps so the arm settles into start pose


def _render_from(env: suite.environments.ManipulationEnv, camera_name: str) -> np.ndarray:
    frame = env.sim.render(camera_name=camera_name, width=RENDER_W, height=RENDER_H)
    return frame[::-1]


def _make_env(camera_name: str) -> suite.environments.ManipulationEnv:
    controller_cfg = load_composite_controller_config(controller="BASIC", robot="Panda")
    return suite.make(
        env_name="NutAssemblySquare",
        robots="Panda",
        controller_configs=controller_cfg,
        has_renderer=False,
        has_offscreen_renderer=True,
        use_camera_obs=False,
        camera_names=camera_name,
        camera_heights=RENDER_H,
        camera_widths=RENDER_W,
        horizon=400,
        control_freq=20,
    )


def _quat_mul(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Hamilton product for MuJoCo's (w, x, y, z) quaternion order."""
    aw, ax, ay, az = a
    bw, bx, by, bz = b
    return np.array(
        [
            aw * bw - ax * bx - ay * by - az * bz,
            aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw,
        ]
    )


def _rotate_vec_by_quat(v: np.ndarray, q: np.ndarray) -> np.ndarray:
    """Rotate a 3-vector by a (w, x, y, z) quaternion via the rotation-matrix form."""
    w, x, y, z = q
    xx, yy, zz = x * x, y * y, z * z
    xy, xz, yz = x * y, x * z, y * z
    wx, wy, wz = w * x, w * y, w * z
    rot = np.array(
        [
            [1 - 2 * (yy + zz), 2 * (xy - wz), 2 * (xz + wy)],
            [2 * (xy + wz), 1 - 2 * (xx + zz), 2 * (yz - wx)],
            [2 * (xz - wy), 2 * (yz + wx), 1 - 2 * (xx + yy)],
        ]
    )
    return rot @ v


def _translate_along_view_axis(
    env: suite.environments.ManipulationEnv, camera_name: str, distance_m: float
) -> None:
    """Translate a camera backward (positive distance) along its local +z axis.

    MuJoCo cameras look along their local -z; +z is therefore "behind". Useful
    after pose composition to dolly the camera away from the scene without
    changing its look direction.
    """
    cam_id = env.sim.model.camera_name2id(camera_name)
    backward_world = _rotate_vec_by_quat(np.array([0.0, 0.0, 1.0]), env.sim.model.cam_quat[cam_id])
    env.sim.model.cam_pos[cam_id] = env.sim.model.cam_pos[cam_id] + distance_m * backward_world


def _slerp(q0: np.ndarray, q1: np.ndarray, t: float) -> np.ndarray:
    """Spherical linear interpolation of two unit quaternions in (w,x,y,z) order."""
    q0 = q0 / np.linalg.norm(q0)
    q1 = q1 / np.linalg.norm(q1)
    dot = float(np.dot(q0, q1))
    if dot < 0.0:
        q1 = -q1
        dot = -dot
    if dot > 0.9995:
        out = q0 + t * (q1 - q0)
        return out / np.linalg.norm(out)
    theta_0 = math.acos(max(-1.0, min(1.0, dot)))
    sin_theta_0 = math.sin(theta_0)
    theta = theta_0 * t
    s0 = math.sin(theta_0 - theta) / sin_theta_0
    s1 = math.sin(theta) / sin_theta_0
    return s0 * q0 + s1 * q1


def _elevate_frontview(env: suite.environments.ManipulationEnv) -> None:
    """Raise frontview +35 cm and pitch it down 15° around its local x-axis.

    Must be called AFTER env.reset() — robosuite reinitializes model data
    inside reset() and clobbers any pre-reset cam edits.
    """
    cam_id = env.sim.model.camera_name2id("frontview")
    pos = env.sim.model.cam_pos[cam_id].copy()
    pos[2] += 0.35
    env.sim.model.cam_pos[cam_id] = pos
    half = math.radians(15) / 2
    tilt = np.array([math.cos(half), -math.sin(half), 0.0, 0.0])
    env.sim.model.cam_quat[cam_id] = _quat_mul(env.sim.model.cam_quat[cam_id], tilt)


def _set_to_midpoint_of(
    env: suite.environments.ManipulationEnv,
    target_camera: str,
    cam_a: str,
    cam_b: str,
    t: float = 0.5,
) -> None:
    """Override `target_camera`'s pose with the (1-t)·A + t·B world-pose mix.

    Position is linearly interpolated, orientation is slerped. Assumes all
    three cameras are attached to the worldbody (cam_bodyid == 0); if any
    camera has a non-worldbody parent, model.cam_pos is a local offset and
    this function will silently produce the wrong world pose. We assert.
    """
    target_id = env.sim.model.camera_name2id(target_camera)
    a_id = env.sim.model.camera_name2id(cam_a)
    b_id = env.sim.model.camera_name2id(cam_b)
    for cid, name in ((target_id, target_camera), (a_id, cam_a), (b_id, cam_b)):
        body_id = int(env.sim.model.cam_bodyid[cid])
        assert body_id == 0, f"camera {name} is parented to body {body_id}, expected 0 (worldbody)"

    pos_mid = (1.0 - t) * env.sim.model.cam_pos[a_id] + t * env.sim.model.cam_pos[b_id]
    quat_mid = _slerp(env.sim.model.cam_quat[a_id], env.sim.model.cam_quat[b_id], t)
    env.sim.model.cam_pos[target_id] = pos_mid
    env.sim.model.cam_quat[target_id] = quat_mid


def _diagnostic(env: suite.environments.ManipulationEnv) -> None:
    """Print cam_pos / cam_quat / cam_bodyid for the four stock cameras."""
    for name in STOCK_CAMERAS:
        cid = env.sim.model.camera_name2id(name)
        pos = env.sim.model.cam_pos[cid]
        quat = env.sim.model.cam_quat[cid]
        body = int(env.sim.model.cam_bodyid[cid])
        print(f"  {name:10s} body={body}  pos={pos}  quat(wxyz)={quat}")


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    zero_action = np.zeros(7, dtype=np.float32)

    for cam in STOCK_CAMERAS:
        env = _make_env(cam)
        env.reset()
        if cam == STOCK_CAMERAS[0]:
            print("Camera diagnostics after reset:")
            _diagnostic(env)
        for _ in range(WARMUP_STEPS):
            env.step(zero_action)
        frame = _render_from(env, cam)
        out = OUT_DIR / f"{cam}.png"
        imageio.imwrite(out, frame)
        print(f"wrote {out.relative_to(REPO_ROOT)}")
        env.close()

    # Elevated frontview — modify AFTER reset.
    env = _make_env("frontview")
    env.reset()
    _elevate_frontview(env)
    for _ in range(WARMUP_STEPS):
        env.step(zero_action)
    frame = _render_from(env, "frontview")
    imageio.imwrite(OUT_DIR / "frontview_elevated.png", frame)
    print("wrote artifacts/smoke/camera_compare/frontview_elevated.png")
    env.close()

    # Midpoint of frontview and agentview — write into agentview's slot.
    # Make the env with BOTH cameras enabled so we can read their poses.
    controller_cfg = load_composite_controller_config(controller="BASIC", robot="Panda")
    env = suite.make(
        env_name="NutAssemblySquare",
        robots="Panda",
        controller_configs=controller_cfg,
        has_renderer=False,
        has_offscreen_renderer=True,
        use_camera_obs=False,
        camera_names=["frontview", "agentview"],
        camera_heights=RENDER_H,
        camera_widths=RENDER_W,
        horizon=400,
        control_freq=20,
    )
    env.reset()
    _set_to_midpoint_of(env, target_camera="agentview", cam_a="frontview", cam_b="agentview", t=0.5)
    _translate_along_view_axis(env, "agentview", distance_m=0.30)
    for _ in range(WARMUP_STEPS):
        env.step(zero_action)
    frame = _render_from(env, "agentview")
    imageio.imwrite(OUT_DIR / "midpoint_front_agent.png", frame)
    print("wrote artifacts/smoke/camera_compare/midpoint_front_agent.png")
    env.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
