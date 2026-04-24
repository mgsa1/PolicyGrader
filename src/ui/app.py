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

from src.agents.system_prompts import PHASE_MARKER_REPORT
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
from src.ui import theme
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
    render_scope_strip,
    render_static_blocks,
)
from src.ui.synthesis import (
    Cluster,
    ScoredRollout,
    cluster_by_condition,
    cluster_by_label,
    cohort_split,
    compute_metrics,
    copy_button,
    load_scored_rollouts,
    population_chip,
    render_all_keyframes,
)

# Color per agent role/phase, used throughout chat blocks + headers.
PHASE_COLORS = {
    "BEGIN PHASE 1: PLANNER": theme.PLANNER,
    "BEGIN PHASE 2: ROLLOUT": theme.ROLLOUT,
    "BEGIN PHASE 3: JUDGE": theme.JUDGE,
    "BEGIN PHASE 4: REPORT": theme.REPORT,
}
DEFAULT_PHASE_COLOR = theme.PHASE_NEUTRAL

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


def _topbar_html() -> str:
    """Brand + tagline + run-name pill + elapsed-time — always-on header.

    Run name and elapsed time are placeholders for now — another pass will
    wire them to runtime.json (session_id, elapsed_seconds).
    """
    return (
        "<div class='pg-topbar'>"
        "<div class='pg-topbar__brand'>"
        "<div class='pg-topbar__logo'>P</div>"
        "<div>"
        "<div class='pg-topbar__wordmark'>PolicyGrader</div>"
        "<div class='pg-topbar__tagline'>Embodied eval orchestrator</div>"
        "</div>"
        "</div>"
        "<div class='pg-topbar__meta'>"
        "<span class='pg-topbar__run-chip'>eval_000000</span>"
        "<span class='pg-topbar__elapsed'>00:00 elapsed</span>"
        "</div>"
        "</div>"
    )


