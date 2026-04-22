"""Keyboard -> rat velocity actuator targets.

Controls:
    W / ↑      forward
    S / ↓      backward
    A / ←      turn left
    D / →      turn right

When no forward/back key is held, translation ctrl is set to the rat's
*current* qvel so the velocity-servo force is ~zero and the rat coasts
like it's on ice. Yaw instead snaps to stop when no turn key is held so
aiming stays crisp.

`mujoco.viewer.launch_passive`'s `key_callback` only fires on press and
GLFW auto-repeat — never on release. We stamp each key's last-seen time
and treat it as "still held" while that stamp is fresh.
"""

from __future__ import annotations

import math
import time

import mujoco
import numpy as np

MOVE_SPEED = 4.5
YAW_RATE = 2.8

# GLFW auto-repeat is ~30 ms; hold the "still pressed" assumption a little
# longer so short repeat gaps don't stutter.
KEY_HOLD_TIMEOUT = 0.12


class RatController:
    def __init__(self, model: mujoco.MjModel, data: mujoco.MjData) -> None:
        self.model = model
        self.data = data
        self.act_vx = model.actuator("rat_vx").id
        self.act_vy = model.actuator("rat_vy").id
        self.act_vyaw = model.actuator("rat_vyaw").id
        self.qposadr_yaw = int(model.jnt_qposadr[model.joint("rat_yaw").id])
        self.dofadr_x = int(model.jnt_dofadr[model.joint("rat_x").id])
        self.dofadr_y = int(model.jnt_dofadr[model.joint("rat_y").id])
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
        turn = int(self._held(glfw.KEY_A, glfw.KEY_LEFT)) - int(
            self._held(glfw.KEY_D, glfw.KEY_RIGHT)
        )

        yaw = float(self.data.qpos[self.qposadr_yaw])
        cur_vx = float(self.data.qvel[self.dofadr_x])
        cur_vy = float(self.data.qvel[self.dofadr_y])

        if forward != 0:
            cos_y, sin_y = math.cos(yaw), math.sin(yaw)
            target_vx = forward * MOVE_SPEED * cos_y
            target_vy = forward * MOVE_SPEED * sin_y
        else:
            # No input → drive ctrl to the current velocity so the servo
            # produces ~0 force and the rat glides.
            target_vx = cur_vx
            target_vy = cur_vy

        self.data.ctrl[self.act_vx] = target_vx
        self.data.ctrl[self.act_vy] = target_vy
        self.data.ctrl[self.act_vyaw] = turn * YAW_RATE

    def position(self) -> np.ndarray:
        return np.array(self.data.xpos[self.rat_body_id])

    def clear_input(self) -> None:
        self.last_seen.clear()
