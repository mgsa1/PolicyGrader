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
    format_cost,
    format_duration,
)
from src.runtime_state import CHAT_JSONL, RUNTIME_JSON

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
    """Render the top banner: $X.XX · Y:ZZ · N scenarios · Phase · Baseline row."""
    rt = _read_runtime(mirror_root)
    cost = float(rt.get("cost_usd", 0.0))
    elapsed = float(rt.get("elapsed_seconds", 0.0))
    n = int(rt.get("n_rollouts", 0))
    phase = str(rt.get("phase", "idle"))

    baseline_cost = baseline_cost_for(n)
    baseline_time = baseline_seconds_for(n)
    cost_ratio = (cost / baseline_cost) if baseline_cost > 0 else 0.0
    time_ratio = (elapsed / baseline_time) if baseline_time > 0 else 0.0

    return f"""
<div style="padding:18px 24px;background:#0f172a;color:#f1f5f9;border-radius:10px;
            font-family:-apple-system,BlinkMacSystemFont,system-ui,sans-serif;">
  <div style="display:flex;gap:32px;flex-wrap:wrap;align-items:baseline;">
    <div>
      <div style="font-size:11px;opacity:0.65;text-transform:uppercase;letter-spacing:1.5px;">
        Cost this run
      </div>
      <div style="font-size:28px;font-weight:600;">{format_cost(cost)}</div>
    </div>
    <div>
      <div style="font-size:11px;opacity:0.65;text-transform:uppercase;letter-spacing:1.5px;">
        Wall time
      </div>
      <div style="font-size:28px;font-weight:600;">{format_duration(elapsed)}</div>
    </div>
    <div>
      <div style="font-size:11px;opacity:0.65;text-transform:uppercase;letter-spacing:1.5px;">
        Scenarios
      </div>
      <div style="font-size:28px;font-weight:600;">{n}</div>
    </div>
    <div style="margin-left:auto;">
      <div style="font-size:11px;opacity:0.65;text-transform:uppercase;letter-spacing:1.5px;">
        Phase
      </div>
      <div style="font-size:18px;font-weight:500;color:#60a5fa;">{phase}</div>
    </div>
  </div>
  <div style="margin-top:14px;padding-top:14px;border-top:1px solid #1e293b;
              display:flex;gap:32px;font-size:13px;opacity:0.85;">
    <div>
      vs <b>manual review</b> baseline
      (${BASELINE_HOURLY_RATE_USD:.0f}/hr × 3 min/rollout):
      <b>{format_cost(baseline_cost)}</b> · <b>{format_duration(baseline_time)}</b>
    </div>
    <div>
      cost ratio: <b>{cost_ratio:.2f}×</b>
    </div>
    <div>
      time ratio: <b>{time_ratio:.2f}×</b>
    </div>
  </div>
</div>
""".strip()


def _chat_html(mirror_root: Path) -> str:
    """Render the chat pane as scrollable HTML, one event per block."""
    entries = _read_chat(mirror_root)
    if not entries:
        return "<p style='opacity:0.6'><i>Waiting for agent activity…</i></p>"

    blocks: list[str] = []
    for e in entries:
        kind = e.get("kind", "?")
        if kind == "phase_marker":
            blocks.append(
                f"<div style='margin:18px 0 8px 0;padding:8px 12px;"
                f"background:#1e293b;color:#93c5fd;border-radius:6px;"
                f"font-family:ui-monospace,monospace;font-weight:600;font-size:13px;'>"
                f"◆ {e.get('marker', '')}"
                f"</div>"
            )
        elif kind == "agent_message":
            text = str(e.get("text", ""))
            blocks.append(
                f"<div style='margin:8px 0;padding:10px 12px;background:#f8fafc;"
                f"border-left:3px solid #64748b;border-radius:4px;white-space:pre-wrap;"
                f"font-size:13px;line-height:1.45;'>{_escape(text)}</div>"
            )
        elif kind == "agent_thinking":
            text = str(e.get("text", ""))
            blocks.append(
                f"<div style='margin:6px 0;padding:8px 12px;background:#f1f5f9;"
                f"border-left:3px solid #cbd5e1;opacity:0.7;font-size:12px;"
                f"font-style:italic;white-space:pre-wrap;'>{_escape(text[:600])}</div>"
            )
        elif kind == "tool_use":
            tool = e.get("tool", "?")
            args = e.get("args", {})
            args_str = ", ".join(f"{k}={v!r}" for k, v in list(args.items())[:4])
            blocks.append(
                f"<div style='margin:6px 0;padding:6px 10px;background:#fef3c7;"
                f"border-left:3px solid #d97706;border-radius:4px;"
                f"font-family:ui-monospace,monospace;font-size:12px;'>"
                f"▶ {tool}({_escape(args_str)})</div>"
            )
        elif kind == "tool_result":
            tool = e.get("tool", "?")
            payload = str(e.get("payload", ""))[:300]
            blocks.append(
                f"<div style='margin:2px 0 6px 0;padding:6px 10px;background:#dcfce7;"
                f"border-left:3px solid #16a34a;border-radius:4px;"
                f"font-family:ui-monospace,monospace;font-size:12px;'>"
                f"◀ {tool} → {_escape(payload)}</div>"
            )
        elif kind == "tool_error":
            tool = e.get("tool", "?")
            err = str(e.get("error", ""))
            blocks.append(
                f"<div style='margin:2px 0 6px 0;padding:6px 10px;background:#fee2e2;"
                f"border-left:3px solid #dc2626;border-radius:4px;"
                f"font-family:ui-monospace,monospace;font-size:12px;'>"
                f"✗ {tool}: {_escape(err)}</div>"
            )

    return "<div style='max-height:600px;overflow-y:auto;'>" + "".join(blocks) + "</div>"


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _rollout_paths(mirror_root: Path) -> list[str]:
    """Return mp4 paths, newest first (so the latest rollout lands at top of grid)."""
    rollouts_dir = mirror_root / "rollouts"
    if not rollouts_dir.exists():
        return []
    paths = sorted(rollouts_dir.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
    return [str(p) for p in paths]


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


def build_app(mirror_root: Path) -> gr.Blocks:
    """Construct the Gradio Blocks app. `mirror_root` is what every pane watches."""

    def banner() -> str:
        return _banner_html(mirror_root)

    def chat() -> str:
        return _chat_html(mirror_root)

    def rollouts() -> list[str]:
        return _rollout_paths(mirror_root)

    def files() -> str:
        return _files_list(mirror_root)

    with gr.Blocks(title="Embodied Eval Orchestrator") as app:
        banner_html = gr.HTML(value=banner())
        with gr.Row():
            with gr.Column(scale=2):
                gr.Markdown("### Agent activity")
                chat_html = gr.HTML(value=chat())
            with gr.Column(scale=2):
                gr.Markdown("### Rollout videos")
                rollout_gallery = gr.Gallery(
                    value=rollouts(),
                    columns=2,
                    height=600,
                    object_fit="contain",
                )
            with gr.Column(scale=1):
                gr.Markdown("### /memories/ tree")
                files_html = gr.HTML(value=files())

        # gr.Timer fires on the given cadence; each tick re-reads the files
        # from disk. No orchestrator coupling.
        timer = gr.Timer(REFRESH_SECONDS)
        timer.tick(fn=banner, outputs=banner_html)
        timer.tick(fn=chat, outputs=chat_html)
        timer.tick(fn=rollouts, outputs=rollout_gallery)
        timer.tick(fn=files, outputs=files_html)

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