def _banner_html(mirror_root: Path) -> str:
    """Hero section with 3 metric cards + savings strip + baseline footnote.

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

    scenarios_sub = (
        f"<span style='color:{theme.CAL};font-weight:500;'>{n_cal} cal</span>"
        f" <span style='color:{theme.INK_4};'>+</span> "
        f"<span style='color:{theme.DEP};font-weight:500;'>{n_dep} dep</span>"
    )
    metrics = (
        _metric_card("Cost", format_cost(cost), f"baseline {format_cost(baseline_cost)}")
        + _metric_card(
            "Wall time", format_duration(elapsed), f"baseline {format_duration(baseline_time)}"
        )
        + _metric_card("Scenarios", str(n), scenarios_sub, sub_is_html=True)
    )

    return (
        "<div class='pg-hero'>"
        "<div style='display:flex;align-items:baseline;justify-content:space-between;gap:16px;'>"
        "<div>"
        "<div class='pg-hero__eyebrow'>Live evaluation</div>"
        "<h1 class='pg-hero__headline'>PolicyGrader vs manual review</h1>"
        "<div class='pg-hero__subhead'>"
        "Agent-run robot-manipulation evals, measured against the baseline a "
        "human would spend."
        "</div>"
        "</div>"
        f"<span class='pg-chip' style='background:{phase_color}1a;color:{phase_color};"
        f"border-color:{phase_color}55;font-weight:600;text-transform:uppercase;"
        "letter-spacing:0.06em;'>"
        f"{phase_short}</span>"
        "</div>"
        f"<div class='pg-metric-grid'>{metrics}</div>"
        f"{_savings_row(cost_savings, cost_save_pct, time_savings, time_save_pct)}"
        "<div class='pg-hero__footnote'>"
        f"Cost baseline: ${BASELINE_HOURLY_RATE_USD:.0f}/hr × 3 min/rollout (labor)  ·  "
        "Time baseline: sum of video durations + 60 s/rollout (sequential review)"
        "</div>"
        "</div>"
    )


def _metric_card(label: str, value: str, sub: str, *, sub_is_html: bool = False) -> str:
    """One metric card in the hero grid. `sub` is a baseline-comparison line."""
    sub_html = sub if sub_is_html else sub
    return (
        "<div class='pg-metric'>"
        f"<div class='pg-metric__label'>{label}</div>"
        f"<div class='pg-metric__value'>{value}</div>"
        f"<div class='pg-metric__base'>{sub_html}</div>"
        "</div>"
    )


def _savings_row(cost_saved: float, cost_pct: float, time_saved: float, time_pct: float) -> str:
    """Green-tinted strip at the bottom of the hero: cost saved + time saved."""
    cost_str = format_cost(cost_saved)
    time_str = format_duration(time_saved)
    return (
        "<div class='pg-savings'>"
        "<div>"
        "<span class='pg-savings__muted'>Cost saved:</span> "
        f"<b>{cost_str}</b> "
        f"<span class='pg-savings__muted'>({cost_pct:.0f}%)</span>"
        "</div>"
        "<div>"
        "<span class='pg-savings__muted'>Time saved:</span> "
        f"<b>{time_str}</b> "
        f"<span class='pg-savings__muted'>({time_pct:.0f}%)</span>"
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
    """Active phase pinned on top; agent stream below in reverse-chronological order.

    Each event block keeps the color of the phase it was emitted under, so as
    you scroll down (back in time) the color shift marks phase boundaries.
    """
    entries = _read_chat(mirror_root)
    if not entries:
        return "<div class='pg-chat__empty'>Waiting for the agent to start…</div>"

    current_phase = "starting"
    body_blocks: list[str] = []
    for e in entries:
        kind = e.get("kind", "?")
        if kind == "phase_marker":
            current_phase = str(e.get("marker", ""))
            continue
        color = PHASE_COLORS.get(current_phase, DEFAULT_PHASE_COLOR)
        body_blocks.append(_chat_block(kind, e, color))

    pinned = (
        "<div class='pg-chat__pinned'>"
        + _phase_explainer_card(current_phase)
        + "</div>"
    )
    return "<div class='pg-chat'>" + pinned + "".join(reversed(body_blocks)) + "</div>"


def _phase_explainer_card(marker: str) -> str:
    """Typographic section divider for a new phase — eyebrow + title + subtitle + outputs."""
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
            f"<code style='color:{color};background:none;'>{_escape(o)}</code>" for o in outputs
        )
        outputs_html = (
            f"<div class='pg-chat__phase-writes'>"
            f"<strong style='color:{color};'>Writes:</strong> {files}</div>"
        )

    return (
        "<div class='pg-chat__phase-hd'>"
        "<div class='pg-chat__phase-eyebrow'>"
        f"<div class='pg-chat__phase-label' style='color:{color};'>{_escape(short)}</div>"
        "<div class='pg-chat__phase-rule' style='"
        f"background:linear-gradient(90deg,{color}66 0%,transparent 100%);'></div>"
        "</div>"
        f"<div class='pg-chat__phase-title'>{_escape(title)}</div>"
        f"<div class='pg-chat__phase-sub'>{_escape(subtitle)}</div>"
        f"{outputs_html}"
        "</div>"
    )


def _chat_block(kind: str, entry: dict[str, Any], color: str) -> str:
    """Render one non-phase chat entry. Color is the active phase's color."""
    if kind == "agent_message":
        text = str(entry.get("text", ""))
        return (
            "<div class='pg-chat__block' "
            f"style='border-left:3px solid {color};white-space:pre-wrap;'>"
            f"{_escape(text)}</div>"
        )
    if kind == "agent_thinking":
        text = str(entry.get("text", ""))
        return (
            "<div class='pg-chat__block pg-chat__block--thinking' "
            f"style='border-left-color:{color}88;white-space:pre-wrap;'>"
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
            "<div class='pg-chat__block pg-chat__block--tool' "
            f"style='border-left:3px solid {color};color:{theme.INK_1};'>"
            f"▶ <b>{_escape(tool)}</b>({_escape(args_str)}){rid_link}</div>"
        )
    if kind == "tool_result":
        tool = entry.get("tool", "?")
        payload = str(entry.get("payload", ""))[:300]
        return (
            "<div class='pg-chat__block pg-chat__block--result' "
            f"style='border-left:3px solid {color}66;color:{theme.OK};'>"
            f"◀ {_escape(tool)} → <span style='color:{theme.INK_3};'>"
            f"{_escape(payload)}</span></div>"
        )
    if kind == "tool_error":
        tool = entry.get("tool", "?")
        err = str(entry.get("error", ""))
        return (
            "<div class='pg-chat__block pg-chat__block--error' "
            f"style='border-left:3px solid {theme.ERR};'>"
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
            f"<div style='font-size:11px;color:{theme.INK_4};font-style:italic;margin-top:4px;'>"
            "(no rollout selected yet)</div>"
        )
    return (
        "<div style='display:flex;align-items:center;gap:8px;margin-top:6px;'>"
        f"<span style='font-size:11px;color:{theme.INK_3};"
        "text-transform:uppercase;letter-spacing:0.08em;font-weight:500;'>"
        "Current mp4</span>"
        f"<span class='pg-kbd'>{Path(path).name}</span>"
        f"{copy_button(path, kind='mp4', inline=True)}"
        "</div>"
    )


