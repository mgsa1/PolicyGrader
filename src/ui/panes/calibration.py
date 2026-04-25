"""Judge calibration pane — KPI row · 2×2 binary · heatmap · per-label · drill.

Most of the heavy data+render logic already lives in `src/ui/metrics_view.py`
(it has its own tests). This pane is a thin facade that exposes the four
block-level renderers the tab composes, plus the drill-filter wiring.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.ui.metrics_view import (
    DrillFilter,
    binary_confusion,
    render_binary_matrix,
    render_drill_down,
    render_heatmap_figure,
    render_judge_calibration_header,
    render_static_blocks,
)
from src.ui.styles import empty, html_escape
from src.ui.synthesis import load_scored_rollouts, render_all_keyframes


def calibration_header_html() -> str:
    """Top-of-tab purpose strip, handed straight through from metrics_view."""
    return render_judge_calibration_header()


def metrics_blocks(mirror_root: Path) -> tuple[str, str, str]:
    """(cohort, caption, per_label_table) HTML for the tab body.

    Binary panel retired with the single-pass CoT migration — sim owns the
    binary verdict, so the only worthwhile metric here is the multiclass
    label breakdown.
    """
    rollouts = load_scored_rollouts(mirror_root)
    if not rollouts:
        return (
            empty(
                "Metrics appear once the orchestrator has run rollouts AND the judge has finished."
            ),
            "",
            "",
        )
    return render_static_blocks(rollouts)


def binary_matrix_html(mirror_root: Path) -> str:
    """At-a-glance 2×2 confusion of the judge's binary verdict vs sim ground truth."""
    return render_binary_matrix(binary_confusion(load_scored_rollouts(mirror_root)))


def heatmap_figure(mirror_root: Path) -> Any:
    """Plotly confusion-matrix figure (legacy; replaced by clickable_grid_data)."""
    return render_heatmap_figure(load_scored_rollouts(mirror_root))


# ---- Clickable confusion matrix --------------------------------------------------


# Full taxonomy label list in canonical order. Length grows/shrinks with the
# FailureMode enum — callers that need a matrix grid should use
# `_taxonomy_order()` and `_used_labels()` directly rather than hardcoding a
# dimension.
def all_labels() -> list[str]:
    """All FailureMode labels in canonical order. Stable across runs."""
    from src.ui.metrics_view import _taxonomy_order

    return [m.value for m in _taxonomy_order()]


def matrix_html(mirror_root: Path) -> str:
    """Single-block HTML confusion matrix using CSS Grid.

    Each cell is an HTML <button>; the onclick fires a JS bridge that sets a
    hidden gr.Textbox's value (the textbox's `.input` handler in build_app
    does the actual drill filter + table update). One gr.HTML widget instead
    of 99 widgets — much tighter layout, no inter-row gaps from Gradio.
    """
    from src.metrics import compute as compute_label_metrics
    from src.ui.metrics_view import _taxonomy_order, _used_labels, to_labeled_rollouts

    rollouts = load_scored_rollouts(mirror_root)
    labeled = to_labeled_rollouts(rollouts)
    metrics = compute_label_metrics(labeled)
    order = _taxonomy_order()
    used = _used_labels(metrics, order)

    if not used:
        return (
            "<div class='pg-cm-empty'>"
            "Confusion matrix populates once the judge has scored at least "
            "one calibration rollout."
            "</div>"
        )

    n = len(used)
    grid_cols = f"220px repeat({n}, 78px)"

    # JS bridge — defined once via window guard so re-renders are idempotent.
    bridge = (
        "<script>"
        "if (!window.pgCmClick) { window.pgCmClick = function(exp, jud) {"
        "  const root = document.getElementById('pg-cm-payload');"
        "  if (!root) return;"
        "  const ta = root.querySelector('textarea, input');"
        "  if (!ta) return;"
        "  const seq = (parseInt(ta.dataset.seq || '0') + 1).toString();"
        "  ta.dataset.seq = seq;"
        "  ta.value = seq + '|' + exp + '::' + jud;"
        "  ta.dispatchEvent(new Event('input', {bubbles: true}));"
        "} }"
        "</script>"
    )

    parts: list[str] = [
        bridge,
        "<div class='pg-cm-axes'>",
        # Y-axis title (rotated, ground truth = expected = rows)
        "<div class='pg-cm-yaxis-title'><span>Ground truth (expected)</span></div>",
        "<div class='pg-cm-axes-inner'>",
        # X-axis title (predicted = judged = columns)
        "<div class='pg-cm-xaxis-title'>Predicted (judged)</div>",
        f"<div class='pg-cm-grid' style='grid-template-columns:{grid_cols};'>",
    ]

    # Top-left corner + col headers
    parts.append("<div class='pg-cm-corner'></div>")
    for jud in used:
        parts.append(f"<div class='pg-cm-colhead'><span>{html_escape(jud.value)}</span></div>")

    # Body rows
    for exp in used:
        parts.append(f"<div class='pg-cm-rowhead'>{html_escape(exp.value)}</div>")
        for jud in used:
            count = metrics.confusion.get(exp, {}).get(jud, 0)
            diag = exp == jud
            classes = ["pg-cm-cell"]
            if diag:
                classes.append("diag" if count > 0 else "diag-zero")
            else:
                classes.append("miss" if count > 0 else "empty")
            label = str(count) if count > 0 else "·"
            click_args = f"'{exp.value}','{jud.value}'"
            parts.append(
                f"<button type='button' class='{' '.join(classes)}' "
                f'onclick="pgCmClick({click_args})">{label}</button>'
            )

    parts.append("</div>")  # .pg-cm-grid
    parts.append("</div>")  # .pg-cm-axes-inner
    parts.append("</div>")  # .pg-cm-axes
    return "".join(parts)


