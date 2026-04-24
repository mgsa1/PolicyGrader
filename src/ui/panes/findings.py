"""Deployment findings pane — judge-trust banner · cluster cards · rollout table.

The trust banner lives in `src/ui/panes/chrome.py` because the Overview tab
may surface a shortened version of it. The cluster cards and the bottom-of-
tab rollout table are specific to this pane.

Cluster cards are the calibrated estimates: each card is one failure label
or one perturbation condition that appeared among judged failures, decorated
with the per-label calibration precision computed in `metrics_view`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.ui.metrics_view import per_label_calibration, render_calibration_chip
from src.ui.styles import empty, html_escape, num
from src.ui.synthesis import (
    Cluster,
    ScoredRollout,
    cluster_by_condition,
    cluster_by_label,
    copy_button,
    load_scored_rollouts,
    population_chip,
    render_all_keyframes,
)

# ---- Cluster cards --------------------------------------------------------------


def cluster_cards_html(mirror_root: Path, mode: str) -> str:
    """Render all cluster cards for the Deployment findings tab.

    `mode` ∈ {'label', 'condition'} selects between cluster_by_label and
    cluster_by_condition — the former groups by judge taxonomy label, the
    latter by perturbation condition (scripted) or (env, policy) pair (BC-RNN).

    Clusters are built from the DEPLOYMENT cohort only. Calibration rollouts
    live on the Judge calibration tab; mixing them here would double-count
    scripted failures as if they were deployment findings. Per-label
    calibration precision (the chips on each breakdown) still comes from the
    full rollout set so we retain the scripted GT signal.
    """
    rollouts = load_scored_rollouts(mirror_root)
    if not rollouts:
        return empty(
            "No dispatch_log.jsonl yet. Synthesis appears once the orchestrator "
            "has run at least one rollout + judge cycle."
        )

    cal_stats = per_label_calibration(rollouts)
    deployment = [r for r in rollouts if r.population == "deployment"]
    if not deployment:
        return empty("Deployment cohort is empty for this run.")

    keyframes = render_all_keyframes(deployment, mirror_root)
    total_failures = sum(1 for r in deployment if r.judged_failure)
    if total_failures == 0:
        return empty(
            "No judged failures yet — either every deployment rollout succeeded, "
            "or the judge hasn't finished labeling the sim failures."
        )

    clusters = cluster_by_label(deployment) if mode == "label" else cluster_by_condition(deployment)
    cards = [
        _cluster_card(i + 1, c, total_failures, keyframes, cal_stats)
        for i, c in enumerate(clusters)
    ]
    return "".join(cards)


def _cluster_card(
    idx: int,
    cluster: Cluster,
    total_failures: int,
    keyframes: dict[str, Path],
    cal_stats: dict[str, Any],
) -> str:
    n = len(cluster.rollouts)
    pct = (n / total_failures * 100) if total_failures else 0.0
    share_pct = min(100, int(pct))

    first_kf = _first_keyframe(cluster, keyframes)
    thumb_html = (
        f'<div class="pg-cluster-thumb"><img src="/gradio_api/file={first_kf}"/></div>'
        if first_kf is not None
        else (
            '<div class="pg-cluster-thumb">'
            '<div class="pg-cluster-thumb-empty">(no keyframe yet — '
            "videos not on host)</div></div>"
        )
    )

    summary = cluster.rollouts[0].judge_description if cluster.rollouts else None
    summary_html = (
        f'<div class="pg-cluster-summary">{html_escape(str(summary)[:240])}</div>'
        if summary
        else ""
    )

    breakdown_html = _breakdown_chips(cluster, n, cal_stats)
    thumbs_html = _thumbs_strip(cluster, keyframes)

    return (
        '<div class="pg-cluster-card">' + thumb_html + '<div class="pg-cluster-body">'
        '<div class="pg-cluster-head">'
        f'<span class="pg-cluster-num">#{num(str(idx))}</span>'
        f'<span class="pg-cluster-label">{html_escape(cluster.name)}</span>'
        f'<span class="pg-cluster-count">{num(f"{n} / {total_failures}")}</span>'
        "</div>"
        f'<div class="pg-cluster-rail"><span style="width:{share_pct}%;"></span></div>'
        + summary_html
        + breakdown_html
        + thumbs_html
        + "</div></div>"
    )


def _first_keyframe(cluster: Cluster, keyframes: dict[str, Path]) -> Path | None:
    for r in cluster.rollouts:
        if r.rollout_id in keyframes:
            return keyframes[r.rollout_id]
    return None


def _breakdown_chips(cluster: Cluster, n: int, cal_stats: dict[str, Any]) -> str:
    if not cluster.breakdown:
        return ""
    chips: list[str] = []
    for label, count in sorted(cluster.breakdown.items(), key=lambda kv: -kv[1]):
        sub_pct = (count / n * 100) if n else 0.0
        looks_like_label = "_" in label or label == "none"
        cal_chip = render_calibration_chip(label, cal_stats) if looks_like_label else ""
        chips.append(
            f'<span class="pg-cluster-breakdown-chip">'
            f"{html_escape(label)} · <b>{num(str(count))}</b> ({sub_pct:.0f}%)"
            "</span>"
            f"{cal_chip}"
        )
    return f'<div style="margin:4px 0 6px 0;">{"".join(chips)}</div>'


def _thumbs_strip(cluster: Cluster, keyframes: dict[str, Path]) -> str:
    items: list[str] = []
    for r in cluster.rollouts[:8]:
        kf = keyframes.get(r.rollout_id)
        if kf is None:
            continue
        kf_url = f"/gradio_api/file={kf}"
        mp4_url = f"/gradio_api/file={r.video_path_host}" if r.video_path_host else "#"
        overlays = copy_button(kf, kind="png", anchor="top-left")
        if r.video_path_host:
            overlays += copy_button(r.video_path_host, kind="mp4", anchor="top-right")
        pop_chip = population_chip(r, compact=True)
        items.append(
            '<div class="pg-cluster-thumb-small">'
            f'<a href="{mp4_url}" target="_blank">'
            f'<div style="position:relative;"><img src="{kf_url}"/>{overlays}</div>'
            f'<div class="id">{html_escape(r.rollout_id)}</div>'
            "</a>"
            f'<div style="position:absolute;bottom:18px;left:4px;">{pop_chip}</div>'
            "</div>"
        )
    if not items:
        return ""
    return f'<div class="pg-cluster-thumbs">{"".join(items)}</div>'


# ---- Rollout table --------------------------------------------------------------


_ROLLOUT_TABLE_COLS = "grid-template-columns: 140px 1.4fr 1.2fr 0.8fr 0.8fr 2fr;"


def rollout_table_html(mirror_root: Path) -> str:
    """Bottom-of-tab rollout table listing every deployment rollout.

    Shows keyframe, id, pass-2 label, success, population chip, and
    description. Deployment cohort only; calibration rollouts live on
    the Judge calibration tab.
    """
    rollouts = load_scored_rollouts(mirror_root)
    dep = [r for r in rollouts if r.population == "deployment"]
    if not dep:
        return empty("Deployment cohort is empty for this run.", small=True)

    keyframes = render_all_keyframes(rollouts, mirror_root)
    rows: list[str] = [
        f'<div class="pg-ptable-row head" style="{_ROLLOUT_TABLE_COLS}">'
        "<div>Keyframe</div><div>Rollout</div><div>Judged label</div>"
        "<div>Success</div><div>Population</div><div>Description</div>"
        "</div>"
    ]
    for r in dep:
        rows.append(_rollout_row(r, keyframes))
    return f'<div class="pg-ptable">{"".join(rows)}</div>'


def _rollout_row(r: ScoredRollout, keyframes: dict[str, Path]) -> str:
    kf = keyframes.get(r.rollout_id)
    if kf is not None:
        overlays = copy_button(kf, kind="png", anchor="top-left")
        if r.video_path_host:
            overlays += copy_button(r.video_path_host, kind="mp4", anchor="top-right")
        thumb = f'<div class="pg-drill-thumb"><img src="/gradio_api/file={kf}"/>{overlays}</div>'
    else:
        thumb = '<div class="pg-drill-thumb-empty">no keyframe</div>'

    link = (
        f'<a class="pg-drill-link" href="/gradio_api/file={r.video_path_host}" '
        f'target="_blank">{html_escape(r.rollout_id)}</a>'
        if r.video_path_host
        else f'<span class="pg-drill-link">{html_escape(r.rollout_id)}</span>'
    )
    judged = r.judge_label or ("none" if r.success else "(pending)")
    success_badge = (
        '<span class="pg-match-badge ok">success</span>'
        if r.success
        else '<span class="pg-match-badge err">failure</span>'
    )
    desc = (r.judge_description or "—")[:160]
    return (
        f'<div class="pg-ptable-row" '
        f'style="{_ROLLOUT_TABLE_COLS}align-items:start;padding:12px 10px;">'
        f"<div>{thumb}</div>"
        f'<div class="pg-ptable-cell-mono">{link}</div>'
        f'<div class="pg-ptable-cell-mono">{html_escape(judged)}</div>'
        f"<div>{success_badge}</div>"
        f"<div>{population_chip(r, compact=True)}</div>"
        f'<div style="font-size:13px;color:var(--pg-ink-2);'
        f'line-height:1.5;">{html_escape(desc)}</div>'
        "</div>"
    )
