"""Live state the orchestrator publishes to disk so the UI can read along.

The Gradio app is a thin file watcher (and Remotion will be too, later) — it
does not import orchestrator state, it just polls these JSON files. Keeping
the IPC mechanism this dumb means:
  - The UI process can be restarted independently of the orchestrator.
  - The same files are the recording surface for a programmatic video tool.
  - Replay is trivial: an old session's mirror_root reproduces the same UI.

Two files in mirror_root:

  runtime.json — a small snapshot, overwritten in place after every event:
    {phase, elapsed_seconds, cost_usd, input_tokens, output_tokens,
     n_rollouts, last_event_at}

  chat.jsonl — append-only log of agent-visible activity, one JSON per line:
    {ts, kind, ...}  where kind ∈ {phase_marker, agent_message,
                                   agent_thinking, tool_use, tool_result}
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.costing import CostTracker

RUNTIME_JSON = "runtime.json"
CHAT_JSONL = "chat.jsonl"


@dataclass
class RuntimeState:
    """Mutable session state the orchestrator updates and writes through."""

    mirror_root: Path
    cost_tracker: CostTracker
    start_time: float
    phase: str = "starting"
    n_rollouts: int = 0
    last_event_at: float = 0.0
    session_id: str = ""
    # Best-effort planned total parsed from the user goal. None if we can't
    # tell — the UI then shows progress without a denominator until Phase 2
    # finishes (at which point the actual count becomes the denominator).
    planned_total: int | None = None

    def set_phase(self, phase: str) -> None:
        self.phase = phase
        self.last_event_at = time.time()
        self.write_snapshot()

    def mark_event(self) -> None:
        """Bump last_event_at and re-snapshot. Cheap; safe to call on every event."""
        self.last_event_at = time.time()
        # Recount rollouts on each tick (cheap glob; bounded by N rollouts).
        rollouts_dir = self.mirror_root / "rollouts"
        if rollouts_dir.exists():
            self.n_rollouts = len(list(rollouts_dir.glob("*.mp4")))
        self.write_snapshot()

    def _dispatch_counts(self) -> tuple[int, int, int, int]:
        """(rollouts, coarse, fine, fine_planned) from dispatch_log.jsonl.

        fine_planned = number of coarse calls that returned verdict='fail',
        which is the eventual denominator for Pass-2 progress.
        """
        path = self.mirror_root / "dispatch_log.jsonl"
        if not path.exists():
            return (0, 0, 0, 0)
        n_rollout = n_coarse = n_fine = n_fail = 0
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            tool = rec.get("tool")
            if tool == "rollout":
                n_rollout += 1
            elif tool == "coarse":
                n_coarse += 1
                if (rec.get("result") or {}).get("verdict") == "fail":
                    n_fail += 1
            elif tool == "fine":
                n_fine += 1
        return (n_rollout, n_coarse, n_fine, n_fail)

    def write_snapshot(self) -> None:
        """Atomic write of the runtime.json snapshot."""
        n_roll, n_coarse, n_fine, n_fine_planned = self._dispatch_counts()
        snapshot = {
            "phase": self.phase,
            "elapsed_seconds": time.time() - self.start_time,
            "cost_usd": self.cost_tracker.total_cost_usd,
            "input_tokens": self.cost_tracker.input_tokens,
            "output_tokens": self.cost_tracker.output_tokens,
            "cache_read_tokens": self.cost_tracker.cache_read_tokens,
            "cache_creation_tokens": self.cost_tracker.cache_creation_tokens,
            "n_rollouts": self.n_rollouts,
            "planned_total": self.planned_total,
            "n_rollouts_dispatched": n_roll,
            "n_coarse_dispatched": n_coarse,
            "n_fine_dispatched": n_fine,
            "n_fine_planned": n_fine_planned,
            "last_event_at": self.last_event_at,
            "session_id": self.session_id,
        }
        path = self.mirror_root / RUNTIME_JSON
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(snapshot, indent=2))
        os.replace(tmp, path)

    def append_chat(self, kind: str, **fields: Any) -> None:
        """Append one record to chat.jsonl. kind is the discriminator."""
        record: dict[str, Any] = {"ts": time.time(), "kind": kind, **fields}
        path = self.mirror_root / CHAT_JSONL
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
