"""Keyboard -> rat force / yaw targets.

Controls:
    W / ↑      forward
    S / ↓      backward
    A / ←      turn left
    D / →      turn right
    Q          strafe left
    E          strafe right

Translation is driven by direct-force motors: a steady push while a
movement key is held, zero otherwise. Kinetic friction from the floor
+ rat geom decelerates coast. Same physics applies during input, after
release, and after a broom hit — one consistent ice feel. A soft
velocity cap stops the force at MAX_FORWARD / MAX_STRAFE; broom
impulses can push the rat past that cap (they're not gated by input).

Yaw is a velocity servo so aiming snaps to stop on release.

`mujoco.viewer.launch_passive`'s `key_callback` only fires on press and
GLFW auto-repeat — never on release. We stamp each key's last-seen time
and treat it as "still held" while that stamp is fresh.
"""

from __future__ import annotations

import math
import time

import mujoco
import numpy as np

MOVE_FORCE = 1.2
STRAFE_FORCE = 0.7
MAX_FORWARD = 4.0
MAX_STRAFE = 2.5
YAW_RATE = 2.8

KEY_HOLD_TIMEOUT = 0.12


class RatController:
    def __init__(self, model: mujoco.MjModel, data: mujoco.MjData) -> None:
        self.model = model
        self.data = data
        self.act_fx = model.actuator("rat_fx").id
        self.act_fy = model.actuator("rat_fy").id
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
        strafe = int(self._held(glfw.KEY_Q)) - int(self._held(glfw.KEY_E))

        yaw = float(self.data.qpos[self.qposadr_yaw])
        cos_y, sin_y = math.cos(yaw), math.sin(yaw)
        cur_vx = float(self.data.qvel[self.dofadr_x])
        cur_vy = float(self.data.qvel[self.dofadr_y])

        # Forward = rat's local +x; strafe-left = local +y.
        fwd_x, fwd_y = cos_y, sin_y
        strafe_x, strafe_y = -sin_y, cos_y

        fx = 0.0
        fy = 0.0

        if forward != 0:
            vel_along = cur_vx * fwd_x + cur_vy * fwd_y
            # Only push if we're still below the max speed *in the desired
            # direction*. This lets knockback push the rat past the cap
            # without the player's held key fighting it.
            if forward > 0 and vel_along < MAX_FORWARD:
                fx += MOVE_FORCE * fwd_x
                fy += MOVE_FORCE * fwd_y
            elif forward < 0 and -vel_along < MAX_FORWARD:
                fx -= MOVE_FORCE * fwd_x
                fy -= MOVE_FORCE * fwd_y

        if strafe != 0:
            vel_along_s = cur_vx * strafe_x + cur_vy * strafe_y
            if strafe > 0 and vel_along_s < MAX_STRAFE:
                fx += STRAFE_FORCE * strafe_x
                fy += STRAFE_FORCE * strafe_y
            elif strafe < 0 and -vel_along_s < MAX_STRAFE:
                fx -= STRAFE_FORCE * strafe_x
                fy -= STRAFE_FORCE * strafe_y

        self.data.ctrl[self.act_fx] = fx
        self.data.ctrl[self.act_fy] = fy
        self.data.ctrl[self.act_vyaw] = turn * YAW_RATE

    def position(self) -> np.ndarray:
        return np.array(self.data.xpos[self.rat_body_id])

    def clear_input(self) -> None:
        self.last_seen.clear()
