"""Tests for src.schemas: RolloutConfig invariants, Finding sim_success/annotation coupling.

These pin down the validators that protect downstream consumers from malformed
configs (e.g. a "scripted" rollout missing its injected-failures payload, which
would silently lose its ground-truth label).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.schemas import (
    Finding,
    JudgeAnnotation,
    RenderConfig,
    RolloutConfig,
    RolloutResult,
    RolloutTelemetry,
    TelemetryRow,
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
        assert cfg.rollout_id == "r1"
        assert cfg.injected_failures == InjectedFailures()

    def test_scripted_with_injected_failure(self) -> None:
        cfg = RolloutConfig(
            rollout_id="r2",
            policy_kind="scripted",
            env_name="Lift",
            injected_failures=InjectedFailures(grip_force_scale=0.3),
        )
        assert cfg.injected_failures is not None
        assert cfg.injected_failures.grip_force_scale == 0.3

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
            env_name="Lift",
            checkpoint_path=Path("/tmp/x.pth"),
        )
        assert cfg.injected_failures is None
        assert cfg.cube_xy_jitter_m == 0.0

    def test_pretrained_with_cube_jitter(self) -> None:
        cfg = RolloutConfig(
            rollout_id="r5a",
            policy_kind="pretrained",
            env_name="Lift",
            checkpoint_path=Path("/tmp/x.pth"),
            cube_xy_jitter_m=0.08,
        )
        assert cfg.cube_xy_jitter_m == 0.08

    def test_negative_cube_jitter_rejected(self) -> None:
        with pytest.raises(ValueError):
            RolloutConfig(
                rollout_id="r5b",
                policy_kind="pretrained",
                env_name="Lift",
                checkpoint_path=Path("/tmp/x.pth"),
                cube_xy_jitter_m=-0.01,
            )

    def test_pretrained_missing_checkpoint_rejected(self) -> None:
        with pytest.raises(ValueError, match="checkpoint_path"):
            RolloutConfig(rollout_id="r6", policy_kind="pretrained", env_name="Lift")

    def test_pretrained_with_failures_rejected(self) -> None:
        with pytest.raises(ValueError, match="injected_failures"):
            RolloutConfig(
                rollout_id="r7",
                policy_kind="pretrained",
                env_name="Lift",
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
                env_name="Lift",
                policy_kind="scripted",
                seed=0,
            )


class TestFinding:
    def test_success_without_annotation(self) -> None:
        f = Finding(rollout_id="r1", sim_success=True)
        assert f.annotation is None

    def test_success_with_annotation_rejected(self) -> None:
        with pytest.raises(ValueError, match="annotation"):
            Finding(
                rollout_id="r1",
                sim_success=True,
                annotation=JudgeAnnotation(
                    taxonomy_label=FailureMode.APPROACH_MISS,
                    frame_index=42,
                    point=(100, 200),
                    description="x",
                ),
            )

    def test_failure_with_annotation(self) -> None:
        f = Finding(
            rollout_id="r1",
            sim_success=False,
            annotation=JudgeAnnotation(
                taxonomy_label=FailureMode.SLIP_DURING_LIFT,
                frame_index=70,
                point=(123, 456),
                description="cube slips at frame 70",
            ),
        )
        assert f.annotation is not None
        assert f.annotation.point == (123, 456)
        assert f.annotation.frame_index == 70

    def test_failure_without_point_is_valid(self) -> None:
        """approach_miss / gripper_collision failures have no gripper-cube contact,
        so the judge may legitimately return point=None. Confirm the schema allows it."""
        f = Finding(
            rollout_id="r2",
            sim_success=False,
            annotation=JudgeAnnotation(
                taxonomy_label=FailureMode.APPROACH_MISS,
                frame_index=30,
                point=None,
                description="gripper closes on empty air",
            ),
        )
        assert f.annotation is not None
        assert f.annotation.point is None

    def test_annotation_rejects_none_label(self) -> None:
        """JudgeAnnotation must never use FailureMode.NONE — the judge only runs
        on sim-confirmed failures, so "no failure" is nonsensical here."""
        with pytest.raises(ValueError, match="FailureMode.NONE"):
            JudgeAnnotation(
                taxonomy_label=FailureMode.NONE,
                frame_index=0,
                point=None,
                description="should be rejected",
            )


class TestRenderConfig:
    def test_defaults(self) -> None:
        r = RenderConfig()
        assert r.camera == "frontview"
        assert (r.width, r.height) == (512, 512)
        assert r.fps == 20


class TestTelemetry:
    def test_round_trip(self) -> None:
        tel = RolloutTelemetry(
            rollout_id="r1",
            fps=20,
            rows=[
                TelemetryRow(
                    step_index=0,
                    gripper_aperture=1.0,
                    ee_to_cube_m=0.18,
                    cube_z_above_table_m=0.0,
                    cube_xy_drift_m=0.0,
                    contact_flag=False,
                ),
                TelemetryRow(
                    step_index=1,
                    gripper_aperture=0.4,
                    ee_to_cube_m=0.01,
                    cube_z_above_table_m=0.001,
                    cube_xy_drift_m=0.018,
                    contact_flag=True,
                ),
            ],
        )
        clone = RolloutTelemetry.model_validate_json(tel.model_dump_json())
        assert clone == tel
        assert clone.rows[1].contact_flag is True

    def test_aperture_out_of_range_rejected(self) -> None:
        with pytest.raises(ValueError):
            TelemetryRow(
                step_index=0,
                gripper_aperture=1.2,
                ee_to_cube_m=0.0,
                cube_z_above_table_m=0.0,
                cube_xy_drift_m=0.0,
                contact_flag=False,
            )

    def test_negative_distance_rejected(self) -> None:
        with pytest.raises(ValueError):
            TelemetryRow(
                step_index=0,
                gripper_aperture=0.5,
                ee_to_cube_m=-0.01,
                cube_z_above_table_m=0.0,
                cube_xy_drift_m=0.0,
                contact_flag=False,
            )

    def test_result_telemetry_path_optional(self, tmp_path: Path) -> None:
        r = RolloutResult(
            rollout_id="r1",
            success=False,
            steps_taken=10,
            video_path=tmp_path / "x.mp4",
            env_name="Lift",
            policy_kind="scripted",
            seed=0,
            telemetry_path=tmp_path / "x.telemetry.json",
        )
        assert r.telemetry_path == tmp_path / "x.telemetry.json"

    def test_result_telemetry_path_defaults_none(self, tmp_path: Path) -> None:
        r = RolloutResult(
            rollout_id="r1",
            success=False,
            steps_taken=10,
            video_path=tmp_path / "x.mp4",
            env_name="Lift",
            policy_kind="scripted",
            seed=0,
        )
        assert r.telemetry_path is None