def _rollout_paths_panel_html(mirror_root: Path) -> str:
    """Per-mp4 paperclip strip below the gallery, since gr.Gallery items aren't overlay-able."""
    paths = _rollout_paths(mirror_root)
    if not paths:
        return (
            f"<div style='font-size:11px;color:{theme.INK_4};font-style:italic;margin-top:6px;'>"
            "(no rollout videos on disk yet)</div>"
        )
    chips = "".join(
        "<div style='display:flex;align-items:center;gap:6px;'>"
        f"<span class='pg-kbd' title='{Path(p).name}'>{Path(p).name}</span>"
        f"{copy_button(p, kind='mp4', inline=True)}"
        "</div>"
        for p in paths[:30]
    )
    overflow = (
        f"<div style='font-size:10px;color:{theme.INK_4};margin-top:4px;'>"
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
            "<div class='pg-empty'>"
            "Metrics appear once the orchestrator has run rollouts AND the judge has finished."
            "</div>"
        )
        return empty, "", "", ""
    binary = compute_metrics(rollouts)
    return render_static_blocks(rollouts, binary)


def _scope_strip_html(mirror_root: Path, scope: str) -> str:
    return render_scope_strip(load_scored_rollouts(mirror_root), scope)


def _heatmap_figure(mirror_root: Path) -> Any:
    """Build the Plotly confusion heatmap for the current mirror."""
    rollouts = load_scored_rollouts(mirror_root)
    return render_heatmap_figure(rollouts)


def _results_html(mirror_root: Path) -> str:
    """Phase-4 Results tab — exec summary of the completed run.

    Hard numbers (cost, time, P/R) come from runtime.json + scored rollouts so
    the headline is auditable independently of what the agent's prose claims.
    The agent's narrative from chat.jsonl is appended below for color.
    """
    rt = _read_runtime(mirror_root)
    phase = str(rt.get("phase", ""))

    if phase != "complete":
        short = _phase_short_name(phase) if phase else "Idle"
        return (
            "<div class='pg-results'>"
            "<div class='pg-empty'>"
            "Final results appear once Phase 4 (Report) finishes. "
            f"Current phase: <b>{_escape(short)}</b>."
            "</div></div>"
        )

    rollouts = load_scored_rollouts(mirror_root)
    binary = compute_metrics(rollouts) if rollouts else None
    n_cal, n_dep = cohort_split(rollouts)

    return (
        "<div class='pg-results'>"
        + _results_summary_html(rt, rollouts, n_cal, n_dep)
        + _results_judge_html(binary, rollouts)
        + _results_pipeline_html(rt)
        + _results_narrative_html(mirror_root)
        + "</div>"
    )


