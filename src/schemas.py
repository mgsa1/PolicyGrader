"""Pydantic models that cross module boundaries.

CLAUDE.md sec 8: "Schemas at boundaries. Every cross-module function takes and
returns Pydantic models. No dicts across module boundaries." This file is the
canonical source of those types.

Core models:
  RolloutConfig    - one row of the test matrix; what to run
  RolloutResult    - what came back (no GT attached — GT comes from humans now)
  FrameObservation - one line of the judge's per-frame chain of thought
  JudgeAnnotation  - single-call judge output (label + frame + optional point + CoT)
  Finding          - one row of findings.jsonl: sim success + optional annotation
  HumanLabel       - one row of human_labels.jsonl: the calibration GT source
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.sim.scripted import FailureMode, InjectedFailures

PolicyKind = Literal["pretrained", "scripted"]
EnvName = Literal["Lift"]

# The human labeler's extended label set: every taxonomy failure mode plus
# `none` (clean success) and `ambiguous` (can't tell from the video). The
# judge's label set stays narrower (see JudgeAnnotation._label_not_none).
HumanLabelValue = Literal[
    "none",
    "approach_miss",
    "gripper_never_opened",
    "cube_scratched_but_not_moved",
    "premature_release",
    "slip_during_lift",
    "knock_object_off_table",
    "gripper_collision",
    "wrong_object_selected",
    "insertion_misalignment",
    "other",
    "ambiguous",
]


class RenderConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    camera: str = "frontview"
    width: int = 512
    height: int = 512
    fps: int = 20


class RolloutConfig(BaseModel):
    """One scenario to execute. Planner emits these; adapter consumes them.

    `injected_failures` is required for scripted rollouts and must be None
    for pretrained ones. The knobs drive the scripted policy's behavior but
    no longer carry ground truth — ground truth for the calibration cohort
    comes from human labels on a sampled subset (see src/human_labels.py).

    `cube_xy_jitter_m` widens the Lift env's cube placement range beyond its
    ~3 cm training distribution — the deployment-stress lever for the BC-RNN.
    0.0 means "use robosuite's default range"; positive values push the cube
    to positions the policy never saw at training time. Scripted rollouts
    always use 0.0.
    """

    model_config = ConfigDict(frozen=True)

    rollout_id: str = Field(..., min_length=1)
    policy_kind: PolicyKind
    env_name: EnvName
    seed: int = 0
    max_steps: int = Field(default=400, gt=0)
    render: RenderConfig = Field(default_factory=RenderConfig)

    injected_failures: InjectedFailures | None = None
    checkpoint_path: Path | None = None
    cube_xy_jitter_m: float = Field(default=0.0, ge=0.0)

    @model_validator(mode="after")
    def _check_policy_invariants(self) -> RolloutConfig:
        if self.policy_kind == "scripted":
            if self.injected_failures is None:
                raise ValueError(
                    "scripted rollout requires injected_failures (use default for clean)"
                )
            if self.checkpoint_path is not None:
                raise ValueError("scripted rollout must not carry a checkpoint_path")
        else:  # pretrained
            if self.checkpoint_path is None:
                raise ValueError("pretrained rollout requires checkpoint_path")
            if self.injected_failures is not None:
                raise ValueError("pretrained rollout must not carry injected_failures")
        return self


class RolloutResult(BaseModel):
    """Outcome of one scenario. The adapter writes this; the judge reads it.

    No ground_truth_label field: scripted rollouts used to derive GT from
    their InjectedFailures knobs, but knob-intent and visual-outcome
    disagreed too often (noise=0.10 labeled as knock but visually an
    approach_miss, etc.). Ground truth now comes from human labels on a
    sampled subset; see src/human_labels.py.

    `telemetry_path` points at the per-step sim-telemetry sidecar written next
    to the mp4. Optional: replays of pre-telemetry artifacts (or runs with
    `video_out=None`) leave it None and the judge falls back to vision-only.
    """

    model_config = ConfigDict(frozen=True)

    rollout_id: str
    success: bool
    steps_taken: int = Field(..., ge=0)
    video_path: Path | None
    env_name: EnvName
    policy_kind: PolicyKind
    seed: int
    telemetry_path: Path | None = None


# ---- Sim telemetry (per-step scalars fed to the judge as text evidence) -------


class TelemetryRow(BaseModel):
    """One row of per-step sim telemetry.

    Each scalar attacks a specific failure-mode confusion the vision-only judge
    has historically struggled with (gripper aperture for closing-vs-closed,
    contact_flag for touching-vs-grasped, cube xy/z drift for knock vs slip).
    Telemetry is evidence — the judge still emits the label from pixels.
    """

    model_config = ConfigDict(frozen=True)

    step_index: int = Field(..., ge=0)
    gripper_aperture: float = Field(..., ge=0.0, le=1.0)
    ee_to_cube_m: float = Field(..., ge=0.0)
    cube_z_above_table_m: float
    cube_xy_drift_m: float = Field(..., ge=0.0)
    contact_flag: bool


class RolloutTelemetry(BaseModel):
    """All per-step telemetry rows for one rollout. Written to <id>.telemetry.json."""

    model_config = ConfigDict(frozen=True)

    rollout_id: str = Field(..., min_length=1)
    fps: int = Field(..., gt=0)
    rows: list[TelemetryRow]


# ---- Judge output (single-call CoT pass; see src/vision/judge.py) -------------


GripperState = Literal["open", "closing", "closed", "opening"]
CubeState = Literal[
    "still_on_table",
    "moving_on_table",
    "in_gripper",
    "falling",
    "off_table",
]
ContactState = Literal["none", "touching_cube", "grasped"]


class FrameObservation(BaseModel):
    """One row of the judge's explicit per-frame chain of thought.

    The judge emits one of these per frame it was shown, in chronological order.
    Forcing this structured walkthrough before the final label is what keeps the
    judge from defaulting to approach_miss when it sees an empty-gripper
    consequence frame.
    """

    model_config = ConfigDict(frozen=True)

    frame_index: int = Field(..., ge=0)
    gripper_state: GripperState
    cube_state: CubeState
    contact: ContactState


class JudgeAnnotation(BaseModel):
    """Single-call judge output for one failed rollout.

    `frame_index` is in the ORIGINAL mp4's frame indexing — the judge module
    converts from its sampled-frame indexing before returning, so downstream
    consumers (keyframe rendering, UI) can index the raw video directly.

    `point` is (x, y) in the 2576-px long-edge grid of the chosen frame, OR
    None when no gripper-cube contact is visible (e.g. approach_miss,
    gripper_collision). `None` is a first-class output: a wrong pixel is
    strictly worse than an abstention.
    """

    model_config = ConfigDict(frozen=True)

    taxonomy_label: FailureMode
    frame_index: int = Field(..., ge=0)
    point: tuple[int, int] | None = None
    description: str = Field(..., min_length=1)
    per_frame_observations: list[FrameObservation] = Field(default_factory=list)

    @model_validator(mode="after")
    def _label_not_none(self) -> JudgeAnnotation:
        if self.taxonomy_label == FailureMode.NONE:
            raise ValueError(
                "JudgeAnnotation must not use FailureMode.NONE — the judge only "
                "runs on sim-confirmed failures; successes skip the judge entirely"
            )
        return self


class Finding(BaseModel):
    """One row of /memories/findings.jsonl: judge's output for one rollout.

    Binary success comes from the simulator (`env._check_success()`), not from
    vision. The judge only runs on sim failures, so `annotation` is non-None
    exactly when `sim_success` is False (and the judge has finished).
    """

    model_config = ConfigDict(frozen=True)

    rollout_id: str
    sim_success: bool
    annotation: JudgeAnnotation | None = None

    @model_validator(mode="after")
    def _annotation_only_on_failure(self) -> Finding:
        if self.sim_success and self.annotation is not None:
            raise ValueError("annotation must be None when sim_success=True")
        return self


class HumanLabel(BaseModel):
    """One row of mirror_root/human_labels.jsonl: the calibration GT source.

    The human labeler picks one value from HumanLabelValue per sampled
    rollout. `ambiguous` is a first-class output — rollouts tagged ambiguous
    contribute to coverage tracking but not to per-label precision/recall.
    `none` is the human's "this was a clean success, no failure to classify"
    vote; the judge never emits it (sim owns the success bit).
    """

    model_config = ConfigDict(frozen=True)

    rollout_id: str = Field(..., min_length=1)
    label: HumanLabelValue
    note: str | None = None
    labeled_at: datetime
