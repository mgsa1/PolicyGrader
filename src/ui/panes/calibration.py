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
    render_drill_down,
    render_heatmap_figure,
    render_judge_calibration_header,
    render_static_blocks,
)
from src.ui.styles import empty, html_escape
from src.ui.synthesis import compute_metrics, load_scored_rollouts, render_all_keyframes


def calibration_header_html() -> str:
    """Top-of-tab purpose strip, handed straight through from metrics_view."""
    return render_judge_calibration_header()


def metrics_blocks(mirror_root: Path) -> tuple[str, str, str, str]:
    """(cohort, caption, binary_panel, per_label_table) HTML for the tab body."""
    rollouts = load_scored_rollouts(mirror_root)
    if not rollouts:
        return (
            empty(
                "Metrics appear once the orchestrator has run rollouts AND the judge has finished."
            ),
            "",
            "",
            "",
        )
    binary = compute_metrics(rollouts)
    return render_static_blocks(rollouts, binary)


def heatmap_figure(mirror_root: Path) -> Any:
    """Plotly confusion-matrix figure (legacy; replaced by clickable_grid_data)."""
    return render_heatmap_figure(load_scored_rollouts(mirror_root))


# ---- Clickable confusion matrix --------------------------------------------------

# Fixed 9-label list in canonical order. Buttons in build_app are pre-allocated
# against this list; visibility is toggled per tick based on used_mask.
def all_labels() -> list[str]:
    """All FailureMode labels in canonical order (length 9). Stable across runs."""
    from src.ui.metrics_view import _taxonomy_order

    return [m.value for m in _taxonomy_order()]


def clickable_grid_data(mirror_root: Path) -> tuple[list[dict[str, Any]], list[bool]]:
    """Return (cells, used_mask) for the clickable confusion matrix.

    `cells` is a row-major list of length 81 — one dict per (expected, judged)
    pair in canonical order. Each dict carries: count, diag, show.
    `used_mask` is length 9 — True when that label appears in the data.
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


def drill_description_html() -> str:
    return (
        '<div style="font-size:13px;color:var(--pg-ink-3);'
        'margin:var(--pg-s-4) 0 var(--pg-s-3) 0;line-height:1.5;">'
        "Pick an expected / judged pair (or either alone) to see the "
        "calibration rollouts behind the number. Leave both blank to clear."
        "</div>"
    )


def heatmap_caption_html() -> str:
    return (
        '<div style="font-size:13px;color:var(--pg-ink-3);'
        'margin:var(--pg-s-4) 0 var(--pg-s-2) 0;line-height:1.5;">'
        "<b>Pass-2 — multiclass confusion.</b> Rows = expected, cols = judged. "
        "Diagonal (green) = matches, off-diagonal (red) = mis-labels. "
        "Zero cells are neutral with a middle dot."
        "</div>"
    )
