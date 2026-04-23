"""Gradio UI over a live eval-orchestrator session.

This is a thin file watcher — not an orchestrator integration. It polls a
mirror_root directory (the one scripts/smoke_agent.py writes to) and re-reads
three artifact surfaces every second:

  runtime.json  — banner data (cost, wall time, scenarios, phase)
  chat.jsonl    — agent messages + tool calls in chronological order
  rollouts/*.mp4 — the recorded rollout videos; newest first in the grid

The decoupling means: the UI process can be started before, during, or after
the orchestrator — replay of an old mirror_root is identical to watching a
live one. It also means a programmatic video tool (Remotion) can render from
the same files without needing any Python runtime.

Launch with `python -m src.ui.app --mirror-root <dir>` or
`scripts/run_ui.py`.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import gradio as gr

from src.costing import (
    BASELINE_HOURLY_RATE_USD,
    baseline_cost_for,
    baseline_seconds_for,
    baseline_time_seconds_for_videos,
    estimated_video_duration_s,
    format_cost,
    format_duration,
)
from src.runtime_state import CHAT_JSONL, RUNTIME_JSON
from src.ui.metrics_view import (
    EMPTY_FILTER,
    DrillFilter,
    judge_trust,
    per_label_calibration,
    render_calibration_chip,
    render_drill_down,
    render_heatmap_figure,
    render_judge_calibration_header,
    render_judge_trust_banner,
    render_static_blocks,
)
from src.ui.synthesis import (
    CALIBRATION_COLOR,
    DEPLOYMENT_COLOR,
    Cluster,
    cluster_by_condition,
    cluster_by_label,
    cohort_split,
    compute_metrics,
    load_scored_rollouts,
    paperclip_button,
    population_chip,
    render_all_keyframes,
)

# Color per agent role/phase, used throughout chat blocks + headers.
PHASE_COLORS = {
    "BEGIN PHASE 1: PLANNER": "#60a5fa",  # blue — designs the test suite
    "BEGIN PHASE 2: ROLLOUT": "#c084fc",  # purple — runs the simulator
    "BEGIN PHASE 3: JUDGE": "#fb923c",  # orange — watches the videos
    "BEGIN PHASE 4: REPORT": "#4ade80",  # green — synthesizes findings
}
DEFAULT_PHASE_COLOR = "#94a3b8"  # slate — for "starting" / "complete" / unknown

# Plain-language explainer per phase: (short title, one-sentence explainer,
# list of artifacts produced). Shown when the phase marker arrives so a viewer
# unfamiliar with the project understands what's about to happen.
PHASE_EXPLAINERS: dict[str, tuple[str, str, list[str]]] = {
    "BEGIN PHASE 1: PLANNER": (
        "Planner",
        "Decides which scenarios to run, which failures to inject, and what "
        "the success criteria are. No simulation yet — pure design.",
        ["plan.md", "test_matrix.csv"],
    ),
    "BEGIN PHASE 2: ROLLOUT": (
        "Rollout worker",
        "Runs every row of the test matrix in MuJoCo + robosuite. Each scenario "
        "produces a short mp4 of the robot attempting the task.",
        ["rollouts/*.mp4"],
    ),
    "BEGIN PHASE 3: JUDGE": (
        "Vision judge",
        "Watches every rollout video twice. Pass-1: cheap binary pass/fail. "
        "Pass-2 (only on failures): high-res frames, picks a failure label, "
        "points at the visual evidence.",
        ["findings.jsonl"],
    ),
    "BEGIN PHASE 4: REPORT": (
        "Report writer",
        "Synthesizes everything: success rate, judge precision/recall vs "
        "ground truth, failure clusters, cost vs the manual-review baseline.",
        ["report.md"],
    ),
}

REFRESH_SECONDS = 1.0


def _read_runtime(mirror_root: Path) -> dict[str, Any]:
    """Load runtime.json, tolerating absence (orchestrator hasn't written yet)."""
    path = mirror_root / RUNTIME_JSON
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())  # type: ignore[no-any-return]
    except (json.JSONDecodeError, OSError):
        # Writer is racing; try again next tick.
        return {}


