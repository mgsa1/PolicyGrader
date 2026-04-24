"""Scripted state-machine pick policy for robosuite Lift, with injectable failure modes.

Drives the calibration cohort of every eval. The deployment cohort uses the
pretrained BC-RNN on the same task under cube-placement perturbations.

The knobs control WHAT the scripted policy does, not WHAT the rollout will be
labeled as: ground truth comes from human labels on a sampled subset of
rollouts (see src/human_labels.py), because knob-intent and visual-outcome
diverged too often under the old knob->label mapping (e.g. action_noise=0.10
was labeled knock_object_off_table but visually produced approach_miss on
many seeds).

Knob menu:
  action_noise            gaussian perturbation on action[:6] every step
                          (amplified by NOISE_GAIN). High values chaotic.
  approach_angle_offset   radial xy offset of target during approach+descent
                          — gripper closes beside the cube.
  gripper_close_prematurely  gripper commanded closed from step 0 — fingers
                          never open, cannot grasp.
  grip_force_scale        < SLIP_THRESHOLD -> gripper opens mid-lift after
                          SLIP_CARRY_STEPS; cube falls visibly.
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

# Slip threshold: weak grip -> gripper releases mid-lift.
SLIP_THRESHOLD = 0.7

# During slip, hold the grasp with GRIP_CLOSE for this many LIFT-phase steps
# so the arm has time to actually raise the cube to ~LIFT_HEIGHT_M before we
# command GRIP_OPEN. Without the hold the gripper released before the lift
# started and the cube never left the table — visually indistinguishable
# from approach_miss. With it, the cube is clearly airborne when released
# and falls back, producing the canonical slip silhouette.
SLIP_CARRY_STEPS = 15

# Internal multiplier on action_noise so the user-facing values from claude.md
# sec 4 ({0.0, 0.05, 0.15}) actually translate to visible behavior on Lift.
# OSC_POSE input range [-1, +1] maps to ±5 cm/step; without the gain, std=0.15
# -> ±7.5 mm/step jitter, which the P-controller absorbs every step. With
# gain=8, std=0.15 -> ±60 mm/step, large enough to push the gripper into the
# cube and knock it off the table within the first few approach steps.
NOISE_GAIN = 8.0


class FailureMode(StrEnum):
    """Visually-distinct failure modes the judge emits on Lift.

    Collapsed from the previous 10-label taxonomy: the fine-grained
    distinctions (scratch vs knock vs approach_miss; slip vs premature_release)
    were below the pixel+frame-rate resolution of the judge and were the main
    driver of multiclass confusion. The new axis is OUTCOME, not mechanism.
    """

    NONE = "none"
    # Policy never secured the cube — fingers close on empty air, or graze /
    # knock the cube without grasping it. Subsumes the old approach_miss,
    # knock_object_off_table, cube_scratched_but_not_moved, gripper_collision.
    MISSED_APPROACH = "missed_approach"
    # Policy secured the cube but lost it during the lift — fingers opening
    # mid-lift OR the cube sliding out of a weak grip. Subsumes the old
    # slip_during_lift and premature_release.
    GRIPPER_SLIPPED = "gripper_slipped"
    # Fingers were closed when they should have been open — hand arrives at the
    # cube already pinched shut and cannot grasp. Was gripper_never_opened.
    GRIPPER_NOT_OPEN = "gripper_not_open"
    OTHER = "other"


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


@dataclass
class _State:
    phase: _Phase = _Phase.APPROACH
    grasp_step_counter: int = 0
    lift_step_counter: int = 0
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
        action[6] = self._gripper_action(gripper_cmd)

        if self._failures.action_noise > 0.0:
            # Amplified by NOISE_GAIN: raw action_noise=0.15 maps to per-step pose
            # perturbations of std=0.6 in input units = ~30 mm/step on the position
            # axes — chaotic enough to actually knock the cube, not just jitter.
            action[:6] += self._rng.normal(
                0.0, self._failures.action_noise * NOISE_GAIN, size=6
            ).astype(np.float32)
            action = np.clip(action, -1.0, 1.0)

        return action

    def _gripper_action(self, nominal_cmd: float) -> float:
        """Slip semantic: carry the cube through the first SLIP_CARRY_STEPS of
        LIFT with GRIP_CLOSE so it is clearly airborne, then command GRIP_OPEN
        so it falls. Binary release on threshold drops the cube reliably —
        continuous interpolation (e.g. 2*scale-1) grasped about half the time
        across cube-placement seeds and made the mode visually ambiguous.
        """
        if self._state.phase != _Phase.LIFT:
            return nominal_cmd
        if (
            self._failures.grip_force_scale < SLIP_THRESHOLD
            and self._state.lift_step_counter >= SLIP_CARRY_STEPS
        ):
            return GRIP_OPEN
        return nominal_cmd

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

        s.lift_step_counter += 1
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
