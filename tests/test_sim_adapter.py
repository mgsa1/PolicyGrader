"""Integration tests for src.sim.adapter.run_rollout.

Marked `integration` because they spin up real robosuite envs (slow on cold
start, ~1-3s each on a quiet machine). These prove the adapter is a faithful
boundary: feed in a RolloutConfig, get back a RolloutResult with the right
ground-truth label and a video on disk.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.schemas import RolloutConfig
from src.sim.scripted import FailureMode, InjectedFailures


@pytest.mark.integration
class TestRunRolloutScripted:
    def test_clean_succeeds_and_writes_video(self, tmp_path: Path) -> None:
        from src.sim.adapter import run_rollout

        cfg = RolloutConfig(
            rollout_id="clean",
            policy_kind="scripted",
            env_name="Lift",
            seed=0,
            max_steps=200,
            injected_failures=InjectedFailures(),
        )
        out = tmp_path / "clean.mp4"
        result = run_rollout(cfg, video_out=out)

        assert result.success is True
        assert result.ground_truth_label == FailureMode.NONE
        assert result.rollout_id == "clean"
        assert result.video_path == out
        assert out.exists() and out.stat().st_size > 1024  # non-empty mp4

    def test_premature_close_fails_with_correct_label(self, tmp_path: Path) -> None:
        from src.sim.adapter import run_rollout

        cfg = RolloutConfig(
            rollout_id="prem-close",
            policy_kind="scripted",
            env_name="Lift",
            seed=0,
            max_steps=200,
            injected_failures=InjectedFailures(gripper_close_prematurely=True),
        )
        # Skip rendering: this test cares about success/label, not the mp4.
        result = run_rollout(cfg, video_out=None)

        assert result.success is False
        assert result.ground_truth_label == FailureMode.APPROACH_MISS
        assert result.video_path is None
