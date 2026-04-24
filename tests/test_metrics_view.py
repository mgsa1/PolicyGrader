"""Pure-arithmetic tests for src.ui.metrics_view. No Gradio, no plotly assertions."""

from __future__ import annotations

from src.sim.scripted import FailureMode
from src.ui.metrics_view import (
    EMPTY_FILTER,
    DrillFilter,
    cohort_counts,
    filter_rollouts,
    to_labeled_rollouts,
    wilson_ci_95,
)
from tests.test_synthesis import _scored


class TestCohortCounts:
    def test_empty(self) -> None:
        c = cohort_counts([])
        assert c.n_calibration == 0
        assert c.n_calibration_with_findings == 0
        assert c.n_deployment == 0

    def test_mixed(self) -> None:
        rollouts = [
            # Calibration success — judge doesn't run, but "scored" counts it.
            _scored("s0", success=True, judge_label=None, ground_truth_label="none"),
            # Calibration failure with judge complete.
            _scored(
                "s1",
                success=False,
                judge_label="approach_miss",
                ground_truth_label="approach_miss",
            ),
            # Deployment rollout (no ground_truth_label).
            _scored("p0", success=False, judge_label="approach_miss", policy_kind="pretrained"),
        ]
        c = cohort_counts(rollouts)
        assert c.n_calibration == 2  # s0, s1 have ground truth
        assert c.n_calibration_with_findings == 2  # both have a verdict
        assert c.n_deployment == 1  # p0

    def test_calibration_pending_judge(self) -> None:
        # Calibration failure but judge hasn't run → not yet scored.
        rollouts = [
            _scored("s0", success=False, judge_label=None, ground_truth_label="approach_miss"),
        ]
        c = cohort_counts(rollouts)
        assert c.n_calibration == 1
        assert c.n_calibration_with_findings == 0


class TestWilsonCI:
    def test_zero_n(self) -> None:
        lo, hi = wilson_ci_95(0, 0)
        assert lo == 0.0 and hi == 0.0

    def test_perfect_score_small_n(self) -> None:
        # 5/5 should give a wide upper-leaning interval, not 1.0±0.
        lo, hi = wilson_ci_95(5, 5)
        assert hi == 1.0
        assert lo < 0.7  # plenty of slack

    def test_half_p(self) -> None:
        # 5/10 → roughly [0.24, 0.76] for Wilson 95%.
        lo, hi = wilson_ci_95(5, 10)
        assert 0.20 < lo < 0.30
        assert 0.70 < hi < 0.80

    def test_large_n_tightens(self) -> None:
        # 50/100 → tighter bounds than 5/10.
        lo, hi = wilson_ci_95(50, 100)
        assert hi - lo < 0.20


class TestToLabeledRollouts:
    def test_skips_no_ground_truth(self) -> None:
        # Deployment rollouts have ground_truth_label=None and never get scored.
        rollouts = [_scored("p0", policy_kind="pretrained")]
        assert to_labeled_rollouts(rollouts) == []

    def test_skips_judge_pending(self) -> None:
        # Sim said fail but judge hasn't run — not yet scorable.
        rollouts = [
            _scored("s0", success=False, judge_label=None, ground_truth_label="approach_miss")
        ]
        assert to_labeled_rollouts(rollouts) == []

    def test_success_maps_to_none(self) -> None:
        # Sim success on a scripted rollout with expected="none" → implicit
        # judge verdict of FailureMode.NONE (judge doesn't run on successes).
        rollouts = [_scored("s0", success=True, judge_label=None, ground_truth_label="none")]
        labeled = to_labeled_rollouts(rollouts)
        assert len(labeled) == 1
        assert labeled[0].expected == FailureMode.NONE
        assert labeled[0].judged == FailureMode.NONE

    def test_judge_label_round_trip(self) -> None:
        # Sim fail + judge label → round-trip through FailureMode enum.
        rollouts = [
            _scored(
                "s0",
                success=False,
                judge_label="slip_during_lift",
                ground_truth_label="approach_miss",
            )
        ]
        labeled = to_labeled_rollouts(rollouts)
        assert labeled[0].expected == FailureMode.APPROACH_MISS
        assert labeled[0].judged == FailureMode.SLIP_DURING_LIFT


class TestDrillFilter:
    def test_empty_filter_inactive(self) -> None:
        assert not EMPTY_FILTER.is_active
        assert EMPTY_FILTER.label_text() == ""

    def test_cell_filter(self) -> None:
        f = DrillFilter(expected="approach_miss", judged="slip_during_lift")
        assert f.is_active
        assert "approach_miss" in f.label_text() and "slip_during_lift" in f.label_text()

    def test_row_filter_only_expected(self) -> None:
        f = DrillFilter(expected="approach_miss", judged=None)
        assert f.is_active
        assert "expected OR judged" in f.label_text()


class TestFilterRollouts:
    def test_no_filter_returns_empty(self) -> None:
        rollouts = [_scored("s0", ground_truth_label="approach_miss")]
        assert filter_rollouts(rollouts, EMPTY_FILTER) == []

    def test_cell_filter_strict(self) -> None:
        rollouts = [
            _scored(
                "a",
                success=False,
                judge_label="approach_miss",
                ground_truth_label="approach_miss",
            ),
            _scored(
                "b",
                success=False,
                judge_label="approach_miss",
                ground_truth_label="slip_during_lift",
            ),  # mismatch
        ]
        f = DrillFilter(expected="approach_miss", judged="approach_miss")
        out = filter_rollouts(rollouts, f)
        assert [r.rollout_id for r in out] == ["a"]

    def test_row_filter_loose(self) -> None:
        rollouts = [
            _scored(
                "a",
                success=False,
                judge_label="approach_miss",
                ground_truth_label="approach_miss",
            ),
            _scored(
                "b",
                success=False,
                judge_label="approach_miss",
                ground_truth_label="slip_during_lift",
            ),
            _scored("c", success=True, judge_label=None, ground_truth_label="none"),
        ]
        f = DrillFilter(expected="approach_miss", judged=None)
        out = sorted(r.rollout_id for r in filter_rollouts(rollouts, f))
        # Both a (matches) and b (judged as approach_miss) should appear.
        assert out == ["a", "b"]
