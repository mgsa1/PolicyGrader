"""Data + render layer for the Metrics tab.

The tab is organised top-to-bottom (per the redesign spec):

  1. Cohort strip          — denominators visible before any percentage
  2. Caption               — single-line "what these numbers mean"
  3. Binary detector panel — Pass-1: 2x2 confusion + 4 stats with Wilson CI
  4. Multiclass heatmap    — Pass-2: clickable confusion matrix
  5. Per-label table       — support, predicted-as, P/R/F1, all as fractions
  6. Drill-down table      — populated when a heatmap cell or label is clicked

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
from src.ui.synthesis import (
    KEYFRAMES_DIR_NAME,
    JudgeMetrics,
    ScoredRollout,
    copyable_path,
)

SMALL_SAMPLE_THRESHOLD = 10  # below this, attach a "small sample" chip
WILSON_Z_95 = 1.96  # 95% Wilson CI z-score; no scipy required


# ---- Cohort counts ---------------------------------------------------------------


@dataclass(frozen=True)
class CohortCounts:
    """The denominators every percentage on this tab is divided by."""

    total: int
    binary_scored: int  # rollouts that received a Pass-1 verdict
    label_scored: int  # rollouts that have ground-truth label (scripted)
    excluded_pretrained: int  # pretrained rollouts (label ground truth unknown)


def cohort_counts(rollouts: list[ScoredRollout]) -> CohortCounts:
    return CohortCounts(
        total=len(rollouts),
        binary_scored=sum(1 for r in rollouts if r.pass1_verdict is not None),
        label_scored=sum(1 for r in rollouts if r.ground_truth_label),
        excluded_pretrained=sum(
            1 for r in rollouts if r.policy_kind == "pretrained" and not r.ground_truth_label
        ),
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
# (a) have ground-truth labels and (b) the judge has finished (Pass-2 done OR
# Pass-1 said pass). A rollout in the in-between state — Pass-1 said fail, Pass-2
# pending — is excluded so it doesn't pollute "judged as none".


def to_labeled_rollouts(rollouts: list[ScoredRollout]) -> list[LabeledRollout]:
    """Convert to LabeledRollout for rollouts that have ground truth AND a complete verdict."""
    out: list[LabeledRollout] = []
    for r in rollouts:
        if not r.ground_truth_label:
            continue
        try:
            expected = FailureMode(r.ground_truth_label)
        except ValueError:
            continue
        if r.pass1_verdict is None:
            continue  # judge incomplete
        if r.pass1_verdict == "pass":
            judged: FailureMode | None = FailureMode.NONE
        elif r.pass2_label:
            try:
                judged = FailureMode(r.pass2_label)
            except ValueError:
                continue  # label not in the FailureMode enum (taxonomy drift); skip
        else:
            continue  # Pass-1 fail but Pass-2 pending — judge incomplete
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
    pills = [
        ("Total", counts.total),
        ("Binary-scored", counts.binary_scored),
        ("Label-scored", counts.label_scored),
        ("Excluded (pretrained)", counts.excluded_pretrained),
    ]
    chips: list[str] = []
    for label, n in pills:
        small = n > 0 and n < SMALL_SAMPLE_THRESHOLD
        small_chip = (
            "<span style='margin-left:8px;font-size:10px;color:#94a3b8;background:#334155;"
            "padding:1px 6px;border-radius:8px;text-transform:none;letter-spacing:0;'>"
            "small sample</span>"
            if small
            else ""
        )
        chips.append(
            f"<div style='padding:10px 16px;background:#1e293b;border-radius:24px;"
            f"display:flex;align-items:baseline;gap:8px;'>"
            f"<span style='font-size:10px;color:#94a3b8;text-transform:uppercase;"
            f"letter-spacing:1.4px;font-weight:600;'>{label}</span>"
            f"<span style='font-size:20px;font-weight:700;color:#f1f5f9;"
            f"font-variant-numeric:tabular-nums;'>{n}</span>"
            f"{small_chip}"
            f"</div>"
        )
    return (
        "<div style='display:flex;gap:12px;flex-wrap:wrap;margin-bottom:14px;'>"
        + "".join(chips)
        + "</div>"
    )


# ---- Caption ---------------------------------------------------------------------


def render_caption() -> str:
    return (
        "<div style='font-size:12px;color:#94a3b8;margin-bottom:18px;line-height:1.5;'>"
        "<b>Pass-1</b>: binary pass/fail vs <code>env._check_success()</code>. "
        "<b>Pass-2</b>: taxonomy label vs the failure-injection parameter used in the "
        "scripted policy. Pretrained rollouts enter Pass-1 only."
        "</div>"
    )


# ---- Binary detector panel -------------------------------------------------------


def render_binary_panel(metrics: JudgeMetrics) -> str:
    """2x2 confusion + Precision/Recall/F1/Accuracy as fractions, with Wilson 95% CI."""
    tp, fp, fn, tn = metrics.pass1_tp, metrics.pass1_fp, metrics.pass1_fn, metrics.pass1_tn
    n = tp + fp + fn + tn
    if n == 0:
        return (
            "<div style='padding:14px;color:#94a3b8;font-style:italic;'>"
            "No Pass-1 verdicts yet.</div>"
        )

    prec_n = tp + fp
    rec_n = tp + fn
    prec_lo, prec_hi = wilson_ci_95(tp, prec_n)
    rec_lo, rec_hi = wilson_ci_95(tp, rec_n)
    accuracy_n = n
    accuracy_correct = tp + tn
    f1 = 2 * tp / (2 * tp + fp + fn) if (2 * tp + fp + fn) else 0.0

    matrix_html = _binary_matrix_html(tp, fp, fn, tn)
    stats_html = _binary_stats_html(
        prec_correct=tp,
        prec_n=prec_n,
        prec_ci=(prec_lo, prec_hi),
        rec_correct=tp,
        rec_n=rec_n,
        rec_ci=(rec_lo, rec_hi),
        f1=f1,
        acc_correct=accuracy_correct,
        acc_n=accuracy_n,
    )
    caption = (
        "<div style='font-size:11px;color:#64748b;margin-top:10px;'>"
        "Ground truth: <code>env._check_success()</code>. All rollouts participate "
        "— pretrained included."
        "</div>"
    )
    return (
        "<div style='padding:18px;background:#0f172a;border:1px solid #1e293b;"
        "border-radius:10px;margin-bottom:18px;'>"
        "<div style='font-size:11px;font-weight:800;color:#c084fc;text-transform:uppercase;"
        "letter-spacing:2px;margin-bottom:12px;'>Pass-1 — binary detector</div>"
        "<div style='display:flex;gap:32px;align-items:flex-start;'>"
        + matrix_html
        + stats_html
        + "</div>"
        + caption
        + "</div>"
    )


def _binary_matrix_html(tp: int, fp: int, fn: int, tn: int) -> str:
    """2x2 confusion matrix, rendered as an HTML grid."""
    log_max = math.log1p(max(tp, fp, fn, tn, 1))

    def cell(count: int, *, correct: bool) -> str:
        intensity = math.log1p(count) / log_max if log_max > 0 else 0.0
        if count == 0:
            bg = "#0f172a"
        elif correct:
            # Green tint scaling with count.
            alpha = int(20 + intensity * 200)
            bg = f"rgba(16, 185, 129, {alpha / 255:.2f})"
        else:
            alpha = int(20 + intensity * 200)
            bg = f"rgba(239, 68, 68, {alpha / 255:.2f})"
        return (
            f"<div style='background:{bg};color:#f1f5f9;padding:18px;text-align:center;"
            f"font-size:22px;font-weight:700;border-radius:6px;"
            f"font-variant-numeric:tabular-nums;border:1px solid #334155;'>{count}</div>"
        )

    label_cell = (
        "color:#94a3b8;font-size:10px;font-weight:700;text-transform:uppercase;"
        "letter-spacing:1.2px;text-align:center;padding:6px;"
    )
    return (
        "<div style='display:grid;grid-template-columns:auto 1fr 1fr;gap:6px;width:280px;'>"
        f"<div></div>"
        f"<div style='{label_cell}'>Judged: pass</div>"
        f"<div style='{label_cell}'>Judged: fail</div>"
        f"<div style='{label_cell};writing-mode:sideways-lr;'>Actual: pass</div>"
        + cell(tn, correct=True)
        + cell(fp, correct=False)
        + f"<div style='{label_cell};writing-mode:sideways-lr;'>Actual: fail</div>"
        + cell(fn, correct=False)
        + cell(tp, correct=True)
        + "</div>"
    )


def _binary_stats_html(
    *,
    prec_correct: int,
    prec_n: int,
    prec_ci: tuple[float, float],
    rec_correct: int,
    rec_n: int,
    rec_ci: tuple[float, float],
    f1: float,
    acc_correct: int,
    acc_n: int,
) -> str:
    """Stats column — every percentage shown as X/Y · Z.Z% with CI for prec & recall."""
    prec = prec_correct / prec_n if prec_n else 0.0
    rec = rec_correct / rec_n if rec_n else 0.0
    acc = acc_correct / acc_n if acc_n else 0.0

    def stat_row(label: str, fraction: str, pct: str, ci: str = "") -> str:
        ci_html = (
            f"<span style='color:#64748b;font-size:11px;margin-left:6px;'>{ci}</span>" if ci else ""
        )
        return (
            "<div style='display:flex;align-items:baseline;gap:10px;padding:6px 0;"
            "border-bottom:1px solid #1e293b;'>"
            f"<div style='width:88px;font-size:11px;color:#94a3b8;text-transform:uppercase;"
            f"letter-spacing:1.2px;font-weight:600;'>{label}</div>"
            f"<div style='font-size:14px;color:#cbd5e1;font-variant-numeric:tabular-nums;"
            f"font-family:ui-monospace,monospace;'>{fraction}</div>"
            f"<div style='font-size:18px;font-weight:700;color:#f1f5f9;"
            f"font-variant-numeric:tabular-nums;'>{pct}</div>"
            f"{ci_html}"
            "</div>"
        )

    rows = [
        stat_row(
            "Precision",
            f"{prec_correct}/{prec_n}",
            f"{prec * 100:.1f}%",
            ci=f"95% CI [{prec_ci[0] * 100:.1f} – {prec_ci[1] * 100:.1f}]",
        ),
        stat_row(
            "Recall",
            f"{rec_correct}/{rec_n}",
            f"{rec * 100:.1f}%",
            ci=f"95% CI [{rec_ci[0] * 100:.1f} – {rec_ci[1] * 100:.1f}]",
        ),
        stat_row("F1", "—", f"{f1:.2f}"),
        stat_row("Accuracy", f"{acc_correct}/{acc_n}", f"{acc * 100:.1f}%"),
    ]
    return "<div style='flex:1;'>" + "".join(rows) + "</div>"


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
                    "font": {"size": 12, "color": "#94a3b8"},
                }
            ],
            plot_bgcolor="#0f172a",
            paper_bgcolor="#0f172a",
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

    fig = go.Figure(
        data=go.Heatmap(
            z=z,
            x=label_strs,
            y=label_strs,
            text=text,
            texttemplate="%{text}",
            textfont={"size": 14, "color": "#f1f5f9"},
            zmin=-1,
            zmax=1,
            colorscale=[
                [0.0, "#9a3412"],  # off-diag, high count -> deep orange
                [0.49, "#1e293b"],  # off-diag, near zero -> background
                [0.5, "#1e293b"],  # zero -> background
                [0.51, "#1e293b"],
                [1.0, "#15803d"],  # diag, high count -> deep green
            ],
            showscale=False,
            hovertemplate="expected: %{y}<br>judged: %{x}<br>count: %{text}<extra></extra>",
            customdata=[[(label_strs[i], label_strs[j]) for j in range(n)] for i in range(n)],
        )
    )
    # Row-total + col-total margin annotations (right side and bottom).
    annotations = []
    for i, total in enumerate(row_totals):
        annotations.append(
            {
                "x": n - 0.5 + 0.6,
                "y": i,
                "text": f"<b>{total}</b>",
                "showarrow": False,
                "xref": "x",
                "yref": "y",
                "font": {"size": 11, "color": "#94a3b8"},
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
                "font": {"size": 11, "color": "#94a3b8"},
                "yanchor": "top",
            }
        )

    fig.update_layout(
        xaxis={
            "title": {"text": "Judged label", "font": {"color": "#94a3b8", "size": 12}},
            "tickangle": -30,
            "tickfont": {"color": "#cbd5e1", "size": 11},
            "side": "top",
        },
        yaxis={
            "title": {"text": "Expected label", "font": {"color": "#94a3b8", "size": 12}},
            "autorange": "reversed",
            "tickfont": {"color": "#cbd5e1", "size": 11},
        },
        margin={"l": 140, "r": 60, "t": 100, "b": 60},
        plot_bgcolor="#0f172a",
        paper_bgcolor="#0f172a",
        height=460,
        annotations=annotations,
    )
    return fig


# ---- Per-label table -------------------------------------------------------------


def render_per_label_table(rollouts: list[ScoredRollout]) -> str:
    """Per-label support / predicted-as / P / R / F1 table.

    Uses src.metrics.per_label for the stats; renders as HTML so we can apply
    the muted-on-low-support styling the spec wants.
    """
    labeled = to_labeled_rollouts(rollouts)
    metrics = compute_label_metrics(labeled)

    # Pre-compute predicted-as counts (= tp + fp for each label).
    rows: list[str] = [
        "<div style='display:grid;grid-template-columns:1.6fr 0.7fr 0.9fr 1.2fr 1.2fr 0.6fr;"
        "gap:8px;padding:8px 12px;color:#94a3b8;font-size:10px;font-weight:700;"
        "text-transform:uppercase;letter-spacing:1.2px;border-bottom:1px solid #334155;'>"
        "<div>Label</div><div>Support</div><div>Predicted as</div>"
        "<div>Precision</div><div>Recall</div><div>F1</div>"
        "</div>"
    ]
    if not metrics.per_label:
        rows.append(
            "<div style='padding:14px;color:#94a3b8;font-style:italic;text-align:center;'>"
            "(no labels with judged-vs-expected pairs yet)</div>"
        )
    for stats in metrics.per_label:
        rows.append(_per_label_row(stats))

    return (
        "<div style='padding:14px;background:#0f172a;border:1px solid #1e293b;"
        "border-radius:10px;margin-bottom:18px;'>"
        "<div style='font-size:11px;font-weight:800;color:#fb923c;text-transform:uppercase;"
        "letter-spacing:2px;margin-bottom:10px;'>Pass-2 — per-label breakdown</div>"
        + "".join(rows)
        + "</div>"
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

    text_color = "#94a3b8" if small else "#cbd5e1"
    label_color = "#94a3b8" if small else "#f1f5f9"

    chip = (
        "<span style='margin-left:6px;font-size:9px;color:#94a3b8;background:#334155;"
        "padding:1px 5px;border-radius:6px;text-transform:none;letter-spacing:0;'>"
        "small sample</span>"
        if small
        else ""
    )

    cell = (
        f"font-variant-numeric:tabular-nums;font-family:ui-monospace,monospace;"
        f"font-size:12px;color:{text_color};"
    )
    return (
        "<div style='display:grid;grid-template-columns:1.6fr 0.7fr 0.9fr 1.2fr 1.2fr 0.6fr;"
        "gap:8px;padding:8px 12px;align-items:baseline;"
        "border-bottom:1px solid #1e293b;'>"
        f"<div style='font-family:ui-monospace,monospace;font-size:13px;color:{label_color};"
        f"font-weight:600;'>{label_str}{chip}</div>"
        f"<div style='{cell}'>{support}</div>"
        f"<div style='{cell}'>{predicted_as}</div>"
        f"<div style='{cell}'>{prec_frac}"
        f"<span style='margin-left:6px;color:#94a3b8;'>{prec_pct}</span></div>"
        f"<div style='{cell}'>{rec_frac}"
        f"<span style='margin-left:6px;color:#94a3b8;'>{rec_pct}</span></div>"
        f"<div style='{cell};color:{label_color};'>{f1}</div>"
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
        # Compute judged for filtering purposes.
        if r.pass1_verdict == "pass":
            jud = "none"
        elif r.pass2_label:
            jud = r.pass2_label
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


def render_drill_down(
    rollouts: list[ScoredRollout],
    f: DrillFilter,
    keyframes: dict[str, Path],
) -> str:
    if not f.is_active:
        return (
            "<div style='padding:24px;text-align:center;color:#94a3b8;font-style:italic;'>"
            "Click a confusion-matrix cell or a label row to inspect the rollouts behind it."
            "</div>"
        )

    matches = filter_rollouts(rollouts, f)
    if not matches:
        return (
            "<div style='padding:18px;color:#94a3b8;font-style:italic;'>"
            "Filter active but no rollouts match. Try Clear filter."
            "</div>"
        )

    rows: list[str] = [
        "<div style='display:grid;grid-template-columns:160px 1.4fr 1.4fr 0.9fr 0.9fr 2fr;"
        "gap:10px;padding:8px 10px;color:#94a3b8;font-size:10px;font-weight:700;"
        "text-transform:uppercase;letter-spacing:1.2px;border-bottom:1px solid #334155;'>"
        "<div>Keyframe</div><div>Rollout</div><div>Expected → Judged</div>"
        "<div>Policy</div><div>Match</div><div>Pass-2 description</div>"
        "</div>"
    ]
    for r in matches:
        rows.append(_drill_row(r, keyframes))
    return (
        "<div style='padding:14px;background:#0f172a;border:1px solid #1e293b;"
        "border-radius:10px;'>" + "".join(rows) + "</div>"
    )


def _drill_row(r: ScoredRollout, keyframes: dict[str, Path]) -> str:
    expected = r.ground_truth_label or "—"
    if r.pass1_verdict == "pass":
        judged = "none"
    elif r.pass2_label:
        judged = r.pass2_label
    else:
        judged = "(pending)"

    match = expected == judged
    badge_color = "#15803d" if match else "#9a3412"
    badge_text = "match" if match else "mismatch"

    kf = keyframes.get(r.rollout_id)
    img_html = (
        f"<img src='/gradio_api/file={kf}' style='width:140px;height:auto;border-radius:4px;"
        f"border:1px solid #334155;'/>"
        if kf is not None
        else "<div style='width:140px;height:80px;background:#1e293b;border-radius:4px;"
        "color:#475569;font-size:10px;display:flex;align-items:center;justify-content:center;'>"
        "no keyframe</div>"
    )
    # Copyable host paths under the thumbnail (in the keyframe column).
    paths_block = ""
    if r.video_path_host:
        paths_block += copyable_path(r.video_path_host, click_label="copy mp4", max_width_px=140)
    if kf is not None:
        paths_block += copyable_path(kf, click_label="copy png", max_width_px=140)

    mp4_link = (
        f"<a href='/gradio_api/file={r.video_path_host}' target='_blank' style='color:#60a5fa;"
        f"text-decoration:none;'>{r.rollout_id}</a>"
        if r.video_path_host
        else r.rollout_id
    )

    desc = (r.pass2_description or "—")[:160]

    return (
        "<div style='display:grid;grid-template-columns:160px 1.4fr 1.4fr 0.9fr 0.9fr 2fr;"
        "gap:10px;padding:10px;align-items:start;border-bottom:1px solid #1e293b;'>"
        f"<div>{img_html}{paths_block}</div>"
        f"<div style='font-family:ui-monospace,monospace;font-size:12px;color:#cbd5e1;'>"
        f"{mp4_link}</div>"
        f"<div style='font-family:ui-monospace,monospace;font-size:11px;color:#cbd5e1;'>"
        f"{expected} → {judged}</div>"
        f"<div style='font-family:ui-monospace,monospace;font-size:11px;color:#94a3b8;'>"
        f"{r.policy_kind}</div>"
        f"<div><span style='display:inline-block;padding:2px 8px;border-radius:10px;"
        f"background:{badge_color}33;color:#f1f5f9;font-size:10px;font-weight:700;"
        f"text-transform:uppercase;letter-spacing:1px;'>{badge_text}</span></div>"
        f"<div style='font-size:12px;color:#cbd5e1;line-height:1.4;'>{desc}</div>"
        "</div>"
    )


# ---- Top-level render orchestrator (everything except the heatmap, which is gr.Plot) -----


def render_static_blocks(
    rollouts: list[ScoredRollout],
    binary_metrics: JudgeMetrics,
) -> tuple[str, str, str, str]:
    """Render the four HTML blocks: cohort, caption, binary panel, per-label table."""
    counts = cohort_counts(rollouts)
    return (
        render_cohort_strip(counts),
        render_caption(),
        render_binary_panel(binary_metrics),
        render_per_label_table(rollouts),
    )


def keyframes_dir(mirror_root: Path) -> Path:
    return mirror_root / KEYFRAMES_DIR_NAME
