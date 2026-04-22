"""Tests for src.memory_layout: paths resolve consistently for both roots."""

from __future__ import annotations

from pathlib import Path

from src.memory_layout import (
    AGENT_MEMORY_ROOT,
    ARTIFACTS_SESSIONS_ROOT,
    findings_path,
    matrix_path,
    plan_path,
    report_path,
    rollout_meta_path,
    rollout_video_path,
    rollouts_dir,
    session_root,
    taxonomy_path,
)


class TestSessionRoot:
    def test_artifact_root_appends_session(self) -> None:
        assert session_root(ARTIFACTS_SESSIONS_ROOT, "abc") == Path("artifacts/sessions/abc")

    def test_agent_root_ignores_session(self) -> None:
        # /memories/ is single-session per container; session_id is mirror-only.
        assert session_root(AGENT_MEMORY_ROOT, "abc") == Path("/memories")


class TestArtifactPaths:
    SID = "demo"

    def test_plan(self) -> None:
        assert plan_path(ARTIFACTS_SESSIONS_ROOT, self.SID) == Path(
            "artifacts/sessions/demo/plan.md"
        )

    def test_matrix_csv(self) -> None:
        assert matrix_path(ARTIFACTS_SESSIONS_ROOT, self.SID) == Path(
            "artifacts/sessions/demo/test_matrix.csv"
        )

    def test_taxonomy(self) -> None:
        assert taxonomy_path(ARTIFACTS_SESSIONS_ROOT, self.SID) == Path(
            "artifacts/sessions/demo/taxonomy.md"
        )

    def test_findings(self) -> None:
        assert findings_path(ARTIFACTS_SESSIONS_ROOT, self.SID) == Path(
            "artifacts/sessions/demo/findings.jsonl"
        )

    def test_report(self) -> None:
        assert report_path(ARTIFACTS_SESSIONS_ROOT, self.SID) == Path(
            "artifacts/sessions/demo/report.md"
        )

    def test_rollouts_dir(self) -> None:
        assert rollouts_dir(ARTIFACTS_SESSIONS_ROOT, self.SID) == Path(
            "artifacts/sessions/demo/rollouts"
        )

    def test_rollout_video(self) -> None:
        assert rollout_video_path(ARTIFACTS_SESSIONS_ROOT, self.SID, "r1") == Path(
            "artifacts/sessions/demo/rollouts/r1.mp4"
        )

    def test_rollout_meta(self) -> None:
        assert rollout_meta_path(ARTIFACTS_SESSIONS_ROOT, self.SID, "r1") == Path(
            "artifacts/sessions/demo/rollouts/r1.json"
        )


class TestAgentPaths:
    """Both roots must yield the same sub-layout — only the prefix differs."""

    def test_plan(self) -> None:
        assert plan_path(AGENT_MEMORY_ROOT, "ignored") == Path("/memories/plan.md")

    def test_rollout_video(self) -> None:
        assert rollout_video_path(AGENT_MEMORY_ROOT, "ignored", "r1") == Path(
            "/memories/rollouts/r1.mp4"
        )
