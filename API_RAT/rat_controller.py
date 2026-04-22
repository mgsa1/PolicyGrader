"""Keyboard -> rat velocity actuator targets.

`mujoco.viewer.launch_passive`'s `key_callback` only fires on key press and
GLFW auto-repeat — it never receives release events. To emulate continuous
'is-key-held' state, we stamp each key's last-seen time and decay.
"""

from __future__ import annotations

import math
import time

import mujoco
import numpy as np

MOVE_SPEED = 4.5
STRAFE_SPEED = 3.5
YAW_RATE = 2.5

# GLFW auto-repeat is ~30 ms; hold the "still pressed" assumption for 120 ms
# after the last event so short repeat gaps don't stutter movement.
KEY_HOLD_TIMEOUT = 0.12


class RatController:
    def __init__(self, model: mujoco.MjModel, data: mujoco.MjData) -> None:
        self.model = model
        self.data = data
        self.act_vx = model.actuator("rat_vx").id
        self.act_vy = model.actuator("rat_vy").id
        self.act_vyaw = model.actuator("rat_vyaw").id
        self.joint_yaw_qposadr = int(model.jnt_qposadr[model.joint("rat_yaw").id])
        self.rat_body_id = model.body("rat").id
        self.last_seen: dict[int, float] = {}

    def on_key(self, key: int) -> None:
        self.last_seen[key] = time.monotonic()

    def _held(self, *keys: int) -> bool:
        now = time.monotonic()
        return any((now - self.last_seen.get(k, 0.0)) < KEY_HOLD_TIMEOUT for k in keys)

    def step(self) -> None:
        import glfw

        forward = int(self._held(glfw.KEY_W, glfw.KEY_UP)) - int(
            self._held(glfw.KEY_S, glfw.KEY_DOWN)
        )
        strafe = int(self._held(glfw.KEY_A)) - int(self._held(glfw.KEY_D))
        turn = int(self._held(glfw.KEY_LEFT, glfw.KEY_Q)) - int(
            self._held(glfw.KEY_RIGHT, glfw.KEY_E)
        )

        yaw = float(self.data.qpos[self.joint_yaw_qposadr])
        cos_y, sin_y = math.cos(yaw), math.sin(yaw)

        vx_local = forward * MOVE_SPEED
        vy_local = strafe * STRAFE_SPEED

        vx_world = cos_y * vx_local - sin_y * vy_local
        vy_world = sin_y * vx_local + cos_y * vy_local

        self.data.ctrl[self.act_vx] = vx_world
        self.data.ctrl[self.act_vy] = vy_world
        self.data.ctrl[self.act_vyaw] = turn * YAW_RATE

    def position(self) -> np.ndarray:
        return np.array(self.data.xpos[self.rat_body_id])

    def clear_input(self) -> None:
        self.last_seen.clear()
