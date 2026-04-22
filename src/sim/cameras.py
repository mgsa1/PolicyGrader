"""Camera-pose utilities for robosuite envs.

Stock robosuite cameras are positioned for general visualization, not for
vision-judge tasks. For NutAssemblySquare neither `frontview` (too far back)
nor `agentview` (too close, too low) gives a clear view of nut-vs-peg
alignment, which is the failure mode that drives precision/recall on this
task. The midpoint pose between the two, dollied back 30 cm, does — see
scripts/compare_cameras.py for the side-by-side comparison.

All env-mutating helpers must run AFTER env.reset(); robosuite reinitializes
model data inside reset() and clobbers any cam_pos/cam_quat edits made
beforehand. Helpers also assume the target camera is parented to worldbody
(cam_bodyid == 0), so model.cam_pos is already in world coordinates —
verified for the four stock cameras on NutAssemblySquare.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

NUT_ENV_NAME = "NutAssemblySquare"
# We hijack the agentview slot rather than registering a new camera, because
# adding cameras at runtime requires XML editing. Anyone rendering from
# "agentview" on a NutAssemblySquare env after `apply_nut_eval_camera` gets
# the midpoint pose.
NUT_RENDER_CAMERA = "agentview"
_NUT_MIDPOINT_T = 0.5
_NUT_PULLBACK_M = 0.30


def _slerp(q0: np.ndarray[Any, Any], q1: np.ndarray[Any, Any], t: float) -> np.ndarray[Any, Any]:
    """Spherical linear interpolation of two unit quaternions in (w, x, y, z) order."""
    q0 = q0 / np.linalg.norm(q0)
    q1 = q1 / np.linalg.norm(q1)
    dot = float(np.dot(q0, q1))
    if dot < 0.0:
        q1 = -q1
        dot = -dot
    if dot > 0.9995:
        out = q0 + t * (q1 - q0)
        return np.asarray(out / np.linalg.norm(out))
    theta_0 = math.acos(max(-1.0, min(1.0, dot)))
    sin_theta_0 = math.sin(theta_0)
    theta = theta_0 * t
    s0 = math.sin(theta_0 - theta) / sin_theta_0
    s1 = math.sin(theta) / sin_theta_0
    return np.asarray(s0 * q0 + s1 * q1)


def _rotate_vec_by_quat(v: np.ndarray[Any, Any], q: np.ndarray[Any, Any]) -> np.ndarray[Any, Any]:
    """Rotate a 3-vector by a (w, x, y, z) quaternion via its rotation matrix."""
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
    return np.asarray(rot @ v)


def apply_nut_eval_camera(env: Any) -> None:
    """Override agentview's pose: midpoint(frontview, agentview) + 30 cm pull-back.

    The env must have both `frontview` and `agentview` allocated (pass them in
    `camera_names` when calling `suite.make`). Call after `env.reset()`.
    """
    front_id = env.sim.model.camera_name2id("frontview")
    agent_id = env.sim.model.camera_name2id("agentview")
    for cid, name in ((front_id, "frontview"), (agent_id, "agentview")):
        body_id = int(env.sim.model.cam_bodyid[cid])
        assert body_id == 0, f"camera {name} parented to body {body_id}, expected worldbody"

    pos_mid = (1.0 - _NUT_MIDPOINT_T) * env.sim.model.cam_pos[front_id] + (
        _NUT_MIDPOINT_T * env.sim.model.cam_pos[agent_id]
    )
    quat_mid = _slerp(
        env.sim.model.cam_quat[front_id],
        env.sim.model.cam_quat[agent_id],
        _NUT_MIDPOINT_T,
    )
    # MuJoCo cameras look along local -z; +local-z is "behind" in world frame.
    backward_world = _rotate_vec_by_quat(np.array([0.0, 0.0, 1.0]), quat_mid)
    env.sim.model.cam_pos[agent_id] = pos_mid + _NUT_PULLBACK_M * backward_world
    env.sim.model.cam_quat[agent_id] = quat_mid
