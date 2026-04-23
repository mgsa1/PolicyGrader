"""Keyboard -> rat force / yaw targets.

Controls:
    ↑          forward
    ↓          backward
    ←          turn left
    →          turn right
    Q          strafe left
    E          strafe right

MuJoCo's native viewer hijacks several letter keys as render-flag
hotkeys (W = wireframe, D = depth, A = actuator vis, S = skin vis,
K = skybox, O = shadow, L = reflection, etc.), and those are handled
in the C++ layer before any Python callback can see them. The safe
set of non-hijacked keys for gameplay is tiny — E, Q, U, V, Y, and
the arrow keys — so movement lives on the arrows and strafe on Q/E.

Translation uses direct-force motors with damping compensation: while
a movement key is held we apply `m*accel + c*v_along_axis`, which
gives a *constant* acceleration (linear speed ramp) up to the max
speed — no spamming keys, just hold. Release = zero force, joint
damping handles the icy coast. Knockback impulses from the broom pass
through unresisted, so the player-vs-broom dynamic stays dramatic.

Yaw is a velocity servo so aiming snaps to stop on release.
"""

from __future__ import annotations

import math
import time

import mujoco
import numpy as np

# RC-car feel: snappy ramp to max speed (~0.5 s), brisk turn rate, modest
# coast when released.
MOVE_ACCEL = 10.0
STRAFE_ACCEL = 6.0
MAX_FORWARD = 5.0
MAX_STRAFE = 3.5
YAW_RATE = 4.0

# macOS's default key auto-repeat has a long initial delay (~500 ms)
# before it fires subsequent repeat events. Use a dynamic timeout: treat
# the key as held for up to KEY_HOLD_INITIAL after the first press so
# the rat doesn't stall during that gap, then tighten to KEY_HOLD_REPEAT
# once we see a second event (= auto-repeat is running, release detection
# becomes snappy again).
KEY_HOLD_INITIAL = 0.7
KEY_HOLD_REPEAT = 0.08


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
        # Effective translational mass at each slide joint =
        # body mass + armature. Used so the damping-compensation force
        # produces the intended acceleration.
        body_mass = float(model.body_mass[self.rat_body_id])
        arm_x = float(model.dof_armature[self.dofadr_x])
        self.m_eff = body_mass + arm_x
        # Per-slide-joint Rayleigh damping coefficient.
        self.damp_x = float(model.dof_damping[self.dofadr_x])
        self.damp_y = float(model.dof_damping[self.dofadr_y])
        self.last_seen: dict[int, float] = {}
        # When we see a key arrive again within REPEAT window of the prior
        # event, auto-repeat is active — switch that key to the tight
        # KEY_HOLD_REPEAT timeout.
        self.in_repeat: dict[int, bool] = {}

    def on_key(self, key: int) -> None:
        now = time.monotonic()
        prev = self.last_seen.get(key, 0.0)
        if prev and now - prev < KEY_HOLD_INITIAL:
            self.in_repeat[key] = True
        else:
            self.in_repeat[key] = False
        self.last_seen[key] = now

    def _held(self, *keys: int) -> bool:
        now = time.monotonic()
        for k in keys:
            last = self.last_seen.get(k, 0.0)
            if not last:
                continue
            timeout = KEY_HOLD_REPEAT if self.in_repeat.get(k, False) else KEY_HOLD_INITIAL
            if now - last < timeout:
                return True
        return False

    def step(self) -> None:
        import glfw

        # Arrow keys only for move/turn — see module docstring for why WASD
        # is off-limits.
        forward = int(self._held(glfw.KEY_UP)) - int(self._held(glfw.KEY_DOWN))
        turn = int(self._held(glfw.KEY_LEFT)) - int(self._held(glfw.KEY_RIGHT))
        strafe = int(self._held(glfw.KEY_Q)) - int(self._held(glfw.KEY_E))

        yaw = float(self.data.qpos[self.qposadr_yaw])
        cos_y, sin_y = math.cos(yaw), math.sin(yaw)
        cur_vx = float(self.data.qvel[self.dofadr_x])
        cur_vy = float(self.data.qvel[self.dofadr_y])

        # Rat-local axes in world frame: forward = local +x, strafe-left = +y.
        fwd_x, fwd_y = cos_y, sin_y
        strafe_x, strafe_y = -sin_y, cos_y

        fx = 0.0
        fy = 0.0

        if forward != 0:
            vel_along = cur_vx * fwd_x + cur_vy * fwd_y
            signed_speed = forward * vel_along  # positive while moving with input
            if signed_speed < MAX_FORWARD:
                # F = m * a  (desired acceleration) + damping compensation
                # (c*v in the forward direction). Yields a *constant* accel.
                push = forward * (self.m_eff * MOVE_ACCEL)
                damp_comp_x = self.damp_x * vel_along * fwd_x
                damp_comp_y = self.damp_y * vel_along * fwd_y
                fx += push * fwd_x + damp_comp_x
                fy += push * fwd_y + damp_comp_y

        if strafe != 0:
            vel_along_s = cur_vx * strafe_x + cur_vy * strafe_y
            signed_s = strafe * vel_along_s
            if signed_s < MAX_STRAFE:
                push = strafe * (self.m_eff * STRAFE_ACCEL)
                damp_comp_x = self.damp_x * vel_along_s * strafe_x
                damp_comp_y = self.damp_y * vel_along_s * strafe_y
                fx += push * strafe_x + damp_comp_x
                fy += push * strafe_y + damp_comp_y

        self.data.ctrl[self.act_fx] = fx
        self.data.ctrl[self.act_fy] = fy
        self.data.ctrl[self.act_vyaw] = turn * YAW_RATE

    def position(self) -> np.ndarray:
        return np.array(self.data.xpos[self.rat_body_id])

    def clear_input(self) -> None:
        self.last_seen.clear()
        self.in_repeat.clear()
