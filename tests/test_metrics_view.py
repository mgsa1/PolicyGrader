"""Pure-arithmetic tests for src.ui.metrics_view. No Gradio, no plotly assertions."""

from __future__ import annotations

from src.sim.scripted import FailureMode
from src.ui.metrics_view import (
    EMPTY_FILTER,
    DrillFilter,
    binary_confusion,
    cohort_counts,
    filter_rollouts,
    render_binary_matrix,
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
                judge_label="missed_approach",
                ground_truth_label="missed_approach",
            ),
            # Deployment rollout (no ground_truth_label).
            _scored("p0", success=False, judge_label="missed_approach", policy_kind="pretrained"),
        ]
        c = cohort_counts(rollouts)
        assert c.n_calibration == 2  # s0, s1 have ground truth
        assert c.n_calibration_with_findings == 2  # both have a verdict
        assert c.n_deployment == 1  # p0

    def test_calibration_pending_judge(self) -> None:
        # Calibration failure but judge hasn't run → not yet scored.
        rollouts = [
            _scored("s0", success=False, judge_label=None, ground_truth_label="missed_approach"),
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
            _scored("s0", success=False, judge_label=None, ground_truth_label="missed_approach")
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
                judge_label="gripper_slipped",
                ground_truth_label="missed_approach",
            )
        ]
        labeled = to_labeled_rollouts(rollouts)
        assert labeled[0].expected == FailureMode.MISSED_APPROACH
        assert labeled[0].judged == FailureMode.GRIPPER_SLIPPED


class TestDrillFilter:
    def test_empty_filter_inactive(self) -> None:
        assert not EMPTY_FILTER.is_active
        assert EMPTY_FILTER.label_text() == ""

    def test_cell_filter(self) -> None:
        f = DrillFilter(expected="missed_approach", judged="gripper_slipped")
        assert f.is_active
        assert "missed_approach" in f.label_text() and "gripper_slipped" in f.label_text()

    def test_row_filter_only_expected(self) -> None:
        f = DrillFilter(expected="missed_approach", judged=None)
        assert f.is_active
        assert "expected OR judged" in f.label_text()


class TestFilterRollouts:
    def test_no_filter_returns_empty(self) -> None:
        rollouts = [_scored("s0", ground_truth_label="missed_approach")]
        assert filter_rollouts(rollouts, EMPTY_FILTER) == []

    def test_cell_filter_strict(self) -> None:
        rollouts = [
            _scored(
                "a",
                success=False,
                judge_label="missed_approach",
                ground_truth_label="missed_approach",
            ),
            _scored(
                "b",
                success=False,
                judge_label="missed_approach",
                ground_truth_label="gripper_slipped",
            ),  # mismatch
        ]
        f = DrillFilter(expected="missed_approach", judged="missed_approach")
        out = filter_rollouts(rollouts, f)
        assert [r.rollout_id for r in out] == ["a"]

    def test_row_filter_loose(self) -> None:
        rollouts = [
            _scored(
                "a",
                success=False,
                judge_label="missed_approach",
                ground_truth_label="missed_approach",
            ),
            _scored(
                "b",
                success=False,
                judge_label="missed_approach",
                ground_truth_label="gripper_slipped",
            ),
            _scored("c", success=True, judge_label=None, ground_truth_label="none"),
        ]
        f = DrillFilter(expected="missed_approach", judged=None)
        out = sorted(r.rollout_id for r in filter_rollouts(rollouts, f))
        # Both a (matches) and b (judged as missed_approach) should appear.
        assert out == ["a", "b"]


class TestBinaryConfusion:
    def test_empty(self) -> None:
        c = binary_confusion([])
        assert (c.tn, c.fp, c.fn, c.tp, c.total) == (0, 0, 0, 0, 0)

    def test_tp_and_tn(self) -> None:
        # Sim-success with no judge label → TN. Sim-failure with any failure
        # label → TP. Both populations (calibration + deployment) count.
        rollouts = [
            _scored("a", success=True, judge_label=None, ground_truth_label="none"),
            _scored("b", success=True, judge_label=None, policy_kind="pretrained"),
            _scored(
                "c",
                success=False,
                judge_label="gripper_slipped",
                ground_truth_label="gripper_slipped",
            ),
            _scored("d", success=False, judge_label="missed_approach", policy_kind="pretrained"),
        ]
        c = binary_confusion(rollouts)
        assert (c.tn, c.fp, c.fn, c.tp) == (2, 0, 0, 2)

    def test_fn_and_fp(self) -> None:
        # FN: sim-failure but judge says "none". FP: sim-success but judge
        # returned a failure label (shouldn't normally happen under the new
        # single-pass design, but must still be counted if the data says so).
        rollouts = [
            _scored("a", success=False, judge_label="none", ground_truth_label="missed_approach"),
            _scored("b", success=True, judge_label="missed_approach", ground_truth_label="none"),
        ]
        c = binary_confusion(rollouts)
        assert (c.tn, c.fp, c.fn, c.tp) == (0, 1, 1, 0)

    def test_pending_judge_excluded(self) -> None:
        # Sim-failure with judge not yet labeled is pending → excluded so a
        # half-finished run doesn't inflate FN.
        rollouts = [
            _scored("a", success=False, judge_label=None, ground_truth_label="missed_approach"),
        ]
        c = binary_confusion(rollouts)
        assert c.total == 0


class TestRenderBinaryMatrix:
    def test_empty_shows_placeholder(self) -> None:
        html = render_binary_matrix(binary_confusion([]))
        assert "pg-bcm__empty" in html
        assert "Populates" in html

    def test_populated_renders_four_cells(self) -> None:
        rollouts = [
            _scored("a", success=True, judge_label=None, ground_truth_label="none"),
            _scored(
                "b",
                success=False,
                judge_label="missed_approach",
                ground_truth_label="missed_approach",
            ),
        ]
        html = render_binary_matrix(binary_confusion(rollouts))
        for tag in ("TN", "FP", "FN", "TP"):
            assert tag in html
        assert "pg-bcm__cell--ok" in html
        assert "pg-bcm__cell--err" in html
        assert "env._check_success()" in html
