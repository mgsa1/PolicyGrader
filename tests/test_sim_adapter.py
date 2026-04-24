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

    def test_zero_jitter_matches_default_placement_bounds(self) -> None:
        """cube_xy_jitter_m=0.0 must NOT mutate the sampler — keeps the default ±3 cm."""
        import os

        import robosuite as suite
        from robosuite.controllers import load_composite_controller_config

        from src.constants import MUJOCO_GL_ENV_KEY

        os.environ.setdefault(MUJOCO_GL_ENV_KEY, "glfw")

        controller_cfg = load_composite_controller_config(controller="BASIC", robot="Panda")
        env = suite.make(
            env_name="Lift",
            robots="Panda",
            controller_configs=controller_cfg,
            has_renderer=False,
            has_offscreen_renderer=False,
            use_camera_obs=False,
            control_freq=20,
            horizon=50,
        )
        # Default bounds from robosuite's Lift env (see lift.py:325).
        assert tuple(env.placement_initializer.x_range) == (-0.03, 0.03)
        assert tuple(env.placement_initializer.y_range) == (-0.03, 0.03)

    def test_nonzero_jitter_widens_placement_bounds(self) -> None:
        """cube_xy_jitter_m=J rewrites x_range/y_range to (-J, +J) before reset."""
        import os

        import robosuite as suite
        from robosuite.controllers import load_composite_controller_config

        from src.constants import MUJOCO_GL_ENV_KEY
        from src.sim.adapter import _apply_cube_xy_jitter

        os.environ.setdefault(MUJOCO_GL_ENV_KEY, "glfw")

        controller_cfg = load_composite_controller_config(controller="BASIC", robot="Panda")
        env = suite.make(
            env_name="Lift",
            robots="Panda",
            controller_configs=controller_cfg,
            has_renderer=False,
            has_offscreen_renderer=False,
            use_camera_obs=False,
            control_freq=20,
            horizon=50,
        )
        _apply_cube_xy_jitter(env, 0.08)
        assert tuple(env.placement_initializer.x_range) == (-0.08, 0.08)
        assert tuple(env.placement_initializer.y_range) == (-0.08, 0.08)
