"""Shared file readers for pane modules.

`runtime.json` + `chat.jsonl` are the two host-mirror files every pane
consumes. Keeping their readers in one place prevents drift between the
Live pane (high-frequency) and the chrome banner (also high-frequency).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.runtime_state import CHAT_JSONL, RUNTIME_JSON


def read_runtime(mirror_root: Path) -> dict[str, Any]:
    """Load runtime.json, tolerating absence (orchestrator hasn't written yet)."""
    path = mirror_root / RUNTIME_JSON
    if not path.exists():
        return {}
    try:
        data: dict[str, Any] = json.loads(path.read_text())
        return data
    except (json.JSONDecodeError, OSError):
        return {}


def read_chat(mirror_root: Path, limit: int = 200) -> list[dict[str, Any]]:
    """Load the last `limit` chat entries, oldest-first."""
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
