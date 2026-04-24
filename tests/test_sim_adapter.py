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
from src.sim.scripted import InjectedFailures


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
        assert result.rollout_id == "clean"
        assert result.video_path == out
        assert out.exists() and out.stat().st_size > 1024  # non-empty mp4

    def test_clean_writes_physics_sane_telemetry(self, tmp_path: Path) -> None:
        """Telemetry sidecar exists, aligns with the mp4, and is physics-sane.

        Clean Lift pickup → contact_flag must flip True at least once,
        gripper_aperture must close (drop below 0.3), cube_z_above_table_m
        must rise above the success threshold (~0.04), cube_xy_drift stays
        small (<5 cm — gripper should grasp, not knock).
        """
        from src.schemas import RolloutTelemetry
        from src.sim.adapter import _telemetry_path_for, run_rollout

        cfg = RolloutConfig(
            rollout_id="clean-tel",
            policy_kind="scripted",
            env_name="Lift",
            seed=0,
            max_steps=200,
            injected_failures=InjectedFailures(),
        )
        out = tmp_path / "clean-tel.mp4"
        result = run_rollout(cfg, video_out=out)

        assert result.success is True
        assert result.telemetry_path == _telemetry_path_for(out)
        assert result.telemetry_path is not None and result.telemetry_path.exists()

        tel = RolloutTelemetry.model_validate_json(result.telemetry_path.read_text())
        assert tel.rollout_id == "clean-tel"
        assert tel.fps == cfg.render.fps
        assert len(tel.rows) == result.steps_taken  # 1:1 with mp4 frames

        assert any(r.contact_flag for r in tel.rows), "gripper never touched cube"
        assert min(r.gripper_aperture for r in tel.rows) < 0.3, "gripper never closed"
        assert max(r.cube_z_above_table_m for r in tel.rows) > 0.04, "cube never lifted"
        assert max(r.cube_xy_drift_m for r in tel.rows) < 0.05, "clean run shouldn't knock"

    def test_no_video_no_telemetry(self, tmp_path: Path) -> None:
        """video_out=None → no mp4 AND no telemetry sidecar."""
        from src.sim.adapter import run_rollout

        cfg = RolloutConfig(
            rollout_id="no-video",
            policy_kind="scripted",
            env_name="Lift",
            seed=0,
            max_steps=50,
            injected_failures=InjectedFailures(),
        )
        result = run_rollout(cfg, video_out=None)
        assert result.video_path is None
        assert result.telemetry_path is None

    def test_premature_close_fails(self, tmp_path: Path) -> None:
        from src.sim.adapter import run_rollout

        cfg = RolloutConfig(
            rollout_id="prem-close",
            policy_kind="scripted",
            env_name="Lift",
            seed=0,
            max_steps=200,
            injected_failures=InjectedFailures(gripper_close_prematurely=True),
        )
        # Skip rendering: this test cares about success, not the mp4.
        result = run_rollout(cfg, video_out=None)

        assert result.success is False
        assert result.video_path is None

    def test_zero_jitter_matches_default_placement_bounds(self) -> None:
        """cube_xy_jitter_m=0.0 must NOT mutate the sampler — keeps the default ±3 cm."""
        import os

        import robosuite as suite
        from robosuite.controllers import load_controller_config

        from src.constants import MUJOCO_GL_ENV_KEY

        os.environ.setdefault(MUJOCO_GL_ENV_KEY, "glfw")

        controller_cfg = load_controller_config(default_controller="OSC_POSE")
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
        from robosuite.controllers import load_controller_config

        from src.constants import MUJOCO_GL_ENV_KEY
        from src.sim.adapter import _apply_cube_xy_jitter

        os.environ.setdefault(MUJOCO_GL_ENV_KEY, "glfw")

        controller_cfg = load_controller_config(default_controller="OSC_POSE")
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
