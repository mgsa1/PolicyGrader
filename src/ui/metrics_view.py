"""Data + render layer for the Metrics tab.

The tab is organised top-to-bottom (per the redesign spec):

  1. Cohort strip      — denominators visible before any percentage
  2. Caption           — single-line "what these numbers mean"
  3. Multiclass heatmap — clickable confusion matrix (the headline content)
  4. Per-label table    — support, predicted-as, P/R/F1, all as fractions
  5. Drill-down table   — populated when a heatmap cell or label is clicked

Binary detection (did the judge think this rollout failed?) no longer has
its own panel — sim success flags are authoritative now, so there is no
vision-vs-sim binary comparison worth rendering. The entire tab measures
the judge's taxonomy label against the injected ground-truth label.

The tab consumes the joined (test_matrix.csv × findings.jsonl) view that
src.ui.synthesis.load_scored_rollouts already returns. No new backend.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import plotly.graph_objects as go

from src.metrics import JudgeMetrics as JudgeMetrics_label
from src.metrics import LabeledRollout, LabelStats
from src.metrics import compute as compute_label_metrics
from src.sim.scripted import FailureMode
from src.ui import theme
from src.ui.synthesis import (
    KEYFRAMES_DIR_NAME,
    ScoredRollout,
    copy_button,
    html_escape,
)

SMALL_SAMPLE_THRESHOLD = 10  # below this, attach a "small sample" chip
WILSON_Z_95 = 1.96  # 95% Wilson CI z-score; no scipy required


# ---- Cohort counts ---------------------------------------------------------------


@dataclass(frozen=True)
class CohortCounts:
    """The calibration / deployment denominators that frame this tab."""

    n_calibration: int  # rollouts with injected ground-truth label
    n_calibration_with_findings: int  # of those, ones scored (success OR judge done)
    n_deployment: int  # rollouts with no ground-truth label (pretrained etc.)


def _calibration_is_scored(r: ScoredRollout) -> bool:
    """True iff this calibration rollout has a complete verdict to score.

    Successful rollouts are implicitly "none" (judge doesn't run). Failed
    rollouts are scored once the judge has produced a label.
    """
    if not r.ground_truth_label:
        return False
    if r.success:
        return True
    return r.judge_label is not None


def cohort_counts(rollouts: list[ScoredRollout]) -> CohortCounts:
    n_cal = sum(1 for r in rollouts if r.ground_truth_label)
    n_cal_done = sum(1 for r in rollouts if _calibration_is_scored(r))
    n_dep = len(rollouts) - n_cal
    return CohortCounts(
        n_calibration=n_cal,
        n_calibration_with_findings=n_cal_done,
        n_deployment=n_dep,
    )


# ---- Wilson 95% CI for a binomial proportion -------------------------------------


def wilson_ci_95(successes: int, n: int) -> tuple[float, float]:
    """Wilson score interval (95% CI) for a binomial proportion."""
    if n == 0:
        return (0.0, 0.0)
    z = WILSON_Z_95
    p = successes / n
    z2_n = z * z / n
    denom = 1 + z2_n
    center = (p + z2_n / 2) / denom
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, center - margin), min(1.0, center + margin))


# ---- ScoredRollout → LabeledRollout adapter --------------------------------------
# The src.metrics module operates on LabeledRollout (FailureMode-typed). For the
# multiclass heatmap and per-label table we feed it the subset of rollouts that
# (a) have ground-truth labels and (b) have a complete verdict — either sim said
# success (→ implicit "none") or sim said fail AND the judge has produced a
# label. Failed rollouts with the judge still pending are excluded so they
# don't pollute the "judged as none" cell.


def to_labeled_rollouts(rollouts: list[ScoredRollout]) -> list[LabeledRollout]:
    """Convert to LabeledRollout for rollouts that have ground truth AND a complete verdict.

    A calibration rollout is "complete" when either (a) sim said success (we
    treat that as judge_label="none" because the judge doesn't run on
    successes) or (b) sim said fail AND the judge has produced a label.
    """
    out: list[LabeledRollout] = []
    for r in rollouts:
        if not r.ground_truth_label:
            continue
        try:
            expected = FailureMode(r.ground_truth_label)
        except ValueError:
            continue
        if r.success:
            judged: FailureMode | None = FailureMode.NONE
        elif r.judge_label:
            try:
                judged = FailureMode(r.judge_label)
            except ValueError:
                continue  # label not in the FailureMode enum (taxonomy drift); skip
        else:
            continue  # sim said fail but judge is pending — not yet scorable
        out.append(LabeledRollout(rollout_id=r.rollout_id, expected=expected, judged=judged))
    return out


# ---- Heatmap label ordering ------------------------------------------------------


def _taxonomy_order() -> list[FailureMode]:
    """`none` first, then the rest alphabetically — matches how a viewer reads the table."""
    others = sorted(
        (lab for lab in FailureMode if lab != FailureMode.NONE),
        key=lambda lab: lab.value,
    )
    return [FailureMode.NONE] + others


def _used_labels(metrics: JudgeMetrics_label, order: list[FailureMode]) -> list[FailureMode]:
    """Return labels that appear (as expected OR judged) in at least one cell."""
    used: set[FailureMode] = set()
    for exp, judged_dict in metrics.confusion.items():
        for jud, count in judged_dict.items():
            if count > 0:
                used.add(exp)
                used.add(jud)
    return [lab for lab in order if lab in used]


# ---- Cohort strip render ---------------------------------------------------------


def render_cohort_strip(counts: CohortCounts) -> str:
    """Three-pill cohort strip: calibration / scored / excluded(deployment)."""
    pills = [
        ("Calibration rollouts", counts.n_calibration, theme.CAL),
        ("Scored by judge", counts.n_calibration_with_findings, theme.CAL),
        ("Excluded (deployment)", counts.n_deployment, theme.DEP),
    ]
    chips: list[str] = []
    for label, n, accent in pills:
        small = n > 0 and n < SMALL_SAMPLE_THRESHOLD
        small_chip = "<span class='pg-chip__small'>small sample</span>" if small else ""
        chips.append(
            f"<div class='pg-cohort-pill' style='border-left-color:{accent};'>"
            f"<span class='pg-cohort-pill__label' style='color:{accent};'>{label}</span>"
            f"<span class='pg-cohort-pill__value'>{n}</span>"
            f"{small_chip}"
            "</div>"
        )
    return "<div class='pg-cohort-strip'>" + "".join(chips) + "</div>"


# ---- Caption ---------------------------------------------------------------------


def render_caption() -> str:
    return (
        "<div style='font-size:12px;color:"
        + theme.INK_3
        + ";margin-bottom:18px;line-height:1.55;'>"
        "Binary success comes from <code>env._check_success()</code> (sim-authoritative). "
        "This tab measures the judge's <b>taxonomy label</b> against the failure-injection "
        "parameter used in the scripted policy. Pretrained (deployment) rollouts have no "
        "injected ground truth and are excluded from these numbers — see the Deployment "
        "findings tab."
        "</div>"
    )


def render_scope_strip(rollouts: list[ScoredRollout], scope: str) -> str:
    """Big top-of-tab strip: 'N videos · M failures' for the cohort in view.

    `scope` is "calibration" or "deployment". Failure denominator comes from
    sim (`env._check_success()`) for both cohorts — binary success is no
    longer a vision-side decision.
    """
    if scope == "calibration":
        cohort = [r for r in rollouts if r.population == "calibration"]
        n_videos = len(cohort)
        n_failures = sum(1 for r in cohort if r.is_failure)
        accent = theme.CAL
        cohort_label = "Calibration cohort"
        failures_caption = "sim failures (ground truth)"
    elif scope == "deployment":
        cohort = [r for r in rollouts if r.population == "deployment"]
        n_videos = len(cohort)
        n_failures = sum(1 for r in cohort if r.is_failure)
        accent = theme.DEP
        cohort_label = "Deployment cohort"
        failures_caption = "sim failures (labeled by judge)"
    else:
        raise ValueError(f"unknown scope: {scope!r}")

    return (
        "<div class='pg-scope'>"
        f"<div class='pg-scope__label' style='color:{accent};'>{cohort_label}</div>"
        "<div class='pg-scope__nums'>"
        f"<div class='pg-scope__num'>"
        f"<div class='pg-scope__value' style='color:{accent};'>{n_videos}</div>"
        "<div class='pg-scope__caption'>videos in scope</div>"
        "</div>"
        "<div class='pg-scope__sep'>·</div>"
        "<div class='pg-scope__num'>"
        f"<div class='pg-scope__value' style='color:{accent};'>{n_failures}</div>"
        f"<div class='pg-scope__caption'>{failures_caption}</div>"
        "</div>"
        "</div>"
        "</div>"
    )


def render_judge_calibration_header() -> str:
    """Framed purpose-line strip at the top of the Judge calibration tab.

    A viewer who reads only this strip + the cohort pills below should
    already understand what the tab is and is not.
    """
    return (
        "<div class='pg-callout'>"
        f"<div class='pg-callout__eyebrow' style='color:{theme.CAL};'>JUDGE CALIBRATION</div>"
        "<div class='pg-callout__body'>"
        "This tab measures the <b>judge</b>, not the policy. The numbers here "
        "come from rollouts where we injected a known failure, so we know the "
        "correct label. Policy findings live in the <b>Deployment findings</b> tab."
        "</div></div>"
    )


# ---- Judge trust summary (used by the Deployment-findings header banner) ---------


@dataclass(frozen=True)
class JudgeTrust:
    """Compact summary of judge calibration for the Deployment findings banner.

    Binary detection is no longer measured — sim success is authoritative.
    The trust numbers now focus on multiclass: overall label accuracy across
    the calibration cohort, plus per-label precision/recall averaged over
    labels with enough support (>=3) to publish a number.
    """

    n_calibration: int
    n_scored: int  # calibration rollouts with a complete verdict
    label_correct: int  # of n_scored, ones where judge matched GT
    per_label_precision_avg: float | None  # None if no labels with support
    per_label_recall_avg: float | None
    n_labels_with_support: int  # taxonomy labels with cal support >= 3
    total_taxonomy_labels: int

    @property
    def label_accuracy(self) -> float | None:
        if self.n_scored == 0:
            return None
        return self.label_correct / self.n_scored


def judge_trust(rollouts: list[ScoredRollout]) -> JudgeTrust:
    """Summarize judge calibration for the trust banner."""
    labeled = to_labeled_rollouts(rollouts)
    label_metrics = compute_label_metrics(labeled)

    n_scored = label_metrics.n_scored
    label_correct = int(round(label_metrics.overall_label_accuracy * n_scored)) if n_scored else 0

    # Per-label precision/recall averaged across labels with support >= 3.
    qual_labels = [s for s in label_metrics.per_label if (s.tp + s.fn) >= 3 or (s.tp + s.fp) >= 3]
    avg_p = sum(s.precision for s in qual_labels) / len(qual_labels) if qual_labels else None
    avg_r = sum(s.recall for s in qual_labels) / len(qual_labels) if qual_labels else None

    n_cal = sum(1 for r in rollouts if r.population == "calibration")
    n_taxonomy_total = len([m for m in FailureMode if m != FailureMode.NONE])

    return JudgeTrust(
        n_calibration=n_cal,
        n_scored=n_scored,
        label_correct=label_correct,
        per_label_precision_avg=avg_p,
        per_label_recall_avg=avg_r,
        n_labels_with_support=len(qual_labels),
        total_taxonomy_labels=n_taxonomy_total,
    )


def render_judge_trust_banner(trust: JudgeTrust) -> str:
    """The 'how much to trust these findings' banner at the top of Deployment findings."""
    if trust.n_calibration == 0:
        return (
            "<div class='pg-callout pg-callout--dep'>"
            f"<div class='pg-callout__eyebrow' style='color:{theme.DEP};'>"
            "JUDGE TRUST · uncalibrated run</div>"
            "<div class='pg-callout__body'>"
            "No calibration rollouts in this run. Judge outputs below are "
            "<b>uncalibrated</b> — treat as directional, not measured."
            "</div></div>"
        )

    acc = trust.label_accuracy
    acc_html = (
        f"<b>{trust.label_correct}/{trust.n_scored}</b> · {acc * 100:.1f}%"
        if acc is not None
        else f"<span style='color:{theme.INK_4};'>no calibration verdicts yet</span>"
    )
    avg_p = (
        f"<b>{trust.per_label_precision_avg:.2f}</b>"
        if trust.per_label_precision_avg is not None
        else f"<span style='color:{theme.INK_4};'>(no labels with support ≥3)</span>"
    )
    avg_r = (
        f"<b>{trust.per_label_recall_avg:.2f}</b>"
        if trust.per_label_recall_avg is not None
        else f"<span style='color:{theme.INK_4};'>—</span>"
    )

    return (
        "<div class='pg-callout'>"
        "<div style='display:flex;align-items:baseline;gap:10px;margin-bottom:10px;'>"
        f"<span class='pg-callout__eyebrow' style='color:{theme.CAL};margin:0;'>JUDGE TRUST</span>"
        f"<span style='font-size:11px;color:{theme.INK_4};'>"
        f"pulled from {trust.n_calibration} calibration rollouts</span>"
        "</div>"
        "<div class='pg-callout__grid'>"
        "<div class='pg-callout__grid-label'>Label accuracy</div>"
        f"<div>{acc_html}</div>"
        "<div class='pg-callout__grid-label'>Per-label average</div>"
        f"<div>precision {avg_p}   ·   recall {avg_r}</div>"
        "<div class='pg-callout__grid-label'>Coverage</div>"
        f"<div><b>{trust.n_labels_with_support}</b> of "
        f"{trust.total_taxonomy_labels} taxonomy labels have support ≥ 3</div>"
        "</div>"
        "<div class='pg-callout__note'>"
        "Findings below are <b>calibrated estimates</b>. Each failure label is "
        "decorated with its calibration precision where available."
        "</div></div>"
    )


# ---- Per-label calibration precision lookup (used to decorate deployment findings) ----


def per_label_calibration(rollouts: list[ScoredRollout]) -> dict[str, LabelStats]:
    """Map taxonomy label → its LabelStats from the calibration subset.

    Used by the Deployment findings tab to attach 'judge P = X' chips to
    deployment-finding label counts.
    """
    labeled = to_labeled_rollouts(rollouts)
    metrics = compute_label_metrics(labeled)
    return {s.label.value: s for s in metrics.per_label}


def render_calibration_chip(label: str, stats: dict[str, LabelStats]) -> str:
    """Return a 'judge P = X' chip for a given label, or 'uncalibrated' if support<3.

    Tooltip mentions the calibration source so the viewer can trace it back.
    """
    s = stats.get(label)
    if s is None:
        text = "uncalibrated"
        title = "No calibration rollouts have this expected label."
        variant = "neutral"
    else:
        support = s.tp + s.fn
        if support < 3:
            text = "uncalibrated"
            title = (
                f"Only {support} calibration rollouts with injected label "
                f"'{label}' — too few to publish a precision."
            )
            variant = "neutral"
        else:
            text = f"judge P = {s.precision:.2f}"
            title = (
                f"Based on {support} calibration rollouts with injected label "
                f"'{label}'. See Judge calibration tab."
            )
            variant = "cal"
    class_attr = "pg-chip" if variant == "neutral" else f"pg-chip pg-chip--{variant}"
    return (
        f"<span title='{html_escape(title)}' class='{class_attr}' "
        f"style='font-family:{theme.FONT_MONO};margin-left:6px;'>"
        f"{text}</span>"
    )


# ---- Multiclass heatmap ----------------------------------------------------------


def render_heatmap_figure(rollouts: list[ScoredRollout]) -> go.Figure:
    """Plotly heatmap. Diagonal cells in green hues, off-diagonal in orange hues.

    Trick: encode position semantics into z (diagonal positive, off-diagonal
    negative) so a single colorscale renders both as different hues.
    """
    labeled = to_labeled_rollouts(rollouts)
    metrics = compute_label_metrics(labeled)
    used = _used_labels(metrics, _taxonomy_order())

    if not used:
        fig = go.Figure()
        fig.update_layout(
            annotations=[
                {
                    "text": "No labeled rollouts yet — needs scripted "
                    "(ground-truth-bearing) rows judged.",
                    "showarrow": False,
                    "font": {"size": 12, "color": theme.INK_4},
                }
            ],
            plot_bgcolor=theme.SURFACE,
            paper_bgcolor=theme.SURFACE,
            margin={"l": 30, "r": 30, "t": 30, "b": 30},
            height=360,
        )
        return fig

    n = len(used)
    counts = [[metrics.confusion.get(exp, {}).get(jud, 0) for jud in used] for exp in used]
    max_count = max((c for row in counts for c in row), default=1)
    log_max = math.log1p(max_count) or 1.0

    # Encode: diagonal -> +log1p/log_max in [0..1]; off-diag -> -log1p/log_max in [-1..0].
    z: list[list[float]] = []
    text: list[list[str]] = []
    for i in range(n):
        z_row, t_row = [], []
        for j in range(n):
            c = counts[i][j]
            if c == 0:
                z_row.append(0.0)
                t_row.append("")
            elif i == j:
                z_row.append(math.log1p(c) / log_max)
                t_row.append(str(c))
            else:
                z_row.append(-math.log1p(c) / log_max)
                t_row.append(str(c))
        z.append(z_row)
        text.append(t_row)

    label_strs = [lab.value for lab in used]
    row_totals = [sum(row) for row in counts]
    col_totals = [sum(counts[i][j] for i in range(n)) for j in range(n)]

    # Text color per cell: the colorscale goes from a deep amber (off-diag, bad)
    # through surface-white (zero) to deep green (diag, good). Near the extremes
    # we need white text for contrast; near zero (surface-white bg) we need ink.
    text_colors: list[list[str]] = []
    for i in range(n):
        row: list[str] = []
        for j in range(n):
            c = counts[i][j]
            if c == 0:
                row.append(theme.INK_5)
            elif abs(z[i][j]) > 0.55:
                row.append(theme.SURFACE)
            else:
                row.append(theme.INK_1)
        text_colors.append(row)

    fig = go.Figure(
        data=go.Heatmap(
            z=z,
            x=label_strs,
            y=label_strs,
            text=text,
            texttemplate="%{text}",
            textfont={"size": 14, "color": theme.INK_1},
            zmin=-1,
            zmax=1,
            colorscale=[
                [0.0, theme.ERR],  # off-diag, high count -> deep red
                [0.49, theme.SURFACE],  # off-diag, near zero -> surface
                [0.5, theme.SURFACE],  # zero -> surface
                [0.51, theme.SURFACE],
                [1.0, theme.OK],  # diag, high count -> deep green
            ],
            showscale=False,
            hovertemplate="expected: %{y}<br>judged: %{x}<br>count: %{text}<extra></extra>",
            customdata=[[(label_strs[i], label_strs[j]) for j in range(n)] for i in range(n)],
            xgap=2,
            ygap=2,
        )
    )
    # Per-cell text-color overrides for contrast against the new colorscale.
    # We overlay an annotation per non-zero cell so we can color each one.
    annotations = []
    for i in range(n):
        for j in range(n):
            if counts[i][j] == 0:
                continue
            annotations.append(
                {
                    "x": j,
                    "y": i,
                    "text": f"<b>{counts[i][j]}</b>",
                    "showarrow": False,
                    "xref": "x",
                    "yref": "y",
                    "font": {"size": 13, "color": text_colors[i][j]},
                }
            )
    # Row/col totals in the margin (INK_4 on the surface).
    for i, total in enumerate(row_totals):
        annotations.append(
            {
                "x": n - 0.5 + 0.6,
                "y": i,
                "text": f"<b>{total}</b>",
                "showarrow": False,
                "xref": "x",
                "yref": "y",
                "font": {"size": 11, "color": theme.INK_4},
                "xanchor": "left",
            }
        )
    for j, total in enumerate(col_totals):
        annotations.append(
            {
                "x": j,
                "y": n - 0.5 + 0.6,
                "text": f"<b>{total}</b>",
                "showarrow": False,
                "xref": "x",
                "yref": "y",
                "font": {"size": 11, "color": theme.INK_4},
                "yanchor": "top",
            }
        )
    # The colored text overlay supersedes the built-in texttemplate, which is
    # always one color. Hide the built-in text so only our annotations show.
    fig.update_traces(text=[["" for _ in range(n)] for _ in range(n)], selector={"type": "heatmap"})

    fig.update_layout(
        xaxis={
            "title": {"text": "Judged label", "font": {"color": theme.INK_3, "size": 12}},
            "tickangle": -30,
            "tickfont": {"color": theme.INK_2, "size": 11},
            "side": "top",
            "gridcolor": theme.LINE,
        },
        yaxis={
            "title": {"text": "Expected label", "font": {"color": theme.INK_3, "size": 12}},
            "autorange": "reversed",
            "tickfont": {"color": theme.INK_2, "size": 11},
            "gridcolor": theme.LINE,
        },
        margin={"l": 140, "r": 60, "t": 100, "b": 60},
        plot_bgcolor=theme.SURFACE,
        paper_bgcolor=theme.SURFACE,
        height=460,
        annotations=annotations,
        font={"family": theme.FONT_BODY},
    )
    return fig


# ---- Per-label table -------------------------------------------------------------


_PER_LABEL_COLS = "grid-template-columns:1.6fr 0.7fr 0.9fr 1.2fr 1.2fr 0.6fr;"


def render_per_label_table(rollouts: list[ScoredRollout]) -> str:
    """Per-label support / predicted-as / P / R / F1 table.

    Uses src.metrics.per_label for the stats; renders as HTML so we can apply
    the muted-on-low-support styling the spec wants.
    """
    labeled = to_labeled_rollouts(rollouts)
    metrics = compute_label_metrics(labeled)

    rows: list[str] = [
        f"<div class='pg-table__row pg-table__row--head' style='{_PER_LABEL_COLS}'>"
        "<div>Label</div><div>Support</div><div>Predicted as</div>"
        "<div>Precision</div><div>Recall</div><div>F1</div>"
        "</div>"
    ]
    if not metrics.per_label:
        rows.append(
            "<div class='pg-empty pg-empty--small'>"
            "(no labels with judged-vs-expected pairs yet)</div>"
        )
    for stats in metrics.per_label:
        rows.append(_per_label_row(stats))

    return (
        "<div class='pg-table'>"
        f"<div class='pg-table__eyebrow' style='color:{theme.JUDGE};'>"
        "Per-label breakdown</div>" + "".join(rows) + "</div>"
    )


def _per_label_row(stats: LabelStats) -> str:
    label_str = stats.label.value
    support = stats.tp + stats.fn
    predicted_as = stats.tp + stats.fp
    prec_frac = f"{stats.tp}/{predicted_as}" if predicted_as else "—"
    rec_frac = f"{stats.tp}/{support}" if support else "—"
    prec_pct = f"{stats.precision * 100:.1f}%" if predicted_as else ""
    rec_pct = f"{stats.recall * 100:.1f}%" if support else ""
    f1 = f"{stats.f1:.2f}"
    small = support > 0 and support < 3

    label_color = theme.INK_4 if small else theme.INK_1
    cell_color = theme.INK_4 if small else theme.INK_2

    chip = "<span class='pg-chip__small'>small sample</span>" if small else ""
    cell_style = f"color:{cell_color};"
    return (
        f"<div class='pg-table__row' style='{_PER_LABEL_COLS}'>"
        f"<div class='pg-table__cell-mono' style='font-size:13px;color:{label_color};"
        f"font-weight:500;'>{label_str}{chip}</div>"
        f"<div class='pg-table__cell-mono' style='{cell_style}'>{support}</div>"
        f"<div class='pg-table__cell-mono' style='{cell_style}'>{predicted_as}</div>"
        f"<div class='pg-table__cell-mono' style='{cell_style}'>{prec_frac}"
        f"<span style='margin-left:6px;color:{theme.INK_4};'>{prec_pct}</span></div>"
        f"<div class='pg-table__cell-mono' style='{cell_style}'>{rec_frac}"
        f"<span style='margin-left:6px;color:{theme.INK_4};'>{rec_pct}</span></div>"
        f"<div class='pg-table__cell-mono' style='color:{label_color};'>{f1}</div>"
        "</div>"
    )


# ---- Drill-down ------------------------------------------------------------------


@dataclass(frozen=True)
class DrillFilter:
    """A user-set filter narrowing the drill-down table.

    `expected` and `judged` together represent a heatmap-cell click (both set).
    Setting only `expected` or only `judged` represents a per-label-row click —
    keep all rollouts where THAT label appears as either expected or judged.
    """

    expected: str | None
    judged: str | None

    @property
    def is_active(self) -> bool:
        return self.expected is not None or self.judged is not None

    def label_text(self) -> str:
        if self.expected and self.judged:
            return f"expected={self.expected} AND judged={self.judged}"
        if self.expected:
            return f"label={self.expected} (expected OR judged)"
        if self.judged:
            return f"label={self.judged} (expected OR judged)"
        return ""


EMPTY_FILTER = DrillFilter(expected=None, judged=None)


def filter_rollouts(rollouts: list[ScoredRollout], f: DrillFilter) -> list[ScoredRollout]:
    if not f.is_active:
        return []
    out: list[ScoredRollout] = []
    for r in rollouts:
        if not r.ground_truth_label:
            continue
        gt = r.ground_truth_label
        # Derive the judge's effective label for this rollout:
        #  - sim said success → implicit "none" (judge didn't run)
        #  - sim said fail and judge has labeled → that label
        #  - sim said fail and judge pending → skip (incomplete verdict)
        if r.success:
            jud = "none"
        elif r.judge_label:
            jud = r.judge_label
        else:
            continue
        if f.expected and f.judged:
            if gt == f.expected and jud == f.judged:
                out.append(r)
        else:
            label = f.expected or f.judged
            if gt == label or jud == label:
                out.append(r)
    return out


_DRILL_COLS = "grid-template-columns:160px 1.4fr 1.4fr 0.9fr 0.9fr 2fr;"


def render_drill_down(
    rollouts: list[ScoredRollout],
    f: DrillFilter,
    keyframes: dict[str, Path],
) -> str:
    if not f.is_active:
        return (
            "<div class='pg-empty'>"
            "Click a confusion-matrix cell or a label row to inspect the rollouts behind it."
            "</div>"
        )

    matches = filter_rollouts(rollouts, f)
    if not matches:
        return (
            "<div class='pg-empty pg-empty--small'>"
            "Filter active but no rollouts match. Try Clear filter."
            "</div>"
        )

    rows: list[str] = [
        f"<div class='pg-table__row pg-table__row--head' style='{_DRILL_COLS}'>"
        "<div>Keyframe</div><div>Rollout</div><div>Expected → Judged</div>"
        "<div>Policy</div><div>Match</div><div>Judge description</div>"
        "</div>"
    ]
    for r in matches:
        rows.append(_drill_row(r, keyframes))
    return "<div class='pg-table'>" + "".join(rows) + "</div>"


def _drill_row(r: ScoredRollout, keyframes: dict[str, Path]) -> str:
    expected = r.ground_truth_label or "—"
    if r.success:
        judged = "none"
    elif r.judge_label:
        judged = r.judge_label
    else:
        judged = "(pending)"

    match = expected == judged
    badge_class = "pg-match-badge--ok" if match else "pg-match-badge--err"
    badge_text = "match" if match else "mismatch"

    kf = keyframes.get(r.rollout_id)
    if kf is not None:
        overlays = copy_button(kf, kind="png", anchor="top-left")
        if r.video_path_host:
            overlays += copy_button(r.video_path_host, kind="mp4", anchor="top-right")
        img_html = f"<div class='pg-drill-thumb'><img src='/gradio_api/file={kf}'/>{overlays}</div>"
    else:
        img_html = "<div class='pg-drill-thumb pg-drill-thumb--empty'>no keyframe</div>"

    mp4_link = (
        f"<a class='pg-drill-link' href='/gradio_api/file={r.video_path_host}' target='_blank'>"
        f"{r.rollout_id}</a>"
        if r.video_path_host
        else f"<span class='pg-drill-link'>{r.rollout_id}</span>"
    )

    desc = (r.judge_description or "—")[:160]

    return (
        f"<div class='pg-table__row' style='{_DRILL_COLS}align-items:start;padding:12px 10px;'>"
        f"<div>{img_html}</div>"
        f"<div class='pg-table__cell-mono'>{mp4_link}</div>"
        f"<div class='pg-table__cell-mono'>{expected} → {judged}</div>"
        f"<div class='pg-table__cell-mono pg-table__cell-muted'>{r.policy_kind}</div>"
        f"<div><span class='pg-match-badge {badge_class}'>{badge_text}</span></div>"
        f"<div style='font-size:12px;color:{theme.INK_2};line-height:1.45;'>{desc}</div>"
        "</div>"
    )


# ---- Top-level render orchestrator (everything except the heatmap, which is gr.Plot) -----


def render_static_blocks(
    rollouts: list[ScoredRollout],
) -> tuple[str, str, str]:
    """Render the three HTML blocks: cohort, caption, per-label table.

    Binary panel is gone with the two-pass retirement — sim owns the binary
    verdict, so only the multiclass label breakdown is worth rendering here.
    """
    counts = cohort_counts(rollouts)
    return (
        render_cohort_strip(counts),
        render_caption(),
        render_per_label_table(rollouts),
    )


def keyframes_dir(mirror_root: Path) -> Path:
    return mirror_root / KEYFRAMES_DIR_NAME