def _read_chat(mirror_root: Path, limit: int = 200) -> list[dict[str, Any]]:
    """Load the last `limit` chat entries, oldest-first, for display."""
    path = mirror_root / CHAT_JSONL
    if not path.exists():
        return []
    lines = path.read_text().splitlines()
    out: list[dict[str, Any]] = []
    for line in lines[-limit:]:
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _banner_html(mirror_root: Path) -> str:
    """Render the top banner: side-by-side columns + savings row.

    Cost column compares pipeline cost vs flat $75/hr × 3 min/rollout (labor
    accounting). Time column compares pipeline wall time vs sum-of-video-
    durations + 60 s/rollout (sequential reviewer wall time).
    """
    rt = _read_runtime(mirror_root)
    cost = float(rt.get("cost_usd", 0.0))
    elapsed = float(rt.get("elapsed_seconds", 0.0))
    n = int(rt.get("n_rollouts", 0))
    phase = str(rt.get("phase", "idle"))

    rollouts = load_scored_rollouts(mirror_root)
    n_cal, n_dep = cohort_split(rollouts)
    durations = [estimated_video_duration_s(r.env_name, r.steps_taken or None) for r in rollouts]
    baseline_time = (
        baseline_time_seconds_for_videos(durations) if durations else baseline_seconds_for(n)
    )
    baseline_cost = baseline_cost_for(n)
    cost_savings = max(baseline_cost - cost, 0.0)
    time_savings = max(baseline_time - elapsed, 0.0)
    cost_save_pct = (cost_savings / baseline_cost * 100) if baseline_cost > 0 else 0.0
    time_save_pct = (time_savings / baseline_time * 100) if baseline_time > 0 else 0.0

    phase_color = PHASE_COLORS.get(phase, DEFAULT_PHASE_COLOR)
    phase_short = _phase_short_name(phase)

    scenarios_breakdown = (
        f"{n} "
        f"<span style='font-size:13px;font-weight:500;color:#94a3b8;'>"
        f"<span style='color:{CALIBRATION_COLOR};'>{n_cal} cal</span>"
        f" + <span style='color:{DEPLOYMENT_COLOR};'>{n_dep} dep</span></span>"
    )
    metric_row_html = (
        _metric_row("Cost", format_cost(cost), format_cost(baseline_cost))
        + _metric_row("Wall time", format_duration(elapsed), format_duration(baseline_time))
        + _metric_row("Scenarios", scenarios_breakdown, str(n))
    )

    return f"""
<div style="padding:18px 24px;background:#0f172a;color:#f1f5f9;border-radius:10px;
            font-family:-apple-system,BlinkMacSystemFont,system-ui,sans-serif;">
  <div style="display:flex;align-items:center;justify-content:space-between;
              padding-bottom:12px;border-bottom:1px solid #1e293b;">
    <div style="font-size:13px;color:#94a3b8;text-transform:uppercase;letter-spacing:1.5px;">
      Live evaluation
    </div>
    <div>
      <span style="display:inline-block;padding:4px 10px;border-radius:14px;
                   background:{phase_color}22;color:{phase_color};
                   font-size:12px;font-weight:600;text-transform:uppercase;
                   letter-spacing:1px;">{phase_short}</span>
    </div>
  </div>

  <div style="display:grid;grid-template-columns:140px 1fr 1fr;align-items:baseline;
              padding:10px 0 6px 0;color:#94a3b8;font-size:11px;
              text-transform:uppercase;letter-spacing:1.2px;font-weight:600;">
    <div></div>
    <div>This pipeline</div>
    <div style="opacity:0.75;">Manual review baseline</div>
  </div>

  {metric_row_html}

  {_savings_row(cost_savings, cost_save_pct, time_savings, time_save_pct)}

  <div style="margin-top:8px;font-size:11px;color:#64748b;text-align:center;">
    Cost baseline: ${BASELINE_HOURLY_RATE_USD:.0f}/hr × 3 min/rollout (labor)  ·
    Time baseline: sum of video durations + 60 s/rollout (sequential review)
  </div>
</div>
""".strip()


_TABULAR = "font-variant-numeric:tabular-nums;"


def _metric_row(label: str, ours: str, base: str) -> str:
    """One row of the banner comparison table — aligned via CSS grid."""
    return (
        '<div style="display:grid;grid-template-columns:140px 1fr 1fr;'
        'align-items:baseline;padding:8px 0;border-top:1px solid #1e293b;">'
        f'<div style="font-size:11px;color:#94a3b8;text-transform:uppercase;'
        f'letter-spacing:1.2px;">{label}</div>'
        f'<div style="font-size:24px;font-weight:600;color:#f1f5f9;{_TABULAR}">{ours}</div>'
        f'<div style="font-size:24px;font-weight:600;color:#cbd5e1;{_TABULAR}'
        f'opacity:0.85;">{base}</div>'
        "</div>"
    )


def _savings_row(cost_saved: float, cost_pct: float, time_saved: float, time_pct: float) -> str:
    """Green-tinted strip at the bottom of the banner: cost saved + time saved."""
    cost_str = format_cost(cost_saved)
    time_str = format_duration(time_saved)
    return (
        '<div style="margin-top:10px;padding:10px 14px;background:#15803d22;'
        "border:1px solid #15803d44;border-radius:8px;display:flex;"
        'justify-content:space-around;font-size:14px;">'
        "<div>"
        '<span style="color:#94a3b8;">Cost saved:</span> '
        f'<b style="color:#4ade80;font-size:18px;{_TABULAR}">{cost_str}</b> '
        f'<span style="color:#94a3b8;font-size:12px;">({cost_pct:.0f}%)</span>'
        "</div>"
        "<div>"
        '<span style="color:#94a3b8;">Time saved:</span> '
        f'<b style="color:#4ade80;font-size:18px;{_TABULAR}">{time_str}</b> '
        f'<span style="color:#94a3b8;font-size:12px;">({time_pct:.0f}%)</span>'
        "</div>"
        "</div>"
    )


