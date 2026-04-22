"""Canonical /memories/ paths. Import these — never hardcode the strings.

The Managed Agent writes to `/memories/` inside its container. We mirror to
`artifacts/sessions/<session_id>/` on disk for the Gradio UI to read. Both
roots have identical sub-layout, so this module returns paths relative to a
caller-supplied root.

CLAUDE.md sec 6 is the source of truth for which file lives where; if the
layout changes, edit it there first, then mirror the constants here.
"""

from __future__ import annotations

from pathlib import Path

# Filenames (relative to the session root).
PLAN_FILE = "plan.md"
TEST_MATRIX_FILE = "test_matrix.csv"
TAXONOMY_FILE = "taxonomy.md"
FINDINGS_FILE = "findings.jsonl"
REPORT_FILE = "report.md"

# Subdirectories.
ROLLOUTS_DIR = "rollouts"
NOTES_DIR = "notes"
ANNOTATED_DIR = "annotated"

# Roots.
AGENT_MEMORY_ROOT = Path("/memories")
ARTIFACTS_SESSIONS_ROOT = Path("artifacts") / "sessions"


def session_root(root: Path, session_id: str) -> Path:
    """Resolve <root>/<session_id> for the artifact mirror, or just <root> for /memories."""
    # /memories/ is a single-session container per agent run; session_id is only
    # meaningful on the artifact-mirror side.
    if root == AGENT_MEMORY_ROOT:
        return root
    return root / session_id


def plan_path(root: Path, session_id: str) -> Path:
    return session_root(root, session_id) / PLAN_FILE


def matrix_path(root: Path, session_id: str) -> Path:
    """Path to test_matrix.csv. Named without 'test_' prefix to avoid pytest collection."""
    return session_root(root, session_id) / TEST_MATRIX_FILE


def taxonomy_path(root: Path, session_id: str) -> Path:
    return session_root(root, session_id) / TAXONOMY_FILE


def findings_path(root: Path, session_id: str) -> Path:
    return session_root(root, session_id) / FINDINGS_FILE


def report_path(root: Path, session_id: str) -> Path:
    return session_root(root, session_id) / REPORT_FILE


def rollouts_dir(root: Path, session_id: str) -> Path:
    return session_root(root, session_id) / ROLLOUTS_DIR


def notes_dir(root: Path, session_id: str) -> Path:
    return session_root(root, session_id) / NOTES_DIR


def annotated_dir(root: Path, session_id: str) -> Path:
    return session_root(root, session_id) / ANNOTATED_DIR


def rollout_video_path(root: Path, session_id: str, rollout_id: str) -> Path:
    return rollouts_dir(root, session_id) / f"{rollout_id}.mp4"


def rollout_meta_path(root: Path, session_id: str, rollout_id: str) -> Path:
    return rollouts_dir(root, session_id) / f"{rollout_id}.json"
