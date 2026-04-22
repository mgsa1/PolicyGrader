"""Tests for src.schemas: RolloutConfig invariants, Finding pass1/pass2 coupling.

These pin down the validators that protect downstream consumers from malformed
configs (e.g. a "scripted" rollout missing its injected-failures payload, which
would silently lose its ground-truth label).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.schemas import (
    Finding,
    Pass1Verdict,
    Pass2Annotation,
    RenderConfig,
    RolloutConfig,
    RolloutResult,
)
from src.sim.scripted import FailureMode, InjectedFailures


class TestRolloutConfig:
    def test_scripted_clean_round_trip(self) -> None:
        cfg = RolloutConfig(
            rollout_id="r1",
            policy_kind="scripted",
            env_name="Lift",
            injected_failures=InjectedFailures(),
        )
        assert cfg.ground_truth_label == FailureMode.NONE

    def test_scripted_with_injected_failure_label(self) -> None:
        cfg = RolloutConfig(
            rollout_id="r2",
            policy_kind="scripted",
            env_name="Lift",
            injected_failures=InjectedFailures(grip_force_scale=0.3),
        )
        assert cfg.ground_truth_label == FailureMode.SLIP_DURING_LIFT

    def test_scripted_missing_failures_rejected(self) -> None:
        with pytest.raises(ValueError, match="injected_failures"):
            RolloutConfig(rollout_id="r3", policy_kind="scripted", env_name="Lift")

    def test_scripted_with_checkpoint_rejected(self) -> None:
        with pytest.raises(ValueError, match="checkpoint_path"):
            RolloutConfig(
                rollout_id="r4",
                policy_kind="scripted",
                env_name="Lift",
                injected_failures=InjectedFailures(),
                checkpoint_path=Path("/tmp/x.pth"),
            )

    def test_pretrained_round_trip(self) -> None:
        cfg = RolloutConfig(
            rollout_id="r5",
            policy_kind="pretrained",
            env_name="NutAssemblySquare",
            checkpoint_path=Path("/tmp/x.pth"),
        )
        assert cfg.ground_truth_label is None

    def test_pretrained_missing_checkpoint_rejected(self) -> None:
        with pytest.raises(ValueError, match="checkpoint_path"):
            RolloutConfig(rollout_id="r6", policy_kind="pretrained", env_name="NutAssemblySquare")

    def test_pretrained_with_failures_rejected(self) -> None:
        with pytest.raises(ValueError, match="injected_failures"):
            RolloutConfig(
                rollout_id="r7",
                policy_kind="pretrained",
                env_name="NutAssemblySquare",
                checkpoint_path=Path("/tmp/x.pth"),
                injected_failures=InjectedFailures(),
            )

    def test_max_steps_must_be_positive(self) -> None:
        with pytest.raises(ValueError):
            RolloutConfig(
                rollout_id="r8",
                policy_kind="scripted",
                env_name="Lift",
                injected_failures=InjectedFailures(),
                max_steps=0,
            )

    def test_frozen(self) -> None:
        cfg = RolloutConfig(
            rollout_id="r9",
            policy_kind="scripted",
            env_name="Lift",
            injected_failures=InjectedFailures(),
        )
        with pytest.raises(ValueError):
            cfg.seed = 1  # type: ignore[misc]


class TestRolloutResult:
    def test_basic(self) -> None:
        r = RolloutResult(
            rollout_id="r1",
            success=True,
            steps_taken=42,
            video_path=Path("artifacts/x.mp4"),
            ground_truth_label=FailureMode.NONE,
            env_name="Lift",
            policy_kind="scripted",
            seed=0,
        )
        assert r.success is True
        assert r.steps_taken == 42

    def test_negative_steps_rejected(self) -> None:
        with pytest.raises(ValueError):
            RolloutResult(
                rollout_id="r1",
                success=False,
                steps_taken=-1,
                video_path=None,
                ground_truth_label=None,
                env_name="Lift",
                policy_kind="scripted",
                seed=0,
            )


class TestFinding:
    def test_pass_with_no_pass2(self) -> None:
        f = Finding(rollout_id="r1", pass1=Pass1Verdict(verdict="pass"))
        assert f.pass2 is None

    def test_pass_with_pass2_rejected(self) -> None:
        with pytest.raises(ValueError, match="pass2"):
            Finding(
                rollout_id="r1",
                pass1=Pass1Verdict(verdict="pass"),
                pass2=Pass2Annotation(
                    taxonomy_label=FailureMode.APPROACH_MISS, point=(100, 200), description="x"
                ),
            )

    def test_pass1_range_only_on_fail(self) -> None:
        with pytest.raises(ValueError, match="failure_frame_range"):
            Pass1Verdict(verdict="pass", failure_frame_range=(10, 20))

    def test_fail_with_pass2(self) -> None:
        f = Finding(
            rollout_id="r1",
            pass1=Pass1Verdict(verdict="fail", failure_frame_range=(50, 80)),
            pass2=Pass2Annotation(
                taxonomy_label=FailureMode.SLIP_DURING_LIFT,
                point=(123, 456),
                description="cube slips at frame 70",
            ),
        )
        assert f.pass2 is not None
        assert f.pass2.point == (123, 456)


class TestRenderConfig:
    def test_defaults(self) -> None:
        r = RenderConfig()
        assert r.camera == "frontview"
        assert (r.width, r.height) == (512, 512)
        assert r.fps == 20