def _phase_short_name(phase: str) -> str:
    """Convert a phase marker into a short human label for the banner."""
    if phase.startswith("BEGIN PHASE"):
        if "PLANNER" in phase:
            return "Phase 1: Planner"
        if "ROLLOUT" in phase:
            return "Phase 2: Rollout"
        if "JUDGE" in phase:
            return "Phase 3: Judge"
        if "REPORT" in phase:
            return "Phase 4: Report"
    if phase == "starting":
        return "Starting"
    if phase == "complete":
        return "Complete"
    return phase or "Idle"


def _chat_html(mirror_root: Path) -> str:
    """Render the chat pane: dark theme, phase-color-coded, with phase explainers."""
    entries = _read_chat(mirror_root)
    if not entries:
        return (
            "<div style='padding:40px;text-align:center;color:#94a3b8;font-style:italic;'>"
            "Waiting for the agent to start…"
            "</div>"
        )

    current_phase = "starting"
    blocks: list[str] = []
    for e in entries:
        kind = e.get("kind", "?")
        if kind == "phase_marker":
            current_phase = str(e.get("marker", ""))
            blocks.append(_phase_explainer_card(current_phase))
            continue
        color = PHASE_COLORS.get(current_phase, DEFAULT_PHASE_COLOR)
        blocks.append(_chat_block(kind, e, color))

    return (
        "<div style='max-height:600px;overflow-y:auto;padding:4px;'>" + "".join(blocks) + "</div>"
    )


def _phase_explainer_card(marker: str) -> str:
    """Render a phase header with plain-language explanation of what's about to happen."""
    color = PHASE_COLORS.get(marker, DEFAULT_PHASE_COLOR)
    explainer = PHASE_EXPLAINERS.get(marker)
    title: str
    subtitle: str
    outputs: list[str]
    if explainer is None:
        title, subtitle, outputs = marker, "", []
    else:
        title, subtitle, outputs = explainer
    short = _phase_short_name(marker)

    outputs_html = ""
    if outputs:
        files = " · ".join(
            f"<code style='color:{color};opacity:0.8;background:none;font-size:11px;'>"
            f"{_escape(o)}</code>"
            for o in outputs
        )
        outputs_html = (
            f"<div style='margin-top:6px;font-size:11px;color:#64748b;'>"
            f"<span style='text-transform:uppercase;letter-spacing:1.2px;"
            f"font-weight:600;'>Writes:</span> {files}</div>"
        )

    # Typographic section divider, NOT a chat block. No background, no box.
    # Uppercase eyebrow + tinted rule to the right so the eye reads it as
    # "new section starting" rather than "another message".
    return f"""
<div style="margin:28px 0 12px 0;">
  <div style="display:flex;align-items:center;gap:14px;margin-bottom:6px;">
    <div style="font-size:11px;font-weight:800;color:{color};text-transform:uppercase;
                letter-spacing:2.5px;white-space:nowrap;">
      {_escape(short)}
    </div>
    <div style="flex:1;height:1px;
                background:linear-gradient(90deg,{color}66 0%,transparent 100%);"></div>
  </div>
  <div style="color:#e2e8f0;font-size:15px;font-weight:600;
              margin-bottom:3px;">{_escape(title)}</div>
  <div style="color:#94a3b8;font-size:12px;line-height:1.5;">{_escape(subtitle)}</div>
  {outputs_html}
</div>
""".strip()