def clickable_grid_data(mirror_root: Path) -> tuple[list[dict[str, Any]], list[bool]]:
    """Return (cells, used_mask) for the clickable confusion matrix.

    `cells` is a row-major list with N*N entries — one dict per (expected,
    judged) pair in canonical order, where N is the number of taxonomy labels
    (`_taxonomy_order()`). Each dict carries: count, diag, show.
    `used_mask` is length N — True when that label appears in the data.
    Headers (rows + cols) get hidden where used_mask is False; non-shown cells
    likewise.
    """
    from src.metrics import compute as compute_label_metrics
    from src.ui.metrics_view import _taxonomy_order, _used_labels, to_labeled_rollouts

    rollouts = load_scored_rollouts(mirror_root)
    labeled = to_labeled_rollouts(rollouts)
    metrics = compute_label_metrics(labeled)
    order = _taxonomy_order()
    used = set(_used_labels(metrics, order))
    used_mask = [m in used for m in order]

    cells: list[dict[str, Any]] = []
    for exp in order:
        for jud in order:
            count = metrics.confusion.get(exp, {}).get(jud, 0)
            cells.append(
                {
                    "expected": exp.value,
                    "judged": jud.value,
                    "count": count,
                    "diag": exp == jud,
                    "show": (exp in used) and (jud in used),
                }
            )
    return cells, used_mask


def heatmap_labels(mirror_root: Path) -> list[str]:
    """Labels currently on the heatmap axes, for the drill-down dropdowns."""
    from src.metrics import compute as compute_label_metrics
    from src.ui.metrics_view import _taxonomy_order, _used_labels, to_labeled_rollouts

    rollouts = load_scored_rollouts(mirror_root)
    labeled = to_labeled_rollouts(rollouts)
    metrics = compute_label_metrics(labeled)
    used = _used_labels(metrics, _taxonomy_order())
    return [lab.value for lab in used]


def drill_html(mirror_root: Path, f: DrillFilter) -> str:
    """Drill-down table — renders with keyframes for each matched rollout."""
    rollouts = load_scored_rollouts(mirror_root)
    keyframes = render_all_keyframes(rollouts, mirror_root)
    return render_drill_down(rollouts, f, keyframes)


def filter_status_html(f: DrillFilter) -> str:
    """Small status pill showing the active drill filter, or empty if none."""
    if not f.is_active:
        return ""
    return (
        '<div class="pg-filter-pill">'
        '<span class="pg-filter-pill-lbl">Filter active:</span>'
        f'<span class="pg-filter-pill-val">{html_escape(f.label_text())}</span>'
        "</div>"
    )


def heatmap_legend_html() -> str:
    """Compact 3-swatch legend rendered next to the matrix eyebrow."""
    return (
        '<span style="display:inline-flex;align-items:center;gap:10px;'
        'font-size:11px;color:var(--pg-ink-4);margin-left:12px;">'
        '<span style="display:inline-flex;align-items:center;gap:4px;">'
        '<span style="width:10px;height:10px;background:var(--pg-ok);'
        'border-radius:2px;"></span>match</span>'
        '<span style="display:inline-flex;align-items:center;gap:4px;">'
        '<span style="width:10px;height:10px;background:var(--pg-err);'
        'border-radius:2px;"></span>miss</span>'
        '<span style="display:inline-flex;align-items:center;gap:4px;">'
        '<span style="opacity:0.5;">·</span>zero</span>'
        "</span>"
    )
