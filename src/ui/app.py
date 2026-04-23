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
from src.ui.synthesis import (
    Cluster,
    JudgeMetrics,
    cluster_by_condition,
    cluster_by_label,
    compute_metrics,
    load_scored_rollouts,
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

    metric_row_html = (
        _metric_row("Cost", format_cost(cost), format_cost(baseline_cost))
        + _metric_row("Wall time", format_duration(elapsed), format_duration(baseline_time))
        + _metric_row("Scenarios", str(n), str(n))
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


def _metrics_html(mirror_root: Path) -> str:
    """Render the Pass-1 + Pass-2 metrics computed from dispatch_log_jsonl."""
    rollouts = load_scored_rollouts(mirror_root)
    if not rollouts:
        return (
            "<div style='padding:40px;text-align:center;color:#94a3b8;font-style:italic;'>"
            "Metrics appear once the orchestrator has run rollouts AND the judge has finished."
            "</div>"
        )
    metrics = compute_metrics(rollouts)
    if metrics.pass1_tp + metrics.pass1_fp + metrics.pass1_fn + metrics.pass1_tn == 0:
        return (
            "<div style='padding:40px;text-align:center;color:#94a3b8;font-style:italic;'>"
            "Judge hasn't returned any verdicts yet."
            "</div>"
        )
    return _metrics_card(metrics)


def _metrics_card(m: JudgeMetrics) -> str:
    """Render the metrics dashboard. Heavy on contextual explanations for newcomers."""
    p1_prec = m.pass1_precision
    p1_rec = m.pass1_recall

    pass2_block = ""
    if m.pass2_label_accuracy is not None:
        acc = m.pass2_label_accuracy
        pass2_block = f"""
<div style='margin-top:18px;padding:18px;background:#1e293b;border-radius:8px;
            border-left:4px solid #fb923c;'>
  <div style='color:#fb923c;font-size:11px;font-weight:700;text-transform:uppercase;
              letter-spacing:1.2px;margin-bottom:8px;'>Pass-2 — failure mode label accuracy</div>
  <div style='font-size:32px;font-weight:700;color:#f1f5f9;font-variant-numeric:tabular-nums;'>
    {acc * 100:.0f}%
  </div>
  <div style='color:#cbd5e1;font-size:13px;margin-top:6px;'>
    On the {m.pass2_labeled} rollouts where the judge picked a label AND ground truth is
    available, <b>{m.pass2_correct}</b> matched the injected failure mode exactly.
  </div>
  <div style='color:#94a3b8;font-size:12px;margin-top:8px;font-style:italic;'>
    Why: only scripted-policy rollouts have ground-truth labels (we know which
    knob we perturbed). Pretrained policy rollouts contribute to Pass-1 binary
    metrics but not to label accuracy.
  </div>
</div>
""".strip()
    else:
        pass2_block = """
<div style='margin-top:18px;padding:14px;background:#1e293b;border-radius:8px;
            color:#94a3b8;font-size:13px;font-style:italic;'>
  No label-accuracy number yet — needs scripted rollouts (which carry ground-truth labels)
  to be judged by Pass-2.
</div>
""".strip()

    return f"""
<div style='padding:8px;'>
  <div style='display:grid;grid-template-columns:1fr 1fr;gap:16px;'>
    <div style='padding:18px;background:#1e293b;border-radius:8px;
                border-left:4px solid #c084fc;'>
      <div style='color:#c084fc;font-size:11px;font-weight:700;text-transform:uppercase;
                  letter-spacing:1.2px;margin-bottom:8px;'>Pass-1 — precision</div>
      <div style='font-size:32px;font-weight:700;color:#f1f5f9;font-variant-numeric:tabular-nums;'>
        {p1_prec * 100:.0f}%
      </div>
      <div style='color:#cbd5e1;font-size:13px;margin-top:6px;'>
        Of the rollouts the judge flagged as <b>fail</b>, this fraction actually failed.
      </div>
      <div style='color:#94a3b8;font-size:11px;margin-top:8px;font-variant-numeric:tabular-nums;'>
        TP {m.pass1_tp} · FP {m.pass1_fp}
      </div>
    </div>
    <div style='padding:18px;background:#1e293b;border-radius:8px;
                border-left:4px solid #c084fc;'>
      <div style='color:#c084fc;font-size:11px;font-weight:700;text-transform:uppercase;
                  letter-spacing:1.2px;margin-bottom:8px;'>Pass-1 — recall</div>
      <div style='font-size:32px;font-weight:700;color:#f1f5f9;font-variant-numeric:tabular-nums;'>
        {p1_rec * 100:.0f}%
      </div>
      <div style='color:#cbd5e1;font-size:13px;margin-top:6px;'>
        Of all rollouts that <b>actually failed</b>, this fraction was caught by the judge.
      </div>
      <div style='color:#94a3b8;font-size:11px;margin-top:8px;font-variant-numeric:tabular-nums;'>
        TP {m.pass1_tp} · FN {m.pass1_fn}
      </div>
    </div>
  </div>
  {pass2_block}
  <div style='margin-top:14px;padding:10px 14px;background:#0f172a;border-radius:6px;
              color:#64748b;font-size:11px;'>
    n = {m.n_total} rollouts · {m.n_with_ground_truth} with ground-truth labels.
    Ground truth is from the env (success / no success) for Pass-1, and from the
    injection knob for Pass-2 (scripted rollouts only).
  </div>
</div>
""".strip()


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


def _cluster_card_html(cluster: Cluster, total_failures: int, keyframes: dict[str, Path]) -> str:
    """Render one cluster card: name, count + %, breakdown row, keyframe grid."""
    n = len(cluster.rollouts)
    pct = (n / total_failures * 100) if total_failures else 0.0

    # Breakdown row: top contributors first, formatted as "label N (XX%)"
    breakdown_chips = ""
    if cluster.breakdown:
        chips = []
        for label, count in sorted(cluster.breakdown.items(), key=lambda kv: -kv[1]):
            sub_pct = (count / n * 100) if n else 0.0
            chips.append(
                f"<span style='display:inline-block;padding:3px 9px;margin:2px 4px 2px 0;"
                f"background:#e0e7ff;color:#3730a3;border-radius:12px;font-size:12px;'>"
                f"{_escape(label)} · <b>{count}</b> ({sub_pct:.0f}%)</span>"
            )
        breakdown_chips = "".join(chips)

    # Keyframe grid: PNG per rollout that has video. Each is a clickable link
    # to the source mp4 served by Gradio (file= URL prefix).
    thumbs = ""
    for r in cluster.rollouts:
        kf = keyframes.get(r.rollout_id)
        if kf is None:
            continue
        # Gradio serves files from the working dir via /file= URL prefix.
        kf_url = f"/file={kf}"
        mp4_url = f"/file={r.video_path_host}" if r.video_path_host else "#"
        thumbs += (
            f"<a href='{mp4_url}' target='_blank' style='display:inline-block;margin:4px;"
            f"text-decoration:none;color:inherit;'>"
            f"<img src='{kf_url}' style='width:180px;height:auto;display:block;border-radius:6px;"
            f"border:1px solid #cbd5e1;'/>"
            f"<div style='font-family:ui-monospace,monospace;font-size:11px;text-align:center;"
            f"margin-top:3px;opacity:0.75;'>{_escape(r.rollout_id)}</div>"
            f"</a>"
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

    clusters = cluster_by_label(rollouts) if mode == "label" else cluster_by_condition(rollouts)
    cards = [_cluster_card_html(c, total_failures, keyframes) for c in clusters]
    return "".join(cards)


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

    def metrics() -> str:
        return _metrics_html(mirror_root)

    def synth_by_label() -> str:
        return _synthesis_html(mirror_root, "label")

    def synth_by_condition() -> str:
        return _synthesis_html(mirror_root, "condition")

    with gr.Blocks(title="Embodied Eval Orchestrator") as app:
        banner_html = gr.HTML(value=banner())

        with gr.Tabs():
            with gr.Tab("Live"), gr.Row():
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
                    gr.Markdown("### All rollouts")
                    rollout_gallery = gr.Gallery(
                        value=rollouts(),
                        columns=3,
                        height=300,
                        object_fit="contain",
                    )
                with gr.Column(scale=2):
                    gr.Markdown("### /memories/ tree")
                    files_html = gr.HTML(value=files())
            with gr.Tab("Metrics"):
                gr.Markdown(
                    "### Judge accuracy against ground truth\n\n"
                    "**Pass-1** is the cheap binary classifier — it decides whether "
                    "each rollout succeeded or failed. Ground truth here comes from "
                    "the simulator (`env._check_success()`), so *every* rollout counts.\n\n"
                    "**Pass-2** only runs on rollouts Pass-1 flagged as failures, and it "
                    "picks a specific failure label. Ground truth for the label comes "
                    "from the injection knob used in the scripted policy (pretrained "
                    "rollouts have no label ground truth)."
                )
                metrics_html = gr.HTML(value=metrics())
            with gr.Tab("Failure synthesis · by label"):
                gr.Markdown(
                    "**Each card** = one Pass-2 taxonomy label seen across all "
                    "judged failures. Chips inside show which **conditions** "
                    "drove that label. Click a keyframe to open the source mp4."
                )
                synth_label_html = gr.HTML(value=synth_by_label())
            with gr.Tab("Failure synthesis · by condition"):
                gr.Markdown(
                    "**Each card** = one perturbation condition (or env+policy "
                    "combination for pretrained). Chips inside show which "
                    "**Pass-2 labels** that condition produced. Click a keyframe "
                    "to open the source mp4."
                )
                synth_condition_html = gr.HTML(value=synth_by_condition())

        # Fast-refresh outputs: banner + chat + current video. These are cheap
        # to recompute (small JSON reads, a directory listing).
        timer = gr.Timer(REFRESH_SECONDS)
        timer.tick(fn=banner, outputs=banner_html)
        timer.tick(fn=chat, outputs=chat_html)
        timer.tick(fn=current_video, outputs=current_video_player)
        timer.tick(fn=rollouts, outputs=rollout_gallery)
        timer.tick(fn=files, outputs=files_html)
        # Slower-refresh outputs: anything that decodes mp4s or re-joins data.
        heavy_timer = gr.Timer(5.0)
        heavy_timer.tick(fn=metrics, outputs=metrics_html)
        heavy_timer.tick(fn=synth_by_label, outputs=synth_label_html)
        heavy_timer.tick(fn=synth_by_condition, outputs=synth_condition_html)

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

    app = build_app(args.mirror_root.resolve())
    app.launch(
        server_port=args.port,
        inbrowser=True,
        theme=gr.themes.Soft(),
        css=".gradio-container {max-width: 1400px !important;}",
    )


if __name__ == "__main__":
    main()
