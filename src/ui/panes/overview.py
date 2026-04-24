"""Overview — landing pane.

DESIGN.md §6: "large headline, KPI strip, 4-card pipeline, 3-card view index".

The KPI strip re-uses the same hero primitives as the run-level pages so the
user can land on Overview and still see the one-glance cost/time/scenarios
pair; the pipeline shows the four phases in their current state; the view-
index points at the other three tabs.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.costing import (
    baseline_cost_for,
    baseline_seconds_for,
    baseline_time_seconds_for_videos,
    estimated_video_duration_s,
    format_cost,
    format_duration,
)
from src.ui.panes._io import read_runtime
from src.ui.styles import chip, html_escape, num
from src.ui.synthesis import (
    cluster_by_label,
    cohort_split,
    load_scored_rollouts,
)


def overview_html(mirror_root: Path) -> str:
    """Render the landing pane against the currently-selected run."""
    rt = read_runtime(mirror_root)
    rollouts = load_scored_rollouts(mirror_root)

    cost = float(rt.get("cost_usd", 0.0))
    elapsed = float(rt.get("elapsed_seconds", 0.0))
    n = int(rt.get("n_rollouts", 0))
    n_cal, n_dep = cohort_split(rollouts)
    n_clusters = len(cluster_by_label(rollouts)) if rollouts else 0

    durations = [estimated_video_duration_s(r.env_name, r.steps_taken or None) for r in rollouts]
    baseline_time = (
        baseline_time_seconds_for_videos(durations) if durations else baseline_seconds_for(n)
    )
    baseline_cost = baseline_cost_for(n)
    cost_save = max(baseline_cost - cost, 0.0)
    time_save = max(baseline_time - elapsed, 0.0)

    return (
        _overview_headline(n_cal, n_dep)
        + _kpi_strip(cost, cost_save, elapsed, time_save, n, n_clusters)
        + _pipeline_cards(rt)
    )


def _overview_headline(n_cal: int, n_dep: int) -> str:
    cal_chip = chip(f"{n_cal} calibration", variant="cal")
    dep_chip = chip(f"{n_dep} deployment", variant="dep")
    return (
        '<div style="margin-bottom:var(--pg-s-6);">'
        '<div class="pg-hero-eyebrow-row">RUN OVERVIEW</div>'
        '<div class="pg-hero-chiprow" style="margin-top:var(--pg-s-4);">'
        f"{cal_chip}{dep_chip}"
        "</div>"
        "</div>"
    )


def _kpi_strip(
    cost: float,
    cost_save: float,
    elapsed: float,
    time_save: float,
    n: int,
    n_clusters: int,
) -> str:
    def cell(lbl: str, val: str, sub: str) -> str:
        return (
            '<div class="pg-kpi-cell">'
            f'<div class="pg-kpi-cell-lbl">{lbl}</div>'
            f'<div class="pg-kpi-cell-val">{val}</div>'
            f'<div class="pg-kpi-cell-sub">{sub}</div>'
            "</div>"
        )

    saved_cost = f"{num(html_escape(format_cost(cost_save)))} saved vs manual"
    saved_time = f"{num(html_escape(format_duration(time_save)))} saved vs manual"
    scenarios_sub = "pipeline scenarios this run"
    clusters_sub = "distinct failure modes"
    return (
        '<div class="pg-kpi-grid">'
        + cell("Cost", num(html_escape(format_cost(cost))), saved_cost)
        + cell("Wall time", num(html_escape(format_duration(elapsed))), saved_time)
        + cell("Scenarios", num(str(n)), scenarios_sub)
        + cell("Clusters", num(str(n_clusters)), clusters_sub)
        + "</div>"
    )


def _pipeline_cards(rt: dict[str, Any]) -> str:
    """4-card strip: planner / rollout / judge / report with current counters."""
    n_roll = int(rt.get("n_rollouts_dispatched", 0) or 0)
    n_judge = int(rt.get("n_judge_dispatched", 0) or 0)
    n_judge_planned = int(rt.get("n_judge_planned", 0) or 0)
    planned = rt.get("planned_total")

    def card(phase: str, title: str, top: str, bottom: str) -> str:
        return (
            f'<div class="pg-card" style="border-left:3px solid var(--pg-phase-{phase});">'
            f'<div style="font-family:var(--pg-font-mono);font-size:var(--pg-fs-micro);'
            "letter-spacing:0.16em;text-transform:uppercase;"
            f'color:var(--pg-phase-{phase});">{title.upper()}</div>'
            f'<div style="font-family:var(--pg-font-display);font-size:22px;'
            f'margin-top:var(--pg-s-2);color:var(--pg-ink);">{top}</div>'
            f'<div style="font-size:var(--pg-fs-xs);color:var(--pg-ink-4);'
            f'margin-top:4px;">{bottom}</div>'
            "</div>"
        )

    planner_sub = f"designed {num(str(planned))} scenarios" if planned else "designing suite…"
    planner_top = "Plan drafted" if planned else "Pending"
    rollout_sub = f"of {num(str(planned))} planned" if planned else "— no denominator yet"
    judge_sub = (
        f"of {num(str(n_judge_planned))} sim failures"
        if n_judge_planned
        else "waiting on sim failures"
    )

    return (
        '<div class="pg-pipeline-grid">'
        + card("planner", "Planner", planner_top, planner_sub)
        + card("rollout", "Rollout", f"{num(str(n_roll))} executed", rollout_sub)
        + card("judge", "Judge", f"{num(str(n_judge))} calls", judge_sub)
        + card(
            "report",
            "Report",
            "pending" if rt.get("phase") != "complete" else "complete",
            "final narrative + numbers",
        )
        + "</div>"
    )
