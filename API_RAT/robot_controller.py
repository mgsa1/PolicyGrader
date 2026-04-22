"""Reactive Franka controller that tracks the rat with joint1.

Joints 2-7 stay at their home pose so the broom hangs vertically at a fixed
radius. Joint1 yaws the whole arm to put the broom between the rat and the
key box, with lead-time prediction, a reaction delay, and a lunge trigger
when the rat gets close.

Tunables (DIFFICULTY, LEAD_TIME, ...) live at the top so we can dial the
game at demo time.
"""

from __future__ import annotations

import math

import mujoco
import numpy as np

DIFFICULTY = 1.0
# Short lead-time + near-zero reaction delay + tiny aim jitter make the
# broom track the rat almost perfectly — the game is meant to be
# nearly impossible, with only occasional human-timing-based openings.
LEAD_TIME = 0.25
REACTION_DELAY = 0.02
AIM_JITTER = 0.012
LUNGE_RADIUS = 2.2
LUNGE_COOLDOWN = 0.7
LUNGE_EXTEND_TIME = 0.08
LUNGE_HOLD_TIME = 0.06
LUNGE_RETRACT_TIME = 0.12

HOME_J2 = 0.0
HOME_J4 = -math.pi / 2
HOME_J6 = math.pi / 2
HOME_J7 = -math.pi / 4

LUNGE_J2 = 0.35
LUNGE_J4 = -math.pi / 2 - 0.25


def _shortest_angle(delta: float) -> float:
    while delta > math.pi:
        delta -= 2 * math.pi
    while delta < -math.pi:
        delta += 2 * math.pi
    return delta


class RobotController:
    def __init__(self, model: mujoco.MjModel, data: mujoco.MjData) -> None:
        self.model = model
        self.data = data

        self.act_j1 = model.actuator("actuator1").id
        self.act_j2 = model.actuator("actuator2").id
        self.act_j3 = model.actuator("actuator3").id
        self.act_j4 = model.actuator("actuator4").id
        self.act_j5 = model.actuator("actuator5").id
        self.act_j6 = model.actuator("actuator6").id
        self.act_j7 = model.actuator("actuator7").id
        self.act_grip = model.actuator("actuator8").id

        # Gameplay > realism: crank joint1 well past the real Franka's 87 Nm
        # so the arm can outrun the rat's 5 m/s top speed with margin.
        # Broom tip at r≈0.55 m needs ω≈18 rad/s to reach ~10 m/s, so we
        # make sure the actuator can sustain that.
        model.actuator_forcerange[self.act_j1] = [-1200.0, 1200.0]
        model.actuator_gainprm[self.act_j1, 0] = 18000.0
        model.actuator_biasprm[self.act_j1, 1] = -18000.0
        model.actuator_biasprm[self.act_j1, 2] = -700.0

        self.j1_qposadr = int(model.jnt_qposadr[model.joint("joint1").id])

        self.rat_body_id = model.body("rat").id
        self.rat_x_qveladr = int(model.jnt_dofadr[model.joint("rat_x").id])
        self.rat_y_qveladr = int(model.jnt_dofadr[model.joint("rat_y").id])
        self.key_box_pos = np.array(data.xpos[model.body("ANTHROPIC_API_KEY").id], copy=True)

        self.target_j1 = 0.0
        self.reaction_timer = 0.0
        self.lunge_state = "idle"
        self.lunge_phase = 0.0
        self.lunge_cooldown = 0.0

        self._rng = np.random.default_rng(0xA91)
        self._apply_rest_pose()

    def _apply_rest_pose(self, extend: float = 0.0) -> None:
        self.data.ctrl[self.act_j2] = HOME_J2 + extend * (LUNGE_J2 - HOME_J2)
        self.data.ctrl[self.act_j3] = 0.0
        self.data.ctrl[self.act_j4] = HOME_J4 + extend * (LUNGE_J4 - HOME_J4)
        self.data.ctrl[self.act_j5] = 0.0
        self.data.ctrl[self.act_j6] = HOME_J6
        self.data.ctrl[self.act_j7] = HOME_J7
        self.data.ctrl[self.act_grip] = 255.0

    def _pick_aim_angle(self) -> float:
        rat_pos = self.data.xpos[self.rat_body_id]
        rat_vx = float(self.data.qvel[self.rat_x_qveladr])
        rat_vy = float(self.data.qvel[self.rat_y_qveladr])

        cur_x, cur_y = float(rat_pos[0]), float(rat_pos[1])
        pred_x = cur_x + rat_vx * LEAD_TIME
        pred_y = cur_y + rat_vy * LEAD_TIME

        box_x, box_y = float(self.key_box_pos[0]), float(self.key_box_pos[1])
        d_cur = math.hypot(cur_x - box_x, cur_y - box_y)
        d_pred = math.hypot(pred_x - box_x, pred_y - box_y)

        aim_x, aim_y = (cur_x, cur_y) if d_cur < d_pred else (pred_x, pred_y)
        jitter = float(self._rng.uniform(-AIM_JITTER, AIM_JITTER))
        return math.atan2(aim_y, aim_x) + jitter

    def step(self, dt: float) -> None:
        self.reaction_timer -= dt
        if self.reaction_timer <= 0.0:
            raw = self._pick_aim_angle()
            # Unwrap relative to the current commanded target so ctrl stays
            # continuous when the rat crosses the ±pi seam behind the robot.
            # Without this, atan2 jumps between +pi and -pi every tick and the
            # servo alternates directions, net zero motion.
            delta = _shortest_angle(raw - self.target_j1)
            self.target_j1 += delta
            # Clamp to joint range; if the rat is past the limit the arm just
            # commits to the closest reachable angle.
            self.target_j1 = max(-2.85, min(2.85, self.target_j1))
            self.reaction_timer = REACTION_DELAY

        self.data.ctrl[self.act_j1] = self.target_j1 * DIFFICULTY

        rat_pos = self.data.xpos[self.rat_body_id]
        rat_dist = math.hypot(float(rat_pos[0]), float(rat_pos[1]))

        self.lunge_cooldown -= dt
        if self.lunge_state == "idle" and self.lunge_cooldown <= 0.0 and rat_dist < LUNGE_RADIUS:
            self.lunge_state = "extend"
            self.lunge_phase = 0.0

        extend_frac = 0.0
        if self.lunge_state == "extend":
            self.lunge_phase += dt
            extend_frac = min(self.lunge_phase / LUNGE_EXTEND_TIME, 1.0)
            if self.lunge_phase >= LUNGE_EXTEND_TIME:
                self.lunge_state = "hold"
                self.lunge_phase = 0.0
        elif self.lunge_state == "hold":
            self.lunge_phase += dt
            extend_frac = 1.0
            if self.lunge_phase >= LUNGE_HOLD_TIME:
                self.lunge_state = "retract"
                self.lunge_phase = 0.0
        elif self.lunge_state == "retract":
            self.lunge_phase += dt
            extend_frac = max(1.0 - self.lunge_phase / LUNGE_RETRACT_TIME, 0.0)
            if self.lunge_phase >= LUNGE_RETRACT_TIME:
                self.lunge_state = "idle"
                self.lunge_phase = 0.0
                self.lunge_cooldown = LUNGE_COOLDOWN

        self._apply_rest_pose(extend=extend_frac)
