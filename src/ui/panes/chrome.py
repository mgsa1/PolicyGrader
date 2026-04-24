"""Shared chrome: topbar, hero banner, phase-progress strip, scope strip,
judge-trust banner.

Every run-level page wears the same chrome. Keeping it in one module means a
tweak to the hero hierarchy (DESIGN.md §1) lands once, not three times.
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
from src.ui import styles
from src.ui.metrics_view import (
    judge_trust,
    render_judge_trust_banner,
    wilson_ci_95,
)
from src.ui.panes._io import read_runtime
from src.ui.styles import html_escape, num
from src.ui.synthesis import (
    cluster_by_label,
    cohort_split,
    compute_metrics,
    load_scored_rollouts,
)

# ---- Phase marker → code mapping ------------------------------------------------
# Maps the orchestrator-emitted phase strings to the four short codes that the
# CSS (memories tree, agent trace, phase chip) keys off.

_MARKER_TO_CODE: dict[str, str] = {
    "BEGIN PHASE 1: PLANNER": "planner",
    "BEGIN PHASE 2: ROLLOUT": "rollout",
    "BEGIN PHASE 3: JUDGE": "judge",
    "BEGIN PHASE 4: REPORT": "report",
}

_CODE_ORDER: dict[str, int] = {"planner": 0, "rollout": 1, "judge": 2, "report": 3}


def phase_code(marker: str) -> str | None:
    """Return the short code ('planner'/'rollout'/'judge'/'report') or None."""
    return _MARKER_TO_CODE.get(marker)


def phase_short(phase: str) -> str:
    """Human-readable short label for a phase marker."""
    code = phase_code(phase)
    if code:
        idx = _CODE_ORDER[code] + 1
        return f"Phase {idx}: {code.capitalize()}"
    if phase == "starting":
        return "Starting"
    if phase == "complete":
        return "Complete"
    return phase or "Idle"


# ---- Topbar ----------------------------------------------------------------------


def topbar_brand_html() -> str:
    """PG monogram + wordmark. Left side of the topbar."""
    return (
        '<div class="pg-brand">'
        f"{styles.monogram()}"
        "<div>"
        '<div class="pg-brand-name">PolicyGrader</div>'
        '<div class="pg-brand-sub">Embodied eval orchestrator</div>'
        "</div>"
        "</div>"
    )


def topbar_meta_html(mirror_root: Path) -> str:
    """Right side of the topbar — elapsed time chip + phase pill."""
    rt = read_runtime(mirror_root)
    elapsed = float(rt.get("elapsed_seconds") or 0.0)
    phase = str(rt.get("phase") or "idle")
    return (
        '<div style="display:inline-flex;align-items:center;gap:14px;">'
        f'<span class="pg-session-pill">{num(html_escape(format_duration(elapsed)))} elapsed</span>'
        f'<span class="pg-phase-pill">{html_escape(phase_short(phase))}</span>'
        "</div>"
    )


# ---- Hero banner (run-level pages) ----------------------------------------------


def hero_html(mirror_root: Path) -> str:
    """The run-level hero: eyebrow + headline + sub + cohort chips + metrics card.

    Hierarchy per DESIGN.md §1:
      1. Hero — cost/time savings + "hours to minutes" headline
      2. Precision/recall against injected ground truth  (right-card cells)
      3. Live cost · time · scenarios                    (right-card cells)
      4. Cluster counts                                   (right-card cells)
    """
    rt = read_runtime(mirror_root)
    rollouts = load_scored_rollouts(mirror_root)
    run_id = str(rt.get("run_id") or "—")

    cost = float(rt.get("cost_usd", 0.0))
    elapsed = float(rt.get("elapsed_seconds", 0.0))
    n = int(rt.get("n_rollouts", 0))
    n_cal, n_dep = cohort_split(rollouts)

    durations = [estimated_video_duration_s(r.env_name, r.steps_taken or None) for r in rollouts]
    baseline_time = (
        baseline_time_seconds_for_videos(durations) if durations else baseline_seconds_for(n)
    )
    baseline_cost = baseline_cost_for(n)
    cost_save_pct = ((baseline_cost - cost) / baseline_cost * 100) if baseline_cost > 0 else 0.0
    time_save_pct = ((baseline_time - elapsed) / baseline_time * 100) if baseline_time > 0 else 0.0

    metrics = compute_metrics(rollouts) if rollouts else None
    trust = judge_trust(rollouts) if rollouts else None
    if metrics and metrics.n_labeled > 0:
        acc = metrics.label_accuracy or 0.0
        acc_pct = f"{acc * 100:.0f}"
        acc_lo, acc_hi = wilson_ci_95(metrics.label_correct, metrics.n_labeled)
        acc_ci = f"CI {int(acc_lo * 100)}–{int(acc_hi * 100)}"
    else:
        acc_pct, acc_ci = "—", "no data"
    if trust and trust.per_label_recall_avg is not None:
        r_pct = f"{trust.per_label_recall_avg * 100:.0f}"
        r_ci = f"{trust.n_labels_with_support} labels · support ≥ 3"
    else:
        r_pct, r_ci = "—", "no data"
    n_clusters = len(cluster_by_label(rollouts)) if rollouts else 0

    if metrics and metrics.n_labeled > 0:
        agree = (
            f"agreed with injected ground truth on <b>{metrics.label_correct} of "
            f"{metrics.n_labeled}</b> calibration rollouts."
        )
    else:
        agree = "judge calibration runs once Phase 3 finishes."

    return (
        '<div class="pg-hero-banner">'
        + _hero_left(run_id, n, n_cal, n_dep, agree, acc_pct, r_pct)
        + _hero_right(
            cost,
            baseline_cost,
            cost_save_pct,
            elapsed,
            baseline_time,
            time_save_pct,
            n,
            n_cal,
            n_dep,
            acc_pct,
            acc_ci,
            r_pct,
            r_ci,
            n_clusters,
        )
        + "</div>"
    )


def _hero_left(
    run_id: str,
    n: int,
    n_cal: int,
    n_dep: int,
    agree: str,
    acc_pct: str,
    r_pct: str,
) -> str:
    cal_chip = styles.chip(f"{n_cal} calibration", variant="cal")
    dep_chip = styles.chip(f"{n_dep} deployment", variant="dep")
    pr_chip = styles.chip(f"acc {acc_pct}% · R {r_pct}%", variant="ok") if acc_pct != "—" else ""
    return (
        '<div class="pg-hero-left">'
        f'<div class="pg-hero-eyebrow-row">LIVE · SESSION '
        f"<code>{html_escape(run_id.upper())}</code></div>"
        '<h1 class="pg-hero-headline">Robot eval review,<br/>'
        "<em>hours to minutes.</em></h1>"
        '<div class="pg-hero-sub">'
        f"An Opus 4.7 agent designed the test suite, ran <b>{n}</b> rollouts, "
        f"watched every failure in a single dense-frame CoT pass, and {agree}"
        "</div>"
        '<div class="pg-hero-chiprow">'
        f"{cal_chip}{dep_chip}{pr_chip}"
        "</div>"
        "</div>"
    )


def _hero_right(
    cost: float,
    baseline_cost: float,
    cost_save_pct: float,
    elapsed: float,
    baseline_time: float,
    time_save_pct: float,
    n: int,
    n_cal: int,
    n_dep: int,
    acc_pct: str,
    acc_ci: str,
    r_pct: str,
    r_ci: str,
    n_clusters: int,
) -> str:
    def cell(label: str, value: str, sub: str) -> str:
        return (
            '<div class="pg-metric-cell">'
            f'<div class="pg-metric-cell-lbl">{label}</div>'
            f'<div class="pg-metric-cell-val">{value}</div>'
            f'<div class="pg-metric-cell-sub">{sub}</div>'
            "</div>"
        )

    cost_sub = (
        f"<s>{html_escape(format_cost(baseline_cost))}</s> "
        f'<span class="delta">−{cost_save_pct:.0f}%</span>'
    )
    time_sub = (
        f"<s>{html_escape(format_duration(baseline_time))}</s> "
        f'<span class="delta">−{time_save_pct:.0f}%</span>'
    )
    scen_sub = (
        f'<span style="color:var(--pg-cal);">{num(str(n_cal))} cal</span> · '
        f'<span style="color:var(--pg-dep);">{num(str(n_dep))} dep</span>'
    )

    acc_value = f'{num(acc_pct)}<span class="unit">%</span>' if acc_pct != "—" else "—"
    r_value = f'{num(r_pct)}<span class="unit">%</span>' if r_pct != "—" else "—"

    return (
        '<div class="pg-hero-right">'
        '<div class="pg-hero-right-eyebrow">This run vs manual review</div>'
        '<div class="pg-metric-grid">'
        + cell("Cost", num(html_escape(format_cost(cost))), cost_sub)
        + cell("Wall time", num(html_escape(format_duration(elapsed))), time_sub)
        + cell("Scenarios", num(str(n)), scen_sub)
        + cell("Label accuracy", acc_value, acc_ci)
        + cell("Avg recall", r_value, r_ci)
        + cell("Clusters", num(str(n_clusters)), "from 1M ctx")
        + "</div>"
        "</div>"
    )


# ---- Phase progress strip -------------------------------------------------------


def phase_progress_html(mirror_root: Path) -> str:
    """The 4-phase chip row under the hero."""
    rt = read_runtime(mirror_root)
    cur = str(rt.get("phase", "starting"))
    n_roll = int(rt.get("n_rollouts_dispatched", 0))
    n_judge = int(rt.get("n_judge_dispatched", 0))
    n_judge_planned = int(rt.get("n_judge_planned", 0))
    planned: int | None = rt.get("planned_total")

    cur_code = phase_code(cur)
    cur_idx = _CODE_ORDER.get(cur_code, -1) if cur_code else (-1 if cur != "complete" else 4)
    rollout_total = planned if cur_idx <= 1 else (n_roll if n_roll > 0 else planned)

    def state_for(idx: int) -> str:
        if cur_idx > idx:
            return "complete"
        if cur_idx == idx:
            return "active"
        return "pending"

    planner = styles.phase_chip("planner", state_for(0))
    rollout = styles.phase_chip(
        "rollout",
        state_for(1),
        counter=(
            f"{n_roll} / {rollout_total}"
            if rollout_total
            else (f"{n_roll} done" if n_roll else None)
        ),
    )
    if rollout_total and state_for(1) == "active":
        rollout = _append_bar(rollout, "rollout", n_roll, rollout_total)
    judge_total = n_judge_planned or None
    judge_sub = f"{n_judge}/{judge_total or '?'} failed rollouts judged"
    judge = styles.phase_chip(
        "judge",
        state_for(2),
        counter=(
            f"{n_judge} / {judge_total}"
            if judge_total
            else (f"{n_judge} done" if n_judge else None)
        ),
        sub=judge_sub,
    )
    if judge_total and state_for(2) == "active":
        judge = _append_bar(judge, "judge", n_judge, judge_total)
    report = styles.phase_chip("report", state_for(3))

    return f'<div class="pg-phase-strip">{planner}{rollout}{judge}{report}</div>'


def _append_bar(chip_html: str, phase: str, done: int, total: int) -> str:
    """Insert a phase-colored progress bar just before the closing `</div>`."""
    bar = styles.phase_progress_bar(phase, done, total)
    return chip_html[:-6] + bar + "</div>"


# ---- Scope strip (Judge calibration / Findings top) -----------------------------


def scope_strip_html(mirror_root: Path, scope: str) -> str:
    """Big cohort-denominator strip at the top of a run-level tab.

    `scope` ∈ {'calibration', 'deployment'}. Colored via the cohort tokens
    (amber for cal, blue for dep).
    """
    rollouts = load_scored_rollouts(mirror_root)
    if scope == "calibration":
        cohort = [r for r in rollouts if r.population == "calibration"]
        n_videos = len(cohort)
        n_failures = sum(1 for r in cohort if r.is_failure)
        label = "Calibration cohort"
        fail_cap = "env-reported failures (ground truth)"
        modifier = "cal"
    elif scope == "deployment":
        cohort = [r for r in rollouts if r.population == "deployment"]
        n_videos = len(cohort)
        n_failures = sum(1 for r in cohort if r.judged_failure)
        label = "Deployment cohort"
        fail_cap = "rollouts the judge flagged as failure"
        modifier = "dep"
    else:
        raise ValueError(f"unknown scope: {scope!r}")

    return (
        f'<div class="pg-scope-strip {modifier}">'
        f'<div class="pg-scope-label">{label}</div>'
        '<div class="pg-scope-nums">'
        '<div class="pg-scope-num">'
        f'<div class="pg-scope-num-val">{num(str(n_videos))}</div>'
        '<div class="pg-scope-num-cap">videos in scope</div>'
        "</div>"
        '<div class="pg-scope-sep">·</div>'
        '<div class="pg-scope-num">'
        f'<div class="pg-scope-num-val">{num(str(n_failures))}</div>'
        f'<div class="pg-scope-num-cap">{html_escape(fail_cap)}</div>'
        "</div>"
        "</div>"
        "</div>"
    )


# ---- Judge trust banner (Deployment findings) -----------------------------------


def judge_trust_banner_html(mirror_root: Path) -> str:
    """Top-of-Findings-tab banner — measured judge calibration numbers."""
    rollouts = load_scored_rollouts(mirror_root)
    return render_judge_trust_banner(judge_trust(rollouts))


# ---- Mirror-root runtime dict passthrough ---------------------------------------
# Useful for panes that want the whole runtime.json (e.g. results section).


def runtime_snapshot(mirror_root: Path) -> dict[str, Any]:
    """Return the current runtime.json snapshot — thin passthrough."""
    return read_runtime(mirror_root)