def _results_summary_html(
    rt: dict[str, Any],
    rollouts: list[ScoredRollout],
    n_cal: int,
    n_dep: int,
) -> str:
    cost = float(rt.get("cost_usd", 0.0))
    elapsed = float(rt.get("elapsed_seconds", 0.0))
    n = int(rt.get("n_rollouts", 0))

    durations = [estimated_video_duration_s(r.env_name, r.steps_taken or None) for r in rollouts]
    baseline_time = (
        baseline_time_seconds_for_videos(durations) if durations else baseline_seconds_for(n)
    )
    baseline_cost = baseline_cost_for(n)
    cost_save = max(baseline_cost - cost, 0.0)
    time_save = max(baseline_time - elapsed, 0.0)
    cost_pct = (cost_save / baseline_cost * 100) if baseline_cost > 0 else 0.0
    time_pct = (time_save / baseline_time * 100) if baseline_time > 0 else 0.0

    scenarios_sub = (
        f"<span style='color:{theme.CAL};font-weight:500;'>{n_cal} cal</span>"
        f" <span style='color:{theme.INK_4};'>+</span> "
        f"<span style='color:{theme.DEP};font-weight:500;'>{n_dep} dep</span>"
    )
    cards = (
        _metric_card("Cost", format_cost(cost), f"baseline {format_cost(baseline_cost)}")
        + _metric_card(
            "Wall time", format_duration(elapsed), f"baseline {format_duration(baseline_time)}"
        )
        + _metric_card("Scenarios", str(n), scenarios_sub, sub_is_html=True)
    )
    return (
        "<div class='pg-results__section'>"
        "<div class='pg-results__eyebrow'>Run summary</div>"
        f"<div class='pg-metric-grid'>{cards}</div>"
        f"{_savings_row(cost_save, cost_pct, time_save, time_pct)}"
        "</div>"
    )


def _results_judge_html(binary: Any, rollouts: list[ScoredRollout]) -> str:
    """Judge scorecard pulled from compute_metrics — calibration only."""
    if not rollouts or binary is None or binary.n_total == 0:
        return (
            "<div class='pg-results__section'>"
            "<div class='pg-results__eyebrow'>Judge calibration</div>"
            "<div class='pg-empty'>No rollouts scored.</div>"
            "</div>"
        )

    p = binary.pass1_precision
    r = binary.pass1_recall
    binary_sub = (
        f"TP {binary.pass1_tp} · FP {binary.pass1_fp} · "
        f"FN {binary.pass1_fn} · TN {binary.pass1_tn}"
    )
    acc = binary.pass2_label_accuracy
    if acc is None:
        acc_value = "—"
        acc_sub = "no labeled calibration rollouts yet"
    else:
        acc_value = f"{acc:.0%}"
        acc_sub = f"{binary.pass2_correct} / {binary.pass2_labeled} exact match on injected GT"

    cards = (
        _metric_card("Binary precision", f"{p:.0%}", binary_sub)
        + _metric_card("Binary recall", f"{r:.0%}", binary_sub)
        + _metric_card("Pass-2 label accuracy", acc_value, acc_sub)
    )
    return (
        "<div class='pg-results__section'>"
        "<div class='pg-results__eyebrow'>Judge scorecard "
        "<span class='pg-results__eyebrow-note'>"
        "(calibration rollouts only — known ground truth)"
        "</span></div>"
        f"<div class='pg-metric-grid'>{cards}</div>"
        "</div>"
    )


def _results_pipeline_html(rt: dict[str, Any]) -> str:
    """One-line strip: rollouts dispatched → coarse → fine."""
    n_total = int(rt.get("n_rollouts", 0))
    n_disp = int(rt.get("n_rollouts_dispatched", 0))
    n_coarse = int(rt.get("n_coarse_dispatched", 0))
    n_fine = int(rt.get("n_fine_dispatched", 0))
    n_fine_planned = int(rt.get("n_fine_planned", 0))
    fine_str = (
        f"{n_fine} / {n_fine_planned}" if n_fine_planned else str(n_fine)
    )
    return (
        "<div class='pg-results__section'>"
        "<div class='pg-results__eyebrow'>Pipeline</div>"
        "<div class='pg-results__pipeline'>"
        f"<span><b>{n_disp}</b> / {n_total} rollouts</span>"
        "<span class='pg-results__arrow'>→</span>"
        f"<span><b>{n_coarse}</b> coarse passes</span>"
        "<span class='pg-results__arrow'>→</span>"
        f"<span><b>{fine_str}</b> fine passes</span>"
        "</div>"
        "</div>"
    )


