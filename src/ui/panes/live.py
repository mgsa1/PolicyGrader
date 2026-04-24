"""Live pane — agent trace · current rollout · /memories/ tree.

The trace stream re-uses the Managed Agents phase markers to segment events:
each phase emits a divider; events between dividers wear the phase's color as
a 3px left-border strip. The memories tree shows the host-side mirror files
(runtime.json, chat.jsonl, dispatch_log.jsonl, rollouts/, keyframes/) so the
viewer can see what's being written to disk as the agent runs.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.ui.panes._io import read_chat
from src.ui.panes.chrome import phase_code, phase_short
from src.ui.styles import empty, html_escape
from src.ui.synthesis import ScoredRollout, copy_button, load_scored_rollouts, population_chip

# Plain-language explainer per phase: (short title, subtitle, list of artifacts).
# Copied from the previous app.py — still load-bearing for onboarding viewers
# who watch the demo and don't know the Managed Agents vocabulary yet.
_PHASE_EXPLAINERS: dict[str, tuple[str, str, list[str]]] = {
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
        "Single dense-frame chain-of-thought call per sim-failed rollout. "
        "Walks through ~30 high-res frames, names the decisive frame, picks a "
        "failure label, points at the evidence (or abstains on no-contact "
        "failures). Sim handles the binary pass/fail decision.",
        ["findings.jsonl"],
    ),
    "BEGIN PHASE 4: REPORT": (
        "Report writer",
        "Synthesizes everything: success rate, judge precision/recall vs "
        "ground truth, failure clusters, cost vs the manual-review baseline.",
        ["report.md"],
    ),
}


# ---- Agent trace stream --------------------------------------------------------


def agent_trace_html(mirror_root: Path) -> str:
    """The full agent activity stream — latest phase pinned, events newest-first."""
    entries = read_chat(mirror_root)
    if not entries:
        return '<div class="pg-trace-empty">Waiting for the agent to start…</div>'

    current_phase = "starting"
    body: list[str] = []
    for e in entries:
        kind = e.get("kind", "?")
        if kind == "phase_marker":
            current_phase = str(e.get("marker", ""))
            continue
        body.append(_event_html(kind, e, current_phase))

    pinned = f'<div class="pg-trace-pinned">{_phase_divider(current_phase)}</div>'
    return f'<div class="pg-trace">{pinned}{"".join(reversed(body))}</div>'


def _phase_divider(marker: str) -> str:
    code = phase_code(marker) or "planner"
    explainer = _PHASE_EXPLAINERS.get(marker)
    title, sub, outputs = explainer if explainer else (marker, "", [])
    short = phase_short(marker)

    outputs_html = ""
    if outputs:
        files = " · ".join(f"<code>{html_escape(o)}</code>" for o in outputs)
        outputs_html = f'<div class="pg-trace-phase-writes"><strong>Writes:</strong> {files}</div>'
    return (
        '<div class="pg-trace-phase">'
        '<div class="pg-trace-phase-eyebrow">'
        f'<div class="pg-trace-phase-label {code}">{html_escape(short)}</div>'
        f'<div class="pg-trace-phase-rule {code}"></div>'
        "</div>"
        f'<div class="pg-trace-phase-title">{html_escape(title)}</div>'
        f'<div class="pg-trace-phase-sub">{html_escape(sub)}</div>'
        f"{outputs_html}"
        "</div>"
    )


def _event_html(kind: str, entry: dict[str, Any], phase_marker: str) -> str:
    code = phase_code(phase_marker) or ""
    code_cls = f" {code}" if code else ""
    if kind == "agent_message":
        text = str(entry.get("text", ""))
        return f'<div class="pg-trace-event say{code_cls}">{html_escape(text)}</div>'
    if kind == "agent_thinking":
        text = str(entry.get("text", ""))[:600]
        return f'<div class="pg-trace-event thinking{code_cls}">{html_escape(text)}</div>'
    if kind == "tool_use":
        tool = entry.get("tool", "?")
        args = entry.get("args", {})
        rid = args.get("rollout_id") if isinstance(args, dict) else None
        args_str = ", ".join(f"{k}={v!r}" for k, v in list(args.items())[:4])
        rid_html = f" → <code>{html_escape(str(rid))}</code>" if rid else ""
        return (
            f'<div class="pg-trace-event tool{code_cls}">'
            f"▸ <b>{html_escape(str(tool))}</b>({html_escape(args_str)}){rid_html}"
            "</div>"
        )
    if kind == "tool_result":
        tool = entry.get("tool", "?")
        payload = str(entry.get("payload", ""))[:300]
        return (
            f'<div class="pg-trace-event result{code_cls}">'
            f"◂ {html_escape(str(tool))} → {html_escape(payload)}"
            "</div>"
        )
    if kind == "tool_error":
        tool = entry.get("tool", "?")
        err = str(entry.get("error", ""))
        return (
            f'<div class="pg-trace-event error{code_cls}">'
            f"✗ {html_escape(str(tool))}: {html_escape(err)}"
            "</div>"
        )
    return ""


# ---- Current rollout ------------------------------------------------------------


def current_video_path(mirror_root: Path) -> str | None:
    """Most-recent rollout_id from chat.jsonl → its mp4 on disk, if present."""
    entries = read_chat(mirror_root)
    rollouts_dir = mirror_root / "rollouts"
    for e in reversed(entries):
        if e.get("kind") not in {"tool_use", "tool_result"}:
            continue
        args = e.get("args", {})
        rid = args.get("rollout_id") if isinstance(args, dict) else None
        if not rid:
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


def current_video_path_html(mirror_root: Path) -> str:
    """The mono path chip + copy button shown under the player."""
    path = current_video_path(mirror_root)
    if path is None:
        return (
            '<div style="font-size:var(--pg-fs-micro);color:var(--pg-ink-4);'
            'font-style:italic;margin-top:4px;">(no rollout selected yet)</div>'
        )
    name = Path(path).name
    return (
        '<div style="display:flex;align-items:center;gap:8px;margin-top:6px;">'
        '<span style="font-size:var(--pg-fs-micro);color:var(--pg-ink-3);'
        'text-transform:uppercase;letter-spacing:0.08em;font-weight:500;">Current mp4</span>'
        f'<span class="pg-kbd">{html_escape(name)}</span>'
        f"{copy_button(path, kind='mp4', inline=True)}"
        "</div>"
    )


# ---- Live gallery ---------------------------------------------------------------


def live_gallery_html(mirror_root: Path) -> str:
    """Metadata-rich grid of all rollouts recorded this session, newest first."""
    rollouts_dir = mirror_root / "rollouts"
    if not rollouts_dir.exists():
        return _gallery_empty()
    mp4s = sorted(rollouts_dir.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not mp4s:
        return _gallery_empty()

    by_id = {r.rollout_id: r for r in load_scored_rollouts(mirror_root)}
    cards = [_gallery_card(p, by_id.get(p.stem)) for p in mp4s[:30]]
    overflow = (
        f'<div class="pg-gallery-more">showing 30 newest of {len(mp4s)}</div>'
        if len(mp4s) > 30
        else ""
    )
    return '<div class="pg-gallery">' + "".join(cards) + "</div>" + overflow


def _gallery_empty() -> str:
    return (
        '<div class="pg-gallery-empty">'
        "No rollouts yet. The first one will appear here when Phase 2 starts."
        "</div>"
    )


def _gallery_card(mp4: Path, scored: ScoredRollout | None) -> str:
    rid = mp4.stem
    mp4_url = f"/gradio_api/file={mp4}"
    pop_html = ""
    meta_html = ""
    if scored is not None:
        pop_html = f'<div class="pop">{population_chip(scored, compact=True)}</div>'
        success_str = (
            '<span class="success-ok">✓ success</span>'
            if scored.success
            else '<span class="success-fail">✗ failed</span>'
        )
        meta_html = (
            '<div class="meta">'
            f'<span class="env">{html_escape(scored.env_name)}</span>'
            f"{success_str}"
            "</div>"
        )
    overlay = copy_button(mp4, kind="mp4", anchor="top-right")
    return (
        '<div class="pg-gallery-card">'
        '<div class="media">'
        f'<video src="{mp4_url}" preload="metadata" muted loop playsinline></video>'
        f"{overlay}{pop_html}"
        "</div>"
        '<div class="body">'
        f'<a class="id" href="{mp4_url}" target="_blank">{html_escape(rid)}</a>'
        f"{meta_html}"
        "</div>"
        "</div>"
    )


# ---- Memories tree --------------------------------------------------------------
# Currently the host has access to the mirror-root artifacts, not the agent's
# in-container /memories/ tree. We render the mirror files here and color each
# row by the phase whose dispatch last wrote it, using dispatch_log.jsonl as
# the source of truth for file ownership.


_OWNERSHIP_BY_NAME: dict[str, str] = {
    # Suffix/name hints — first hit wins.
    "runtime.json": "rollout",
    "chat.jsonl": "rollout",
    "dispatch_log.jsonl": "rollout",
    "meta.json": "planner",
}
_OWNERSHIP_BY_PREFIX: dict[str, str] = {
    "rollouts/": "rollout",
    "keyframes/": "judge",
}


def memories_tree_html(mirror_root: Path) -> str:
    """Render the mirror-root artifact tree with phase-colored indicator strips."""
    if not mirror_root.exists():
        return '<div class="pg-memories-empty">(no artifacts yet)</div>'

    # Track the most-recently-modified file so we can highlight it as "writing".
    paths = [p for p in sorted(mirror_root.rglob("*")) if p.is_file()]
    if not paths:
        return '<div class="pg-memories-empty">(no artifacts yet)</div>'
    youngest = max(paths, key=lambda p: p.stat().st_mtime)

    rows: list[str] = ['<div class="pg-memories">']
    last_dir: str | None = None
    for p in paths:
        rel = p.relative_to(mirror_root)
        parent = str(rel.parent) if str(rel.parent) != "." else ""
        if parent != last_dir:
            if parent:
                rows.append(f'<div class="pg-memories-row dir">▸ {html_escape(parent)}/</div>')
            last_dir = parent
        owner = _owner_for(rel.as_posix())
        writing = " writing" if p == youngest else ""
        size_kb = p.stat().st_size / 1024
        indent_px = 12 + (12 if parent else 0)
        rows.append(
            f'<div class="pg-memories-row {owner}{writing}" '
            f'style="padding-left:{indent_px}px;">'
            f'<span class="pg-memories-path">{html_escape(rel.name)}</span>'
            f'<span class="pg-memories-size">{size_kb:>6.1f} KB</span>'
            "</div>"
        )
    rows.append("</div>")
    return "".join(rows)


def _owner_for(rel_path: str) -> str:
    name = rel_path.rsplit("/", 1)[-1]
    if name in _OWNERSHIP_BY_NAME:
        return _OWNERSHIP_BY_NAME[name]
    for prefix, owner in _OWNERSHIP_BY_PREFIX.items():
        if rel_path.startswith(prefix):
            return owner
    return "report"


# ---- "How to read this dashboard" block (accordion body) ------------------------


def read_intro_html() -> str:
    return (
        '<div class="pg-card" style="font-size:14px;line-height:1.6;">'
        '<p style="margin:0 0 10px 0;">'
        '<b style="color:var(--pg-cal);">Calibration.</b> '
        "A portion of rollouts use a scripted picker with deliberately-injected "
        "failures. Because we caused the failure, we know the correct label. "
        "We measure the judge against those — that's what the "
        "<b>Judge calibration</b> tab is for.</p>"
        '<p style="margin:0 0 10px 0;">'
        '<b style="color:var(--pg-dep);">Deployment.</b> '
        "The rest of the rollouts use a real policy (today: a pretrained BC-RNN). "
        "The judge labels those without a safety net.</p>"
        '<p style="margin:0;">'
        "The <b>Deployment findings</b> tab applies the calibrated judge to the "
        "deployment rollouts and cites its calibration precision alongside each "
        "finding.</p>"
        "</div>"
    )


def empty_live() -> str:
    """Fallback used if something blocks rendering; not normally reached."""
    return empty("Live feed waiting for the orchestrator to emit its first event.")