def _chat_block(kind: str, entry: dict[str, Any], color: str) -> str:
    """Render one non-phase chat entry. Color is the active phase's color."""
    if kind == "agent_message":
        text = str(entry.get("text", ""))
        return (
            f"<div style='margin:6px 0;padding:10px 12px;background:#1e293b;"
            f"color:#f1f5f9;border-left:3px solid {color};border-radius:4px;"
            f"white-space:pre-wrap;font-size:13px;line-height:1.5;'>"
            f"{_escape(text)}</div>"
        )
    if kind == "agent_thinking":
        text = str(entry.get("text", ""))
        return (
            f"<div style='margin:4px 0;padding:8px 12px;background:#0f172a;"
            f"color:#94a3b8;border-left:2px dashed {color}66;border-radius:4px;"
            f"font-style:italic;font-size:12px;white-space:pre-wrap;line-height:1.45;'>"
            f"{_escape(text[:600])}</div>"
        )
    if kind == "tool_use":
        tool = entry.get("tool", "?")
        args = entry.get("args", {})
        rid = args.get("rollout_id")
        args_str = ", ".join(f"{k}={v!r}" for k, v in list(args.items())[:4])
        rid_link = ""
        if rid:
            rid_link = (
                f"<span style='color:{color};font-size:11px;margin-left:8px;'>"
                f"→ <code style='background:{color}22;padding:1px 5px;border-radius:3px;'>"
                f"{_escape(rid)}</code></span>"
            )
        return (
            f"<div style='margin:6px 0;padding:7px 12px;background:#1e293b;"
            f"color:#fbbf24;border-left:3px solid {color};border-radius:4px;"
            f"font-family:ui-monospace,monospace;font-size:12px;'>"
            f"▶ <b>{_escape(tool)}</b>({_escape(args_str)}){rid_link}</div>"
        )
    if kind == "tool_result":
        tool = entry.get("tool", "?")
        payload = str(entry.get("payload", ""))[:300]
        return (
            f"<div style='margin:2px 0 6px 0;padding:6px 12px;background:#1e293b;"
            f"color:#4ade80;border-left:3px solid {color}66;border-radius:4px;"
            f"font-family:ui-monospace,monospace;font-size:11px;opacity:0.85;'>"
            f"◀ {_escape(tool)} → {_escape(payload)}</div>"
        )
    if kind == "tool_error":
        tool = entry.get("tool", "?")
        err = str(entry.get("error", ""))
        return (
            f"<div style='margin:2px 0 6px 0;padding:6px 12px;background:#7f1d1d;"
            f"color:#fecaca;border-left:3px solid #dc2626;border-radius:4px;"
            f"font-family:ui-monospace,monospace;font-size:12px;'>"
            f"✗ {_escape(tool)}: {_escape(err)}</div>"
        )
    return ""


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _rollout_paths(mirror_root: Path) -> list[str]:
    """Return mp4 paths, newest first (so the latest rollout lands at top of grid)."""
    rollouts_dir = mirror_root / "rollouts"
    if not rollouts_dir.exists():
        return []
    paths = sorted(rollouts_dir.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
    return [str(p) for p in paths]


def _current_video_path_html(mirror_root: Path) -> str:
    """A single paperclip button beside the Current Rollout heading.

    gr.Video can't be overlaid (Gradio renders it inside its own container),
    so the icon flows inline below the player. Click → copies the host mp4 path.
    """
    path = _current_video_path(mirror_root)
    if path is None:
        return (
            "<div style='font-size:11px;color:#64748b;font-style:italic;margin-top:4px;'>"
            "(no rollout selected yet)</div>"
        )
    return (
        "<div style='display:flex;align-items:center;gap:8px;margin-top:4px;'>"
        "<span style='font-size:11px;color:#94a3b8;'>Current mp4:</span>"
        f"{paperclip_button(path, tooltip='Copy current mp4 path', inline=True)}"
        "</div>"
    )


def _rollout_paths_panel_html(mirror_root: Path) -> str:
    """Per-mp4 paperclip strip below the gallery, since gr.Gallery items aren't overlay-able."""
    paths = _rollout_paths(mirror_root)
    if not paths:
        return (
            "<div style='font-size:11px;color:#64748b;font-style:italic;margin-top:6px;'>"
            "(no rollout videos on disk yet)</div>"
        )
    chips = "".join(
        f"<div style='display:flex;align-items:center;gap:6px;'>"
        f"<span style='font-family:ui-monospace,monospace;font-size:10px;color:#94a3b8;"
        f"max-width:160px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;' "
        f"title='{Path(p).name}'>{Path(p).name}</span>"
        f"{paperclip_button(p, tooltip='Copy mp4 path', inline=True)}"
        f"</div>"
        for p in paths[:30]
    )
    overflow = (
        f"<div style='font-size:10px;color:#64748b;margin-top:4px;'>"
        f"showing 30 newest of {len(paths)}</div>"
        if len(paths) > 30
        else ""
    )
    return (
        "<div style='margin-top:6px;max-height:220px;overflow-y:auto;"
        "display:grid;grid-template-columns:1fr 1fr;gap:4px 12px;'>"
        f"{chips}</div>{overflow}"
    )


def _current_video_path(mirror_root: Path) -> str | None:
    """Most recently mentioned rollout_id from chat.jsonl, mapped to its mp4 if it exists."""
    entries = _read_chat(mirror_root)
    rollouts_dir = mirror_root / "rollouts"
    for e in reversed(entries):
        if e.get("kind") not in {"tool_use", "tool_result"}:
            continue
        args = e.get("args", {})
        rid = args.get("rollout_id") if isinstance(args, dict) else None
        if not rid:
            # tool_result has the payload as a JSON string; try to extract rollout_id.
            payload = e.get("payload")
            if isinstance(payload, str) and "rollout_id" in payload:
                try:
                    rid = json.loads(payload).get("rollout_id")
                except json.JSONDecodeError:
                    rid = None
        if rid:
            mp4 = rollouts_dir / f"{rid}.mp4"
            if mp4.exists():
                return str(mp4)
    return None


def _metrics_blocks(mirror_root: Path) -> tuple[str, str, str, str]:
    """Return (cohort, caption, binary_panel, per_label_table) HTML blocks."""
    rollouts = load_scored_rollouts(mirror_root)
    if not rollouts:
        empty = (
            "<div style='padding:40px;text-align:center;color:#94a3b8;font-style:italic;'>"
            "Metrics appear once the orchestrator has run rollouts AND the judge has finished."
            "</div>"
        )
        return empty, "", "", ""
    binary = compute_metrics(rollouts)
    return render_static_blocks(rollouts, binary)


def _heatmap_figure(mirror_root: Path) -> Any:
    """Build the Plotly confusion heatmap for the current mirror."""
    rollouts = load_scored_rollouts(mirror_root)
    return render_heatmap_figure(rollouts)


def _drill_html(mirror_root: Path, f: DrillFilter) -> str:
    rollouts = load_scored_rollouts(mirror_root)
    keyframes = render_all_keyframes(rollouts, mirror_root)
    return render_drill_down(rollouts, f, keyframes)


def _heatmap_labels(mirror_root: Path) -> list[str]:
    """Return the labels currently used as rows/columns in the heatmap.

    We re-derive them from the same data path render_heatmap_figure used,
    so a click index from gr.SelectData maps consistently back to a label.
    """
    from src.metrics import compute as compute_label_metrics
    from src.ui.metrics_view import _taxonomy_order, _used_labels, to_labeled_rollouts

    rollouts = load_scored_rollouts(mirror_root)
    labeled = to_labeled_rollouts(rollouts)
    metrics = compute_label_metrics(labeled)
    used = _used_labels(metrics, _taxonomy_order())
    return [lab.value for lab in used]


def _filter_status_html(f: DrillFilter) -> str:
    """Small status pill showing the active drill filter, or empty if none."""
    if not f.is_active:
        return ""
    return (
        "<div style='display:flex;gap:10px;align-items:center;padding:8px 12px;"
        "background:#1e293b;border-radius:6px;'>"
        "<span style='font-size:11px;color:#94a3b8;text-transform:uppercase;"
        "letter-spacing:1.2px;font-weight:600;'>Filter active:</span>"
        f"<code style='color:#fbbf24;font-size:12px;background:none;'>"
        f"{_escape(f.label_text())}</code>"
        "</div>"
    )


def _files_list(mirror_root: Path) -> str:
    """Render a compact list of non-mp4 artifacts in mirror_root."""
    if not mirror_root.exists():
        return "<p style='opacity:0.6'><i>(no artifacts yet)</i></p>"
    rows: list[str] = []
    for p in sorted(mirror_root.rglob("*")):
        if p.is_dir() or p.suffix == ".mp4":
            continue
        rel = p.relative_to(mirror_root)
        size_kb = p.stat().st_size / 1024
        rows.append(
            f"<div style='padding:3px 0;font-family:ui-monospace,monospace;font-size:12px;'>"
            f"<span style='opacity:0.5;'>{size_kb:>6.1f} KB</span>  "
            f"<span>{rel}</span></div>"
        )
    if not rows:
        return "<p style='opacity:0.6'><i>(no artifacts yet)</i></p>"
    return "<div style='max-height:600px;overflow-y:auto;'>" + "".join(rows) + "</div>"


def _cluster_card_html(
    cluster: Cluster,
    total_failures: int,
    keyframes: dict[str, Path],
    cal_stats: dict[str, Any],
) -> str:
    """Render one cluster card: name, count + %, breakdown row, keyframe grid.

    `cal_stats` is the per-label calibration map (label -> LabelStats) — used
    to attach a 'judge P = X' chip on each label in the breakdown row.
    """
    n = len(cluster.rollouts)
    pct = (n / total_failures * 100) if total_failures else 0.0

    # Breakdown row: top contributors first, formatted as "label N (XX%)" plus
    # a calibration-precision chip if this looks like a label name (taxonomy).
    breakdown_chips = ""
    if cluster.breakdown:
        chips = []
        for label, count in sorted(cluster.breakdown.items(), key=lambda kv: -kv[1]):
            sub_pct = (count / n * 100) if n else 0.0
            cal_chip = ""
            # Attach calibration chip only for things that look like taxonomy
            # labels (simple identifiers like 'approach_miss' or 'none', not
            # condition strings like 'high action noise (≥0.1)').
            looks_like_label = "_" in label or label == "none"
            if looks_like_label:
                cal_chip = render_calibration_chip(label, cal_stats)
            chips.append(
                "<span style='display:inline-block;padding:3px 9px;margin:2px 4px 2px 0;"
                f"background:#e0e7ff;color:#3730a3;border-radius:12px;font-size:12px;'>"
                f"{_escape(label)} · <b>{count}</b> ({sub_pct:.0f}%)</span>"
                f"{cal_chip}"
            )
        breakdown_chips = "".join(chips)

    # Keyframe grid: PNG per rollout that has video. Click the thumb to open
    # the source mp4. Two paperclip overlays per thumbnail (PNG/mp4 paths)
    # plus a population chip in the bottom-left corner.
    thumbs = ""
    for r in cluster.rollouts:
        kf = keyframes.get(r.rollout_id)
        if kf is None:
            continue
        kf_url = f"/gradio_api/file={kf}"
        mp4_url = f"/gradio_api/file={r.video_path_host}" if r.video_path_host else "#"
        overlays = paperclip_button(kf, tooltip="Copy keyframe PNG path", anchor="top-left")
        if r.video_path_host:
            overlays += paperclip_button(
                r.video_path_host, tooltip="Copy source mp4 path", anchor="top-right"
            )
        # Population chip overlaid bottom-left over the thumb.
        pop_chip = (
            f"<div style='position:absolute;bottom:6px;left:6px;'>"
            f"{population_chip(r, compact=True)}</div>"
        )
        thumbs += (
            "<div style='display:inline-block;margin:4px;vertical-align:top;width:180px;'>"
            f"<a href='{mp4_url}' target='_blank' "
            "style='display:block;text-decoration:none;color:inherit;'>"
            "<div style='position:relative;'>"
            f"<img src='{kf_url}' style='width:180px;height:auto;display:block;"
            "border-radius:6px;border:1px solid #cbd5e1;'/>"
            f"{overlays}{pop_chip}"
            "</div>"
            "<div style='font-family:ui-monospace,monospace;font-size:11px;"
            f"text-align:center;margin-top:3px;opacity:0.85;'>{_escape(r.rollout_id)}</div>"
            "</a>"
            "</div>"
        )
    if not thumbs:
        thumbs = (
            "<p style='opacity:0.6;font-style:italic;'>(no keyframes — videos not on host yet)</p>"
        )

    return f"""
<div style='margin:16px 0;padding:18px;background:#ffffff;border:1px solid #e2e8f0;
            border-radius:10px;box-shadow:0 1px 3px rgba(0,0,0,0.05);'>
  <div style='display:flex;align-items:baseline;justify-content:space-between;
              border-bottom:1px solid #f1f5f9;padding-bottom:10px;margin-bottom:12px;'>
    <h3 style='margin:0;font-size:18px;font-family:ui-monospace,monospace;color:#1e293b;'>
      {_escape(cluster.name)}
    </h3>
    <div style='font-size:14px;color:#475569;'>
      <b>{n}</b> rollouts · <b>{pct:.0f}%</b> of all failures
    </div>
  </div>
  <div style='margin-bottom:14px;'>{breakdown_chips}</div>
  <div style='display:flex;flex-wrap:wrap;'>{thumbs}</div>
</div>
""".strip()


def _synthesis_html(mirror_root: Path, mode: str) -> str:
    """Render the full synthesis view in the chosen mode ('label' or 'condition')."""
    rollouts = load_scored_rollouts(mirror_root)
    if not rollouts:
        return (
            "<p style='opacity:0.6'><i>No dispatch_log.jsonl yet. Synthesis appears once "
            "the orchestrator has run at least one rollout + judge cycle.</i></p>"
        )

    keyframes = render_all_keyframes(rollouts, mirror_root)
    total_failures = sum(1 for r in rollouts if r.judged_failure)
    if total_failures == 0:
        return (
            "<p style='opacity:0.6'><i>No judged failures yet — Pass-1 hasn't flagged "
            "any rollout as fail.</i></p>"
        )

    cal_stats = per_label_calibration(rollouts)
    clusters = cluster_by_label(rollouts) if mode == "label" else cluster_by_condition(rollouts)
    cards = [_cluster_card_html(c, total_failures, keyframes, cal_stats) for c in clusters]
    return "".join(cards)


def _judge_trust_html(mirror_root: Path) -> str:
    """Top-of-tab Judge Trust banner for the Deployment findings tab."""
    rollouts = load_scored_rollouts(mirror_root)
    return render_judge_trust_banner(judge_trust(rollouts))


def _read_dashboard_intro_html() -> str:
    """The 'How to read this dashboard' accordion content."""
    return (
        "<div style='padding:14px 18px;background:#0f172a;border:1px solid #1e293b;"
        "border-radius:8px;color:#cbd5e1;font-size:13px;line-height:1.6;'>"
        "<p style='margin:0 0 10px 0;'><b style='color:"
        f"{CALIBRATION_COLOR};'>Calibration.</b> A portion of rollouts use a "
        "scripted picker with deliberately-injected failures. Because we caused "
        "the failure, we know the correct label. We measure the judge against "
        "those — that's what the <b>Judge calibration</b> tab is for.</p>"
        "<p style='margin:0 0 10px 0;'><b style='color:"
        f"{DEPLOYMENT_COLOR};'>Deployment.</b> The rest of the rollouts use a "
        "real policy (today: a pretrained BC-RNN). The judge labels those "
        "without a safety net.</p>"
        "<p style='margin:0;'>The <b>Deployment findings</b> tab applies the "
        "calibrated judge to the deployment rollouts and cites its calibration "
        "precision alongside each finding.</p>"
        "</div>"
    )


def build_app(mirror_root: Path) -> gr.Blocks:
    """Construct the Gradio Blocks app. `mirror_root` is what every pane watches."""

    def banner() -> str:
        return _banner_html(mirror_root)

    def chat() -> str:
        return _chat_html(mirror_root)

    def current_video() -> str | None:
        return _current_video_path(mirror_root)

    def rollouts() -> list[str]:
        return _rollout_paths(mirror_root)

    def files() -> str:
        return _files_list(mirror_root)

    def metrics_blocks() -> tuple[str, str, str, str]:
        return _metrics_blocks(mirror_root)

    def heatmap() -> Any:
        return _heatmap_figure(mirror_root)

    def drill(f: DrillFilter) -> str:
        return _drill_html(mirror_root, f)

    def synth_by_label() -> str:
        return _synthesis_html(mirror_root, "label")

    def synth_by_condition() -> str:
        return _synthesis_html(mirror_root, "condition")

    with gr.Blocks(title="Embodied Eval Orchestrator") as app:
        banner_html = gr.HTML(value=banner())

        with gr.Tabs():
            with gr.Tab("Live"):
                with gr.Accordion("What is this tool doing?", open=False):
                    gr.HTML(value=_read_dashboard_intro_html())
                with gr.Row():
                    with gr.Column(scale=3):
                        gr.Markdown("### Agent activity")
                        chat_html = gr.HTML(value=chat())
                    with gr.Column(scale=3):
                        gr.Markdown("### Current rollout")
                        current_video_player = gr.Video(
                            value=current_video(),
                            autoplay=True,
                            loop=True,
                            height=400,
                        )
                        current_video_path_html = gr.HTML(
                            value=_current_video_path_html(mirror_root)
                        )
                        gr.Markdown("### All rollouts")
                        rollout_gallery = gr.Gallery(
                            value=rollouts(),
                            columns=3,
                            height=300,
                            object_fit="contain",
                        )
                        rollout_paths_html = gr.HTML(value=_rollout_paths_panel_html(mirror_root))
                    with gr.Column(scale=2):
                        gr.Markdown("### /memories/ tree")
                        files_html = gr.HTML(value=files())
            with gr.Tab("Judge calibration"):
                gr.HTML(value=render_judge_calibration_header())
                _initial_blocks = metrics_blocks()
                metrics_cohort_html = gr.HTML(value=_initial_blocks[0])
                metrics_caption_html = gr.HTML(value=_initial_blocks[1])
                metrics_binary_html = gr.HTML(value=_initial_blocks[2])
                gr.Markdown(
                    "**Pass-2 — multiclass confusion.** Rows=expected, cols=judged. "
                    "Diagonal (green) = matches, off-diagonal (orange) = mis-labels."
                )
                metrics_heatmap = gr.Plot(value=heatmap())
                metrics_per_label_html = gr.HTML(value=_initial_blocks[3])

                gr.Markdown(
                    "### Drill into calibration rollouts\n"
                    "Pick an expected/judged pair (or either alone) to see the "
                    "calibration rollouts behind the number. Leave both blank to clear."
                )
                _initial_labels = _heatmap_labels(mirror_root)
                with gr.Row():
                    metrics_filter_expected = gr.Dropdown(
                        label="Expected label",
                        choices=_initial_labels,
                        value=None,
                        interactive=True,
                    )
                    metrics_filter_judged = gr.Dropdown(
                        label="Judged label",
                        choices=_initial_labels,
                        value=None,
                        interactive=True,
                    )
                metrics_filter_status = gr.HTML(value="")
                metrics_drill_html = gr.HTML(value=drill(EMPTY_FILTER))
            with gr.Tab("Deployment findings"):
                # Banner sits above the sub-tabs so a viewer landing here sees
                # judge-trust info before any cluster card.
                deployment_trust_html = gr.HTML(value=_judge_trust_html(mirror_root))
                with gr.Tabs():
                    with gr.Tab("By label"):
                        gr.Markdown(
                            "**Each card** = one Pass-2 taxonomy label seen across "
                            "all judged failures. Each rollout in the card carries "
                            "its population chip (calibration vs deployment). "
                            "Click a keyframe to open the source mp4."
                        )
                        synth_label_html = gr.HTML(value=synth_by_label())
                    with gr.Tab("By condition"):
                        gr.Markdown(
                            "**Each card** = one perturbation condition (or env+policy "
                            "combination for deployment rollouts). Chips inside show "
                            "which Pass-2 labels that condition produced — each "
                            "decorated with its calibration precision where available."
                        )
                        synth_condition_html = gr.HTML(value=synth_by_condition())

        # Fast-refresh outputs: banner + chat + current video. These are cheap
        # to recompute (small JSON reads, a directory listing).
        timer = gr.Timer(REFRESH_SECONDS)
        timer.tick(fn=banner, outputs=banner_html)
        timer.tick(fn=chat, outputs=chat_html)
        timer.tick(fn=current_video, outputs=current_video_player)
        timer.tick(
            fn=lambda: _current_video_path_html(mirror_root),
            outputs=current_video_path_html,
        )
        timer.tick(fn=rollouts, outputs=rollout_gallery)
        timer.tick(
            fn=lambda: _rollout_paths_panel_html(mirror_root),
            outputs=rollout_paths_html,
        )
        timer.tick(fn=files, outputs=files_html)
        # Slower-refresh outputs: anything that decodes mp4s or re-joins data.
        heavy_timer = gr.Timer(5.0)
        heavy_timer.tick(
            fn=metrics_blocks,
            outputs=[
                metrics_cohort_html,
                metrics_caption_html,
                metrics_binary_html,
                metrics_per_label_html,
            ],
        )
        heavy_timer.tick(fn=heatmap, outputs=metrics_heatmap)
        heavy_timer.tick(fn=synth_by_label, outputs=synth_label_html)
        heavy_timer.tick(fn=synth_by_condition, outputs=synth_condition_html)
        heavy_timer.tick(
            fn=lambda: _judge_trust_html(mirror_root),
            outputs=deployment_trust_html,
        )

        # Dropdown changes → drill-down filter. (gr.Plot in Gradio 6 only emits
        # .change, not .select, so cell clicks aren't wired; a pair of label
        # dropdowns above the drill table drives the filter instead.)
        def _on_filter_change(expected: str | None, judged: str | None) -> tuple[str, str]:
            exp = expected or None
            jud = judged or None
            f = DrillFilter(expected=exp, judged=jud)
            return _filter_status_html(f), drill(f)

        metrics_filter_expected.change(
            fn=_on_filter_change,
            inputs=[metrics_filter_expected, metrics_filter_judged],
            outputs=[metrics_filter_status, metrics_drill_html],
        )
        metrics_filter_judged.change(
            fn=_on_filter_change,
            inputs=[metrics_filter_expected, metrics_filter_judged],
            outputs=[metrics_filter_status, metrics_drill_html],
        )

        # Keep dropdown choices in sync with the labels the data currently uses.
        def _refresh_dropdown_choices() -> tuple[Any, Any]:
            labels = _heatmap_labels(mirror_root)
            return gr.update(choices=labels), gr.update(choices=labels)

        heavy_timer.tick(
            fn=_refresh_dropdown_choices,
            outputs=[metrics_filter_expected, metrics_filter_judged],
        )

        # Re-render the drill-down on the slow timer too, so new rollouts that
        # match the active filter appear without forcing a manual refresh.
        def _refresh_drill(expected: str | None, judged: str | None) -> str:
            f = DrillFilter(expected=expected or None, judged=judged or None)
            return drill(f)

        heavy_timer.tick(
            fn=_refresh_drill,
            inputs=[metrics_filter_expected, metrics_filter_judged],
            outputs=metrics_drill_html,
        )

    # mypy can't track gr.Blocks's __enter__ return type through the with-block.
    assert isinstance(app, gr.Blocks)
    return app


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mirror-root",
        type=Path,
        required=True,
        help="Path to the orchestrator's mirror dir (runtime.json, chat.jsonl, rollouts/).",
    )
    parser.add_argument("--port", type=int, default=7860, help="Port to bind the Gradio server to.")
    args = parser.parse_args()

    mirror_root = args.mirror_root.resolve()
    app = build_app(mirror_root)
    app.launch(
        server_port=args.port,
        inbrowser=True,
        theme=gr.themes.Soft(),
        css=".gradio-container {max-width: 1400px !important;}",
        allowed_paths=[str(mirror_root)],
    )


if __name__ == "__main__":
    main()
