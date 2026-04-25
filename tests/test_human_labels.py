"""Tests for src/human_labels.py — sampling, persistence, resume."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from src.human_labels import (
    DEFAULT_CAP,
    DEFAULT_FLOOR,
    append_label,
    labels_by_rollout,
    pending_rollouts,
    read_labels,
    sample_for_labeling,
    submit_label,
)
from src.schemas import HumanLabel


class TestSampleForLabeling:
    """Sampling must be scripted-only, stratified, deterministic, and resilient
    when a stratum is short."""

    def test_empty_candidates_returns_empty(self) -> None:
        assert sample_for_labeling([]) == []

    def test_deployment_only_returns_empty(self) -> None:
        # Pretrained (deployment) rollouts are never sampled — calibration is a
        # scripted-cohort story.
        candidates = [(f"deploy_{i}", i % 2 == 0, "pretrained") for i in range(10)]
        assert sample_for_labeling(candidates) == []

    def test_floor_applies_on_small_runs(self) -> None:
        # 10 scripted rollouts -> 10% = 1; floor -> 6.
        candidates = [
            (f"calib_{i}", i < 4, "scripted") for i in range(10)
        ]  # 4 successes, 6 failures
        picked = sample_for_labeling(candidates, seed=0)
        assert len(picked) == DEFAULT_FLOOR

    def test_cap_applies_on_large_runs(self) -> None:
        # 400 scripted rollouts -> 10% = 40; cap -> 20.
        candidates = [(f"calib_{i}", i % 3 == 0, "scripted") for i in range(400)]
        picked = sample_for_labeling(candidates, seed=0)
        assert len(picked) == DEFAULT_CAP

    def test_1_3_success_2_3_failure_stratification(self) -> None:
        # 100 scripted rollouts, plenty in each stratum -> expect 10 total,
        # ~3 successes + ~7 failures (1/3 vs 2/3).
        candidates = [
            (f"calib_{i}", i < 50, "scripted") for i in range(100)
        ]  # 50 success, 50 failure
        picked = sample_for_labeling(candidates, seed=0)
        n_success = sum(1 for rid in picked if int(rid.split("_")[1]) < 50)
        n_failure = len(picked) - n_success
        # Allow for rounding: 10 total / 1/3 = 3.33 -> round to 3.
        assert n_success == 3
        assert n_failure == 7

    def test_deterministic_with_same_seed(self) -> None:
        candidates = [(f"calib_{i}", i % 2 == 0, "scripted") for i in range(50)]
        a = sample_for_labeling(candidates, seed=42)
        b = sample_for_labeling(candidates, seed=42)
        assert a == b

    def test_different_seeds_give_different_samples(self) -> None:
        candidates = [(f"calib_{i}", i % 2 == 0, "scripted") for i in range(50)]
        a = sample_for_labeling(candidates, seed=1)
        b = sample_for_labeling(candidates, seed=2)
        assert a != b

    def test_rebalance_when_successes_are_short(self) -> None:
        # Only 1 success available but floor of 6 requested → fill from failures.
        candidates = [("calib_ok", True, "scripted")] + [
            (f"calib_fail_{i}", False, "scripted") for i in range(20)
        ]
        picked = sample_for_labeling(candidates, seed=0)
        assert len(picked) == DEFAULT_FLOOR
        assert "calib_ok" in picked  # the one success is included

    def test_rebalance_when_failures_are_short(self) -> None:
        # Only 2 failures available but target demands more → fill from successes.
        candidates = [(f"calib_ok_{i}", True, "scripted") for i in range(20)] + [
            ("calib_fail_0", False, "scripted"),
            ("calib_fail_1", False, "scripted"),
        ]
        picked = sample_for_labeling(candidates, seed=0)
        assert len(picked) == DEFAULT_FLOOR
        assert "calib_fail_0" in picked
        assert "calib_fail_1" in picked

    def test_mixed_cohort_only_scripted_picked(self) -> None:
        candidates = [
            ("calib_0", True, "scripted"),
            ("calib_1", False, "scripted"),
            ("calib_2", False, "scripted"),
            ("deploy_0", True, "pretrained"),
            ("deploy_1", False, "pretrained"),
        ]
        # Tiny scripted pool: 3 candidates, floor=6 but only 3 available.
        picked = sample_for_labeling(candidates, seed=0)
        assert all(rid.startswith("calib_") for rid in picked)
        assert len(picked) == 3


class TestPersistence:
    def test_append_and_read_roundtrip(self, tmp_path: Path) -> None:
        label = HumanLabel(
            rollout_id="calib_00",
            label="missed_approach",
            note="gripper closed on empty air",
            labeled_at=datetime.now(UTC),
        )
        append_label(tmp_path, label)
        records = read_labels(tmp_path)
        assert len(records) == 1
        assert records[0].rollout_id == "calib_00"
        assert records[0].label == "missed_approach"

    def test_missing_file_returns_empty(self, tmp_path: Path) -> None:
        assert read_labels(tmp_path) == []

    def test_submit_label_helper_writes_and_returns_record(self, tmp_path: Path) -> None:
        rec = submit_label(tmp_path, rollout_id="calib_07", label="failed_grip")
        assert rec.rollout_id == "calib_07"
        assert rec.label == "failed_grip"
        assert rec.note is None
        reloaded = read_labels(tmp_path)
        assert len(reloaded) == 1
        assert reloaded[0] == rec

    def test_last_write_wins_on_duplicate_rollout_id(self, tmp_path: Path) -> None:
        submit_label(tmp_path, rollout_id="calib_00", label="missed_approach")
        submit_label(tmp_path, rollout_id="calib_00", label="failed_grip")
        mapping = labels_by_rollout(tmp_path)
        assert mapping["calib_00"].label == "failed_grip"

    def test_malformed_lines_skipped(self, tmp_path: Path) -> None:
        # Pre-seed the file with one good record + two bad lines.
        path = tmp_path / "human_labels.jsonl"
        good = HumanLabel(
            rollout_id="calib_00",
            label="none",
            note=None,
            labeled_at=datetime.now(UTC),
        )
        path.write_text(
            good.model_dump_json()
            + "\n"
            + "not json\n"
            + '{"rollout_id": "calib_01"}\n'  # missing required fields
        )
        records = read_labels(tmp_path)
        assert len(records) == 1
        assert records[0].rollout_id == "calib_00"


class TestResume:
    def test_pending_rollouts_filters_already_labeled(self, tmp_path: Path) -> None:
        queue = ["calib_0", "calib_1", "calib_2", "calib_3"]
        submit_label(tmp_path, rollout_id="calib_0", label="none")
        submit_label(tmp_path, rollout_id="calib_2", label="missed_approach")
        pending = pending_rollouts(queue, tmp_path)
        assert pending == ["calib_1", "calib_3"]

    def test_pending_on_empty_file(self, tmp_path: Path) -> None:
        queue = ["calib_0", "calib_1"]
        assert pending_rollouts(queue, tmp_path) == queue


class TestLegacyLabelRemap:
    """Past runs' human_labels.jsonl files carry labels that no longer exist
    in the current taxonomy (e.g. `gripper_slipped`). They must be remapped
    on read so the UI renders against the current 2-mode set without needing
    to rewrite old artifacts."""

    def test_legacy_labels_remapped_on_read(self, tmp_path: Path) -> None:
        # Hand-write a human_labels.jsonl with three legacy labels + one
        # current-taxonomy label. Reading it back should remap the legacy
        # values while leaving the current ones alone.
        path = tmp_path / "human_labels.jsonl"
        lines = [
            '{"rollout_id": "r0", "label": "gripper_slipped",'
            ' "note": null, "labeled_at": "2026-04-01T00:00:00+00:00"}',
            '{"rollout_id": "r1", "label": "gripper_not_open",'
            ' "note": null, "labeled_at": "2026-04-01T00:00:00+00:00"}',
            '{"rollout_id": "r2", "label": "knock_object_off_table",'
            ' "note": null, "labeled_at": "2026-04-01T00:00:00+00:00"}',
            '{"rollout_id": "r3", "label": "missed_approach",'
            ' "note": null, "labeled_at": "2026-04-01T00:00:00+00:00"}',
        ]
        path.write_text("\n".join(lines) + "\n")

        mapping = labels_by_rollout(tmp_path)
        assert mapping["r0"].label == "failed_grip"
        assert mapping["r1"].label == "missed_approach"
        assert mapping["r2"].label == "missed_approach"
        assert mapping["r3"].label == "missed_approach"
