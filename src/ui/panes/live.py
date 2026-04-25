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
from src.ui.styles import empty, html_escape, render_markdown
from src.ui.synthesis import ScoredRollout, copy_button, load_scored_rollouts, population_chip

# Per-phase descriptive blurb + the artifacts that phase produces. The eyebrow
# already names the phase ("Phase 1: Planner"), so we skip a redundant bold
# title and go straight to the description.
_PHASE_EXPLAINERS: dict[str, tuple[str, list[str]]] = {
    "BEGIN PHASE 1: PLANNER": (
        "Decides which scenarios to run, which failures to inject, and what "
        "the success criteria are. No simulation yet — pure design.",
        ["plan.md", "test_matrix.csv"],
    ),
    "BEGIN PHASE 2: ROLLOUT": (
        "Runs every row of the test matrix in MuJoCo + robosuite. Each scenario "
        "produces a short mp4 of the robot attempting the task.",
        ["rollouts/*.mp4"],
    ),
    "BEGIN PHASE 3: JUDGE": (
        "Single dense-frame chain-of-thought call per sim-failed rollout. "
        "Walks through ~30 high-res frames, names the decisive frame, picks a "
        "failure label, points at the evidence (or abstains on no-contact "
        "failures). Sim handles the binary pass/fail decision.",
        ["findings.jsonl"],
    ),
    "BEGIN PHASE 4: REPORT": (
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
    sub, outputs = explainer if explainer else ("", [])
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
        f'<div class="pg-trace-phase-sub">{html_escape(sub)}</div>'
        f"{outputs_html}"
        "</div>"
    )


def _worker_chip(worker: str | None) -> str:
    """Tiny chip identifying which specialized session produced an event.

    The orchestrator tags every event with `planner` / `rollout` / `judge-NN`
    / `reporter`. When no worker tag is present (early bring-up or legacy
    artifacts), returning an empty string keeps the trace uncluttered.
    The chip color follows the phase that worker belongs to.
    """
    if not worker:
        return ""
    if worker.startswith("judge"):
        code = "judge"
    elif worker == "rollout":
        code = "rollout"
    elif worker == "planner":
        code = "planner"
    elif worker == "reporter":
        code = "report"
    else:
        code = ""
    code_cls = f" {code}" if code else ""
    return f'<span class="pg-worker-chip{code_cls}">{html_escape(worker)}</span>'


def _event_html(kind: str, entry: dict[str, Any], phase_marker: str) -> str:
    code = phase_code(phase_marker) or ""
    code_cls = f" {code}" if code else ""
    worker = entry.get("worker")
    chip = _worker_chip(worker if isinstance(worker, str) else None)
    if kind == "session_created":
        role = str(entry.get("role", worker or "?"))
        session_id = str(entry.get("session_id", ""))[:12]
        return (
            f'<div class="pg-trace-event session-created{code_cls}">'
            f"{chip}◆ session created "
            f'<span class="pg-kbd">{html_escape(role)}</span>'
            f" <code>{html_escape(session_id)}…</code>"
            "</div>"
        )
    if kind == "agent_message":
        text = str(entry.get("text", ""))
        return f'<div class="pg-trace-event say{code_cls}">{chip}{render_markdown(text)}</div>'
    if kind == "agent_thinking":
        text = str(entry.get("text", ""))[:600]
        return f'<div class="pg-trace-event thinking{code_cls}">{chip}{render_markdown(text)}</div>'
    if kind == "tool_use":
        tool = entry.get("tool", "?")
        args = entry.get("args", {})
        rid = args.get("rollout_id") if isinstance(args, dict) else None
        args_str = ", ".join(f"{k}={v!r}" for k, v in list(args.items())[:4])
        rid_html = f" → <code>{html_escape(str(rid))}</code>" if rid else ""
        return (
            f'<div class="pg-trace-event tool{code_cls}">'
            f"{chip}▸ <b>{html_escape(str(tool))}</b>({html_escape(args_str)}){rid_html}"
            "</div>"
        )
    if kind == "tool_result":
        tool = entry.get("tool", "?")
        payload = str(entry.get("payload", ""))[:300]
        return (
            f'<div class="pg-trace-event result{code_cls}">'
            f"{chip}◂ {html_escape(str(tool))} → {html_escape(payload)}"
            "</div>"
        )
    if kind == "tool_error":
        tool = entry.get("tool", "?")
        err = str(entry.get("error", ""))
        return (
            f'<div class="pg-trace-event error{code_cls}">'
            f"{chip}✗ {html_escape(str(tool))}: {html_escape(err)}"
            "</div>"
        )
    return ""


# ---- Current rollout ------------------------------------------------------------


def _rid_from_entry(entry: dict[str, Any]) -> str | None:
    """Extract rollout_id from a tool_use or tool_result chat entry, if any."""
    if entry.get("kind") not in {"tool_use", "tool_result"}:
        return None
    args = entry.get("args", {})
    rid = args.get("rollout_id") if isinstance(args, dict) else None
    if rid:
        return str(rid)
    payload = entry.get("payload")
    if isinstance(payload, str) and "rollout_id" in payload:
        try:
            value = json.loads(payload).get("rollout_id")
            if value:
                return str(value)
        except json.JSONDecodeError:
            return None
    return None


def current_video_path(mirror_root: Path) -> str | None:
    """Most-recent rollout_id from chat.jsonl → its mp4 on disk, if present."""
    entries = read_chat(mirror_root)
    rollouts_dir = mirror_root / "rollouts"
    for e in reversed(entries):
        rid = _rid_from_entry(e)
        if rid:
            mp4 = rollouts_dir / f"{rid}.mp4"
            if mp4.exists():
                return str(mp4)
    return None


def _per_worker_current_mp4(mirror_root: Path) -> list[tuple[str, str]]:
    """(worker_label, mp4_name) for each worker, newest tool_use with an rid wins.

    During the judge phase, multiple judge-NN workers stream concurrently;
    each one's most recent rollout_id is what that worker is "looking at" now.
    Order: deterministic by worker label so the strip doesn't reshuffle on
    each refresh.
    """
    entries = read_chat(mirror_root)
    rollouts_dir = mirror_root / "rollouts"
    newest: dict[str, str] = {}
    for e in entries:
        worker = e.get("worker")
        if not isinstance(worker, str):
            continue
        rid = _rid_from_entry(e)
        if not rid:
            continue
        if (rollouts_dir / f"{rid}.mp4").exists():
            newest[worker] = rid  # last-writer wins because we iterate oldest→newest
    return [(w, f"{rid}.mp4") for w, rid in sorted(newest.items())]


def current_video_path_html(mirror_root: Path) -> str:
    """The mono path chip shown under the player.

    Shows the most-recent mp4 overall. During the judge phase, appends a
    per-worker strip showing which mp4 each judge session is currently
    watching — that's where concurrency is visible.
    """
    path = current_video_path(mirror_root)
    if path is None:
        return (
            '<div style="font-size:var(--pg-fs-micro);color:var(--pg-ink-4);'
            'font-style:italic;margin-top:4px;">(no rollout selected yet)</div>'
        )
    name = Path(path).name
    head = (
        '<div style="display:flex;align-items:center;gap:8px;margin-top:6px;">'
        '<span style="font-size:var(--pg-fs-micro);color:var(--pg-ink-3);'
        'text-transform:uppercase;letter-spacing:0.08em;font-weight:500;">Current mp4</span>'
        f'<span class="pg-kbd">{html_escape(name)}</span>'
        f"{copy_button(path, kind='mp4', inline=True)}"
        "</div>"
    )

    # Per-worker strip — only meaningful when ≥ 2 distinct workers touched
    # a rollout, i.e. we're in the judge phase with multiple workers.
    per_worker = _per_worker_current_mp4(mirror_root)
    judge_workers = [(w, mp4) for w, mp4 in per_worker if w.startswith("judge")]
    if len(judge_workers) < 2:
        return head

    tiles: list[str] = []
    for worker, mp4_name in judge_workers:
        tiles.append(
            '<div class="pg-live-worker-tile">'
            f'<span class="pg-worker-chip judge">{html_escape(worker)}</span>'
            f'<span class="pg-kbd">{html_escape(mp4_name)}</span>'
            "</div>"
        )
    strip = (
        '<div class="pg-live-workers">'
        '<div class="pg-live-workers-label">'
        f"Now judging ({len(judge_workers)} workers in parallel)"
        "</div>"
        '<div class="pg-live-workers-grid">' + "".join(tiles) + "</div>"
        "</div>"
    )
    return head + strip


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


def empty_live() -> str:
    """Fallback used if something blocks rendering; not normally reached."""
    return empty("Live feed waiting for the orchestrator to emit its first event.")