def _results_narrative_html(mirror_root: Path) -> str:
    """Concatenate agent_message events that fall under the REPORT phase."""
    entries = _read_chat(mirror_root, limit=400)
    in_report = False
    messages: list[str] = []
    for e in entries:
        kind = e.get("kind")
        if kind == "phase_marker":
            in_report = str(e.get("marker", "")) == PHASE_MARKER_REPORT
            continue
        if not in_report:
            continue
        if kind == "agent_message":
            text = str(e.get("text", "")).strip()
            if text:
                messages.append(text)

    if not messages:
        return (
            "<div class='pg-results__section'>"
            "<div class='pg-results__eyebrow'>Agent's report</div>"
            "<div class='pg-empty'>No report narrative captured yet.</div>"
            "</div>"
        )

    body = "<hr style='border:none;border-top:1px solid " + theme.LINE + ";margin:14px 0;'/>".join(
        f"<div style='white-space:pre-wrap;'>{_escape(m)}</div>" for m in messages
    )
    return (
        "<div class='pg-results__section'>"
        "<div class='pg-results__eyebrow'>Agent's report</div>"
        f"<div class='pg-results__narrative'>{body}</div>"
        "</div>"
    )


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
        "<div class='pg-filter-pill'>"
        "<span class='pg-filter-pill__label'>Filter active:</span>"
        f"<span class='pg-filter-pill__value'>{_escape(f.label_text())}</span>"
        "</div>"
    )


def _files_list(mirror_root: Path) -> str:
    """Render a compact list of non-mp4 artifacts in mirror_root."""
    if not mirror_root.exists():
        return "<div class='pg-empty pg-empty--small'>(no artifacts yet)</div>"
    rows: list[str] = []
    for p in sorted(mirror_root.rglob("*")):
        if p.is_dir() or p.suffix == ".mp4":
            continue
        rel = p.relative_to(mirror_root)
        size_kb = p.stat().st_size / 1024
        rows.append(
            "<div class='pg-filelist__row'>"
            f"<span class='pg-filelist__size'>{size_kb:>6.1f} KB</span>  "
            f"<span>{rel}</span></div>"
        )
    if not rows:
        return "<div class='pg-empty pg-empty--small'>(no artifacts yet)</div>"
    return "<div class='pg-filelist'>" + "".join(rows) + "</div>"


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
                "<span class='pg-cluster-card__breakdown-chip'>"
                f"{_escape(label)} · <b>{count}</b> ({sub_pct:.0f}%)</span>"
                f"{cal_chip}"
            )
        breakdown_chips = "".join(chips)

    thumbs = ""
    for r in cluster.rollouts:
        kf = keyframes.get(r.rollout_id)
        if kf is None:
            continue
        kf_url = f"/gradio_api/file={kf}"
        mp4_url = f"/gradio_api/file={r.video_path_host}" if r.video_path_host else "#"
        overlays = copy_button(kf, kind="png", anchor="top-left")
        if r.video_path_host:
            overlays += copy_button(r.video_path_host, kind="mp4", anchor="top-right")
        pop_chip = f"<div class='pg-thumb__pop'>{population_chip(r, compact=True)}</div>"
        thumbs += (
            "<div class='pg-thumb'>"
            f"<a href='{mp4_url}' target='_blank'>"
            "<div class='pg-thumb__media'>"
            f"<img src='{kf_url}'/>"
            f"{overlays}{pop_chip}"
            "</div>"
            f"<div class='pg-thumb__id'>{_escape(r.rollout_id)}</div>"
            "</a>"
            "</div>"
        )
    if not thumbs:
        thumbs = "<p class='pg-thumb__empty'>(no keyframes — videos not on host yet)</p>"

    return (
        "<div class='pg-cluster-card'>"
        "<div class='pg-cluster-card__head'>"
        f"<h3 class='pg-cluster-card__title'>{_escape(cluster.name)}</h3>"
        "<div class='pg-cluster-card__count'>"
        f"<b>{n}</b> rollouts · <b>{pct:.0f}%</b> of all failures"
        "</div>"
        "</div>"
        f"<div class='pg-cluster-card__breakdown'>{breakdown_chips}</div>"
        f"<div class='pg-cluster-card__thumbs'>{thumbs}</div>"
        "</div>"
    )


