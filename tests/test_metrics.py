"""Pure-tabular tests for src.metrics. No sim, no API."""

from __future__ import annotations

from src.metrics import LabeledRollout, compute
from src.sim.scripted import FailureMode


def _row(rid: str, expected: FailureMode, judged: FailureMode | None) -> LabeledRollout:
    return LabeledRollout(rollout_id=rid, expected=expected, judged=judged)


class TestCompute:
    def test_empty_input(self) -> None:
        m = compute([])
        assert m.n_scored == 0
        assert m.overall_label_accuracy == 0.0
        assert m.per_label == []
        assert m.confusion == {}

    def test_perfect_agreement(self) -> None:
        rows = [
            _row("a", FailureMode.NONE, FailureMode.NONE),
            _row("b", FailureMode.MISSED_APPROACH, FailureMode.MISSED_APPROACH),
            _row("c", FailureMode.FAILED_GRIP, FailureMode.FAILED_GRIP),
        ]
        m = compute(rows)
        assert m.overall_label_accuracy == 1.0
        assert m.failure_detection_precision == 1.0
        assert m.failure_detection_recall == 1.0

    def test_judged_none_when_pass1_says_pass(self) -> None:
        # judged=None means Pass 1 said "pass" — collapse to NONE for scoring.
        rows = [_row("a", FailureMode.NONE, None)]
        m = compute(rows)
        assert m.overall_label_accuracy == 1.0  # NONE vs implicit-NONE matches

    def test_binary_failure_detection(self) -> None:
        rows = [
            # Judge missed a failure (FN for the binary detector)
            _row("a", FailureMode.FAILED_GRIP, FailureMode.NONE),
            # Judge invented a failure (FP)
            _row("b", FailureMode.NONE, FailureMode.MISSED_APPROACH),
            # Judge correctly flagged
            _row("c", FailureMode.MISSED_APPROACH, FailureMode.MISSED_APPROACH),
            _row("d", FailureMode.FAILED_GRIP, FailureMode.FAILED_GRIP),
        ]
        m = compute(rows)
        # binary TP = 2 (c, d), FP = 1 (b), FN = 1 (a)
        assert m.failure_detection_precision == 2 / 3
        assert m.failure_detection_recall == 2 / 3

    def test_label_swap_breaks_label_accuracy_but_not_binary_detection(self) -> None:
        # Both rollouts are failures and the judge said "fail" on both, just with
        # the wrong specific label. Binary detector is perfect; multi-class is 0.
        rows = [
            _row("a", FailureMode.MISSED_APPROACH, FailureMode.FAILED_GRIP),
            _row("b", FailureMode.FAILED_GRIP, FailureMode.MISSED_APPROACH),
        ]
        m = compute(rows)
        assert m.overall_label_accuracy == 0.0
        assert m.failure_detection_precision == 1.0
        assert m.failure_detection_recall == 1.0

    def test_per_label_precision_recall(self) -> None:
        rows = [
            _row("a", FailureMode.MISSED_APPROACH, FailureMode.MISSED_APPROACH),
            _row("b", FailureMode.MISSED_APPROACH, FailureMode.MISSED_APPROACH),
            _row("c", FailureMode.MISSED_APPROACH, FailureMode.FAILED_GRIP),  # FN for AM
            _row("d", FailureMode.NONE, FailureMode.MISSED_APPROACH),  # FP for AM
        ]
        m = compute(rows)
        am = next(s for s in m.per_label if s.label == FailureMode.MISSED_APPROACH)
        # tp=2, fp=1, fn=1 -> precision 2/3, recall 2/3
        assert am.tp == 2
        assert am.fp == 1
        assert am.fn == 1
        assert am.precision == 2 / 3
        assert am.recall == 2 / 3

    def test_confusion_matrix_counts(self) -> None:
        rows = [
            _row("a", FailureMode.MISSED_APPROACH, FailureMode.MISSED_APPROACH),
            _row("b", FailureMode.MISSED_APPROACH, FailureMode.FAILED_GRIP),
            _row("c", FailureMode.NONE, FailureMode.NONE),
        ]
        m = compute(rows)
        assert m.confusion[FailureMode.MISSED_APPROACH][FailureMode.MISSED_APPROACH] == 1
        assert m.confusion[FailureMode.MISSED_APPROACH][FailureMode.FAILED_GRIP] == 1
        assert m.confusion[FailureMode.NONE][FailureMode.NONE] == 1
