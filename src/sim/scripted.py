"""Scripted state-machine pick policy for robosuite Lift, with injectable failure modes.

This is the source of GROUND-TRUTH labels for vision-judge precision/recall:
each rollout config carries an InjectedFailures and a derivable FailureMode
label that the judge's output is later compared against.

Lift was chosen over NutAssemblySquare because a 4-phase hand-coded policy
can reliably succeed on Lift; Square requires nut-peg orientation alignment
that takes 10x more code to get right. The eval mechanism (inject known
failure -> render video -> judge sees it -> measure agreement) is identical
either way.

Knob -> label mapping (priority high to low; first match wins):
  action_noise >= 0.1            -> KNOCK_OBJECT_OFF_TABLE
  approach_angle_offset_deg > 0  -> APPROACH_MISS
  gripper_close_prematurely      -> APPROACH_MISS  (closes in air, never grasps)
  grip_force_scale < 0.7         -> SLIP_DURING_LIFT
  otherwise                      -> NONE
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from math import cos, radians, sin
from typing import Any

import numpy as np

from src.sim.policies import Policy

CUBE_KEY = "cube_pos"
EEF_KEY = "robot0_eef_pos"
GRIPPER_QPOS_KEY = "robot0_gripper_qpos"

# OSC_POSE controller bounds (matches robosuite default for Panda).
POS_DELTA_MAX_M = 0.05
GRIP_OPEN = -1.0
GRIP_CLOSE = +1.0

APPROACH_HEIGHT_M = 0.10
GRASP_HEIGHT_OFFSET_M = 0.005
LIFT_HEIGHT_M = 0.20

POS_TOLERANCE_M = 0.01
GRASP_HOLD_STEPS = 8


class FailureMode(StrEnum):
    NONE = "none"
    APPROACH_MISS = "approach_miss"
    PREMATURE_RELEASE = "premature_release"
    SLIP_DURING_LIFT = "slip_during_lift"
    KNOCK_OBJECT_OFF_TABLE = "knock_object_off_table"


class _Phase(StrEnum):
    APPROACH = "approach"
    DESCEND = "descend"
    GRASP = "grasp"
    LIFT = "lift"
    DONE = "done"


@dataclass(frozen=True)
class InjectedFailures:
    action_noise: float = 0.0
    gripper_close_prematurely: bool = False
    approach_angle_offset_deg: float = 0.0
    grip_force_scale: float = 1.0

    def to_label(self) -> FailureMode:
        if self.action_noise >= 0.1:
            return FailureMode.KNOCK_OBJECT_OFF_TABLE
        if self.approach_angle_offset_deg > 0.0:
            return FailureMode.APPROACH_MISS
        if self.gripper_close_prematurely:
            return FailureMode.APPROACH_MISS
        if self.grip_force_scale < 0.7:
            return FailureMode.SLIP_DURING_LIFT
        return FailureMode.NONE


@dataclass
class _State:
    phase: _Phase = _Phase.APPROACH
    grasp_step_counter: int = 0
    initial_cube_pos: np.ndarray[Any, Any] | None = field(default=None)


class ScriptedLiftPolicy(Policy):
    """4-phase pick-and-lift state machine: approach -> descend -> grasp -> lift.

    The policy reads cube_pos and robot0_eef_pos from the obs dict each step
    and emits a 7-dim OSC_POSE+gripper action. All failure injections are
    applied AFTER the nominal action is computed, so the labeling stays
    invariant of the state machine internals.
    """

    def __init__(self, failures: InjectedFailures, seed: int = 0) -> None:
        self._failures = failures
        self._seed = seed
        self._state = _State()
        self._rng = np.random.default_rng(seed)

    @property
    def injected_label(self) -> FailureMode:
        return self._failures.to_label()

    def reset(self) -> None:
        self._state = _State()
        self._rng = np.random.default_rng(self._seed)

    def act(self, obs: dict[str, Any]) -> np.ndarray[Any, Any]:
        eef = np.asarray(obs[EEF_KEY], dtype=np.float64)
        cube = np.asarray(obs[CUBE_KEY], dtype=np.float64)
        gripper_qpos = np.asarray(obs[GRIPPER_QPOS_KEY], dtype=np.float64)

        if self._state.initial_cube_pos is None:
            self._state.initial_cube_pos = cube.copy()

        target_pos, gripper_cmd = self._compute_target(eef, cube, gripper_qpos)

        # Position command: P-controller toward target, capped at one-step delta.
        pos_error = target_pos - eef
        pos_input = np.clip(pos_error / POS_DELTA_MAX_M, -1.0, 1.0)

        # 7-dim OSC_POSE: [dx, dy, dz, drx, dry, drz, gripper]
        action = np.zeros(7, dtype=np.float32)
        action[:3] = pos_input
        action[6] = gripper_cmd * self._failures.grip_force_scale

        if self._failures.action_noise > 0.0:
            action[:6] += self._rng.normal(0.0, self._failures.action_noise, size=6).astype(
                np.float32
            )
            action = np.clip(action, -1.0, 1.0)

        return action

    def _compute_target(
        self,
        eef: np.ndarray[Any, Any],
        cube: np.ndarray[Any, Any],
        gripper_qpos: np.ndarray[Any, Any],
    ) -> tuple[np.ndarray[Any, Any], float]:
        s = self._state
        approach_xy = self._approach_xy_offset()

        # The xy offset persists through DESCEND/GRASP — the policy thinks the
        # cube is at cube+offset and never corrects. Without this, an
        # approach_angle_offset would be cosmetic (DESCEND would re-target
        # cube center and the gripper would still grasp).
        xy_off = np.array([approach_xy[0], approach_xy[1]])

        if s.phase == _Phase.APPROACH:
            target = cube + np.array([xy_off[0], xy_off[1], APPROACH_HEIGHT_M])
            grip = GRIP_CLOSE if self._failures.gripper_close_prematurely else GRIP_OPEN
            if np.linalg.norm(target - eef) < POS_TOLERANCE_M:
                s.phase = _Phase.DESCEND
            return target, grip

        if s.phase == _Phase.DESCEND:
            target = cube + np.array([xy_off[0], xy_off[1], GRASP_HEIGHT_OFFSET_M])
            grip = GRIP_CLOSE if self._failures.gripper_close_prematurely else GRIP_OPEN
            if eef[2] - cube[2] < 0.02:
                s.phase = _Phase.GRASP
            return target, grip

        if s.phase == _Phase.GRASP:
            target = cube + np.array([xy_off[0], xy_off[1], GRASP_HEIGHT_OFFSET_M])
            s.grasp_step_counter += 1
            if s.grasp_step_counter >= GRASP_HOLD_STEPS:
                s.phase = _Phase.LIFT
            return target, GRIP_CLOSE

        # LIFT or DONE
        assert s.initial_cube_pos is not None
        target = s.initial_cube_pos + np.array([xy_off[0], xy_off[1], LIFT_HEIGHT_M])
        return target, GRIP_CLOSE

    def _approach_xy_offset(self) -> tuple[float, float]:
        if self._failures.approach_angle_offset_deg == 0.0:
            return 0.0, 0.0
        # Fixed 6 cm radial offset rotated by the requested angle. 6 cm is wider
        # than the Lift cube (4 cm) plus half the open gripper aperture, so the
        # gripper tips clear the cube entirely and the grasp closes on air.
        radius = 0.06
        theta = radians(self._failures.approach_angle_offset_deg)
        return radius * cos(theta), radius * sin(theta)