def _synthesis_html(mirror_root: Path, mode: str) -> str:
    """Render the full synthesis view in the chosen mode ('label' or 'condition')."""
    rollouts = load_scored_rollouts(mirror_root)
    if not rollouts:
        return (
            "<div class='pg-empty'>No dispatch_log.jsonl yet. Synthesis appears once "
            "the orchestrator has run at least one rollout + judge cycle.</div>"
        )

    keyframes = render_all_keyframes(rollouts, mirror_root)
    total_failures = sum(1 for r in rollouts if r.judged_failure)
    if total_failures == 0:
        return (
            "<div class='pg-empty'>No judged failures yet — Pass-1 hasn't flagged "
            "any rollout as fail.</div>"
        )

    cal_stats = per_label_calibration(rollouts)
    clusters = cluster_by_label(rollouts) if mode == "label" else cluster_by_condition(rollouts)
    cards = [_cluster_card_html(c, total_failures, keyframes, cal_stats) for c in clusters]
    return "".join(cards)


def _judge_trust_html(mirror_root: Path) -> str:
    """Top-of-tab Judge Trust banner for the Deployment findings tab."""
    rollouts = load_scored_rollouts(mirror_root)
    return render_judge_trust_banner(judge_trust(rollouts))


def _phase_progress_html(mirror_root: Path) -> str:
    """4-phase progress strip below the top banner.

    Each phase chip is one of pending / active / complete, with a progress
    bar where counts are known. Sources of truth:
      - phase: runtime.json `phase` (the active marker, or 'starting'/'complete')
      - counts: runtime.json `n_rollouts_dispatched`, `n_coarse_dispatched`,
        `n_fine_dispatched`, `n_fine_planned`
      - denominator: runtime.json `planned_total` (parsed from goal) for
        ROLLOUT, then the actual dispatched count for downstream phases.
    """
    rt = _read_runtime(mirror_root)
    cur = str(rt.get("phase", "starting"))
    n_roll = int(rt.get("n_rollouts_dispatched", 0))
    n_coarse = int(rt.get("n_coarse_dispatched", 0))
    n_fine = int(rt.get("n_fine_dispatched", 0))
    n_fine_planned = int(rt.get("n_fine_planned", 0))
    planned: int | None = rt.get("planned_total")

    # Phase ordering: 0=PLANNER, 1=ROLLOUT, 2=JUDGE, 3=REPORT.
    order = {
        "starting": -1,
        "BEGIN PHASE 1: PLANNER": 0,
        "BEGIN PHASE 2: ROLLOUT": 1,
        "BEGIN PHASE 3: JUDGE": 2,
        "BEGIN PHASE 4: REPORT": 3,
        "complete": 4,
    }
    cur_idx = order.get(cur, -1)

    # Once Phase 2 ends, the rollout dispatch count IS the planned total.
    rollout_total = planned if cur_idx <= 1 else (n_roll if n_roll > 0 else planned)

    def _state(phase_idx: int) -> str:
        if cur_idx > phase_idx:
            return "complete"
        if cur_idx == phase_idx:
            return "active"
        return "pending"

    chips = [
        _phase_chip("Phase 1: Planner", "BEGIN PHASE 1: PLANNER", _state(0), None, None),
        _phase_chip(
            "Phase 2: Rollout",
            "BEGIN PHASE 2: ROLLOUT",
            _state(1),
            n_roll,
            rollout_total,
        ),
        _phase_chip(
            "Phase 3: Judge",
            "BEGIN PHASE 3: JUDGE",
            _state(2),
            n_coarse + n_fine,
            (rollout_total or 0) + (n_fine_planned or 0) if rollout_total else None,
            sub=f"coarse {n_coarse}/{rollout_total or '?'} · fine {n_fine}/{n_fine_planned or '?'}",
        ),
        _phase_chip("Phase 4: Report", "BEGIN PHASE 4: REPORT", _state(3), None, None),
    ]
    return "<div class='pg-phase-grid'>" + "".join(chips) + "</div>"


