"""Pydantic models that cross module boundaries.

CLAUDE.md sec 8: "Schemas at boundaries. Every cross-module function takes and
returns Pydantic models. No dicts across module boundaries." This file is the
canonical source of those types.

Three core models:
  RolloutConfig  - one row of the test matrix; what to run
  RolloutResult  - what came back; carries ground-truth label for grading
  Finding        - vision judge output for one rollout (pass1 + optional pass2)
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.sim.scripted import FailureMode, InjectedFailures

PolicyKind = Literal["pretrained", "scripted"]
EnvName = Literal["Lift"]


class RenderConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    camera: str = "frontview"
    width: int = 512
    height: int = 512
    fps: int = 20


class RolloutConfig(BaseModel):
    """One scenario to execute. Planner emits these; adapter consumes them.

    `injected_failures` is required for scripted rollouts (it carries the
    ground-truth label) and must be None for pretrained ones.

    `cube_xy_jitter_m` widens the Lift env's cube placement range beyond its
    ~3 cm training distribution — the deployment-stress lever for the BC-RNN.
    0.0 means "use robosuite's default range"; positive values push the cube
    to positions the policy never saw at training time. Calibration rollouts
    should always use 0.0 so the scripted policy's behavior stays invariant
    across the injected-failure knobs.
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

    @property
    def ground_truth_label(self) -> FailureMode | None:
        """The label this rollout WILL be graded against. None for pretrained."""
        return self.injected_failures.to_label() if self.injected_failures is not None else None


class RolloutResult(BaseModel):
    """Outcome of one scenario. The adapter writes this; the judge reads it."""

    model_config = ConfigDict(frozen=True)

    rollout_id: str
    success: bool
    steps_taken: int = Field(..., ge=0)
    video_path: Path | None
    ground_truth_label: FailureMode | None
    env_name: EnvName
    policy_kind: PolicyKind
    seed: int


class Pass1Verdict(BaseModel):
    """Coarse vision pass: did the rollout succeed, and roughly when did it break?"""

    model_config = ConfigDict(frozen=True)

    verdict: Literal["pass", "fail"]
    failure_frame_range: tuple[int, int] | None = None

    @model_validator(mode="after")
    def _range_only_on_fail(self) -> Pass1Verdict:
        if self.verdict == "pass" and self.failure_frame_range is not None:
            raise ValueError("failure_frame_range must be None when verdict=='pass'")
        return self


class Pass2Annotation(BaseModel):
    """Fine vision pass: taxonomy label + 2576px point on the failure frame."""

    model_config = ConfigDict(frozen=True)

    taxonomy_label: FailureMode
    point: tuple[int, int]
    description: str = Field(..., min_length=1)


class Finding(BaseModel):
    """One row of /memories/findings.jsonl: judge's full output for one rollout."""

    model_config = ConfigDict(frozen=True)

    rollout_id: str
    pass1: Pass1Verdict
    pass2: Pass2Annotation | None = None

    @model_validator(mode="after")
    def _pass2_only_on_fail(self) -> Finding:
        if self.pass1.verdict == "pass" and self.pass2 is not None:
            raise ValueError("pass2 annotation must be None when pass1.verdict=='pass'")
        return self
