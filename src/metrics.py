"""Precision/recall of the vision judge against injected ground-truth labels.

CLAUDE.md sec 13: the demo's TPM-slide frame is `Precision X% · Recall Y%`,
so this module is what makes the eval an *eval*. It must:

  - never look at frames or videos — it's a pure tabular comparison
  - work over a list of (expected, judged) label pairs
  - give per-label numbers, not just a global score, so the report can
    surface "we're great at slip but mediocre at approach_miss"
  - report binary fail-detection (any-failure vs none) separately from
    multi-class label agreement, since those answer different questions

The taxonomy is the closed set in src.sim.scripted.FailureMode. Pretrained
rollouts have ground_truth_label=None (we don't know what should happen) and
are excluded from precision/recall — they only enter via the per-policy
success rate column in the report.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from src.sim.scripted import FailureMode


@dataclass(frozen=True)
class LabeledRollout:
    """One row to score: ground-truth label and what the judge emitted.

    `judged_label` is None when Pass 1 returned "pass" (no Pass 2 ran); the
    rollout is treated as judge_says_none for the purposes of metrics.
    """

    rollout_id: str
    expected: FailureMode
    judged: FailureMode | None

    @property
    def judge_label(self) -> FailureMode:
        return self.judged if self.judged is not None else FailureMode.NONE


@dataclass(frozen=True)
class LabelStats:
    """Per-label confusion counts and derived rates."""

    label: FailureMode
    tp: int  # expected==label AND judged==label
    fp: int  # expected!=label AND judged==label
    fn: int  # expected==label AND judged!=label

    @property
    def precision(self) -> float:
        denom = self.tp + self.fp
        return self.tp / denom if denom else 0.0

    @property
    def recall(self) -> float:
        denom = self.tp + self.fn
        return self.tp / denom if denom else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0


@dataclass(frozen=True)
class JudgeMetrics:
    """Top-level scorecard the report writer consumes."""

    n_scored: int
    overall_label_accuracy: float  # exact-match rate across all rows

    # Binary "is something wrong" detector — collapses every non-NONE label to FAIL.
    failure_detection_precision: float
    failure_detection_recall: float

    # Per-label breakdown over labels that actually appear in the data.
    per_label: list[LabelStats]

    # rows × cols dict for the confusion matrix in the report. Outer key is
    # expected label, inner key is judged label, value is count.
    confusion: dict[FailureMode, dict[FailureMode, int]]


def _to_binary_fail(label: FailureMode) -> bool:
    return label != FailureMode.NONE


def compute(rollouts: Iterable[LabeledRollout]) -> JudgeMetrics:
    """Score the judge against ground truth. Pure function, no I/O."""
    rows = list(rollouts)
    n = len(rows)

    if n == 0:
        return JudgeMetrics(
            n_scored=0,
            overall_label_accuracy=0.0,
            failure_detection_precision=0.0,
            failure_detection_recall=0.0,
            per_label=[],
            confusion={},
        )

    # Confusion matrix.
    confusion: dict[FailureMode, dict[FailureMode, int]] = {}
    correct = 0
    for r in rows:
        confusion.setdefault(r.expected, {}).setdefault(r.judge_label, 0)
        confusion[r.expected][r.judge_label] += 1
        if r.expected == r.judge_label:
            correct += 1

    # Per-label precision/recall over labels that appear in either column.
    labels_seen: set[FailureMode] = set()
    for r in rows:
        labels_seen.add(r.expected)
        labels_seen.add(r.judge_label)

    per_label: list[LabelStats] = []
    for label in sorted(labels_seen, key=lambda x: x.value):
        tp = sum(1 for r in rows if r.expected == label and r.judge_label == label)
        fp = sum(1 for r in rows if r.expected != label and r.judge_label == label)
        fn = sum(1 for r in rows if r.expected == label and r.judge_label != label)
        per_label.append(LabelStats(label=label, tp=tp, fp=fp, fn=fn))

    # Binary fail-detection: positive class = "any non-none label".
    bin_tp = sum(1 for r in rows if _to_binary_fail(r.expected) and _to_binary_fail(r.judge_label))
    bin_fp = sum(
        1 for r in rows if not _to_binary_fail(r.expected) and _to_binary_fail(r.judge_label)
    )
    bin_fn = sum(
        1 for r in rows if _to_binary_fail(r.expected) and not _to_binary_fail(r.judge_label)
    )
    bin_prec = bin_tp / (bin_tp + bin_fp) if (bin_tp + bin_fp) else 0.0
    bin_rec = bin_tp / (bin_tp + bin_fn) if (bin_tp + bin_fn) else 0.0

    return JudgeMetrics(
        n_scored=n,
        overall_label_accuracy=correct / n,
        failure_detection_precision=bin_prec,
        failure_detection_recall=bin_rec,
        per_label=per_label,
        confusion=confusion,
    )