def _phase_chip(
    title: str,
    marker: str,
    state: str,  # 'pending' | 'active' | 'complete'
    done: int | None,
    total: int | None,
    sub: str | None = None,
) -> str:
    """One phase tile with title, status, and optional progress bar + sub-line."""
    color = PHASE_COLORS.get(marker, DEFAULT_PHASE_COLOR)

    # Active + complete tint the card with the phase color; pending stays neutral.
    if state == "complete":
        bg_style = f"background:{color}12;border-left-color:{color};"
        status_html = (
            f"<span class='pg-phase-chip__status' style='color:{color};'>✓ complete</span>"
        )
    elif state == "active":
        bg_style = f"background:{color}1a;border-left-color:{color};"
        status_html = f"<span class='pg-phase-chip__status' style='color:{color};'>● active</span>"
    else:
        bg_style = f"border-left-color:{theme.LINE_2};"
        status_html = (
            f"<span class='pg-phase-chip__status' style='color:{theme.INK_4};'>○ pending</span>"
        )

    bar_html = ""
    counter_html = ""
    if done is not None:
        if total and total > 0:
            pct = min(100, int(done / total * 100))
            bar_html = (
                "<div class='pg-progress'>"
                f"<div class='pg-progress__fill' style='width:{pct}%;background:{color};'></div>"
                "</div>"
            )
            counter_html = f"<div class='pg-phase-chip__counter'>{done} / {total}</div>"
        else:
            counter_html = f"<div class='pg-phase-chip__counter'>{done} done</div>"
    sub_html = f"<div class='pg-phase-chip__sub'>{sub}</div>" if sub else ""

    return (
        f"<div class='pg-phase-chip' style='{bg_style}'>"
        "<div class='pg-phase-chip__head'>"
        f"<div class='pg-phase-chip__title'>{title}</div>"
        f"{status_html}"
        "</div>"
        f"{bar_html}"
        f"{counter_html}"
        f"{sub_html}"
        "</div>"
    )


def _live_gallery_html(mirror_root: Path) -> str:
    """Metadata-rich custom grid replacing gr.Gallery on the Live tab.

    Each card:
      - inline <video> thumbnail (browser auto-renders the first frame as poster)
      - rollout_id (clickable to open the mp4 in a new tab)
      - population chip (calibration/deployment) when we have dispatch_log data
      - env name + success indicator if known
      - copy-mp4 button overlaid top-right

    Newest first, capped at 30 cards. Replaces gr.Gallery + the separate
    paths panel — those are now redundant since each card carries its own
    copy button.
    """
    rollouts_dir = mirror_root / "rollouts"
    if not rollouts_dir.exists():
        return _live_gallery_empty()
    mp4s = sorted(rollouts_dir.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not mp4s:
        return _live_gallery_empty()

    by_id = {r.rollout_id: r for r in load_scored_rollouts(mirror_root)}
    cards = [_live_gallery_card(p, by_id.get(p.stem)) for p in mp4s[:30]]

    overflow = (
        f"<div class='pg-gallery-more'>showing 30 newest of {len(mp4s)}</div>"
        if len(mp4s) > 30
        else ""
    )
    return "<div class='pg-gallery-grid'>" + "".join(cards) + "</div>" + overflow


def _live_gallery_empty() -> str:
    return (
        "<div class='pg-gallery-empty'>"
        "No rollouts yet. The first one will appear here when Phase 2 starts."
        "</div>"
    )


def _live_gallery_card(mp4: Path, scored: ScoredRollout | None) -> str:
    """One card in the metadata-rich gallery.

    `scored` is the matching ScoredRollout from dispatch_log if we have one
    (None for mp4s that exist on disk but haven't been logged yet — usually
    a brief transient between mp4 write and dispatch-log append).
    """
    mp4_url = f"/gradio_api/file={mp4}"
    rid = mp4.stem
    pop_html = ""
    meta_html = ""
    if scored is not None:
        pop_html = (
            f"<div class='pg-gallery-card__pop'>{population_chip(scored, compact=True)}</div>"
        )
        success_str = (
            "<span class='pg-gallery-card__success-ok'>✓ success</span>"
            if scored.success
            else "<span class='pg-gallery-card__success-fail'>✗ failed</span>"
        )
        meta_html = (
            "<div class='pg-gallery-card__meta'>"
            f"<span class='pg-gallery-card__env'>{_escape(scored.env_name)}</span>"
            f"{success_str}"
            "</div>"
        )

    overlay = copy_button(mp4, kind="mp4", anchor="top-right")
    return (
        "<div class='pg-gallery-card'>"
        "<div class='pg-gallery-card__media'>"
        f"<video src='{mp4_url}' preload='metadata' muted loop playsinline></video>"
        f"{overlay}"
        f"{pop_html}"
        "</div>"
        "<div class='pg-gallery-card__body'>"
        f"<a class='pg-gallery-card__id' href='{mp4_url}' target='_blank'>{_escape(rid)}</a>"
        f"{meta_html}"
        "</div>"
        "</div>"
    )


def _read_dashboard_intro_html() -> str:
    """The 'How to read this dashboard' accordion content."""
    return (
        "<div class='pg-card' style='padding:16px 20px;font-size:14px;line-height:1.6;'>"
        f"<p style='margin:0 0 10px 0;'><b style='color:{theme.CAL};'>Calibration.</b> "
        "A portion of rollouts use a scripted picker with deliberately-injected failures. "
        "Because we caused the failure, we know the correct label. We measure the judge "
        "against those — that's what the <b>Judge calibration</b> tab is for.</p>"
        f"<p style='margin:0 0 10px 0;'><b style='color:{theme.DEP};'>Deployment.</b> "
        "The rest of the rollouts use a real policy (today: a pretrained BC-RNN). "
        "The judge labels those without a safety net.</p>"
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

    def results() -> str:
        return _results_html(mirror_root)

    with gr.Blocks(title="PolicyGrader") as app:
        gr.HTML(value=_topbar_html())
        banner_html = gr.HTML(value=banner())
        progress_html = gr.HTML(value=_phase_progress_html(mirror_root))

        with gr.Tabs():
            with gr.Tab("Live"):
                with gr.Accordion("What is this tool doing?", open=False):
                    gr.HTML(value=_read_dashboard_intro_html())
                with gr.Row():
                    with gr.Column(scale=2):
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
                        live_gallery_html = gr.HTML(value=_live_gallery_html(mirror_root))
            with gr.Tab("Judge calibration"):
                judge_scope_html = gr.HTML(value=_scope_strip_html(mirror_root, "calibration"))
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
                dep_scope_html = gr.HTML(value=_scope_strip_html(mirror_root, "deployment"))
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
            with gr.Tab("Results"):
                results_html = gr.HTML(value=results())

        # Fast-refresh outputs: banner + chat + current video. These are cheap
        # to recompute (small JSON reads, a directory listing).
        timer = gr.Timer(REFRESH_SECONDS)
        timer.tick(fn=banner, outputs=banner_html)
        timer.tick(fn=lambda: _phase_progress_html(mirror_root), outputs=progress_html)
        timer.tick(fn=chat, outputs=chat_html)
        timer.tick(fn=current_video, outputs=current_video_player)
        timer.tick(
            fn=lambda: _current_video_path_html(mirror_root),
            outputs=current_video_path_html,
        )
        timer.tick(
            fn=lambda: _live_gallery_html(mirror_root),
            outputs=live_gallery_html,
        )
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
        heavy_timer.tick(
            fn=lambda: _scope_strip_html(mirror_root, "calibration"),
            outputs=judge_scope_html,
        )
        heavy_timer.tick(
            fn=lambda: _scope_strip_html(mirror_root, "deployment"),
            outputs=dep_scope_html,
        )
        heavy_timer.tick(fn=results, outputs=results_html)

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
    # Theme + CSS live on launch() in Gradio 6. The light base gets overridden
    # almost entirely by our .pg-* classes in theme.CSS — the Soft theme just
    # provides a clean starting point for Gradio's own inputs/dropdowns/etc.
    app.launch(
        server_port=args.port,
        inbrowser=True,
        theme=gr.themes.Soft(primary_hue="blue", neutral_hue="gray"),
        css=theme.CSS,
        allowed_paths=[str(mirror_root)],
    )


if __name__ == "__main__":
    main()
