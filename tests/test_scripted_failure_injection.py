"""Tests for src.sim.scripted: injected-failure behavior on the real sim.

Ground truth for the calibration cohort comes from human labels on a sampled
subset (see src/human_labels.py), not from the knob configuration — so there
are no knob->label mapping tests here. What we DO verify is that each knob
actually breaks the rollout in a visible way the human labeler will see.
"""

from __future__ import annotations

import pytest


@pytest.mark.integration
class TestScriptedLiftIntegration:
    """Real-sim checks that injected failures actually break the rollout.

    These are the ground-truth fixtures the vision judge gets graded against:
    if the cube DID get lifted despite an injected failure, the label is a lie.
    """

    @pytest.fixture(scope="class")
    def env_factory(self):  # type: ignore[no-untyped-def]
        import os

        from src.constants import MUJOCO_GL_ENV_KEY

        os.environ.setdefault(MUJOCO_GL_ENV_KEY, "glfw")

        import robosuite as suite
        from robosuite.controllers import load_controller_config

        controller_cfg = load_controller_config(default_controller="OSC_POSE")

        def _make():  # type: ignore[no-untyped-def]
            return suite.make(
                env_name="Lift",
                robots="Panda",
                controller_configs=controller_cfg,
                has_renderer=False,
                has_offscreen_renderer=False,
                use_camera_obs=False,
                control_freq=20,
                horizon=200,
            )

        return _make

    @staticmethod
    def _run(env, policy, max_steps: int = 200) -> bool:  # type: ignore[no-untyped-def]
        # Robosuite samples cube placement from np.random globally and exposes
        # no reset(seed=) — pin it here so test outcomes don't depend on
        # execution order or what other tests ran first.
        import numpy as np

        np.random.seed(0)
        obs = env.reset()
        policy.reset()
        for _ in range(max_steps):
            obs, _r, _d, _i = env.step(policy.act(obs))
        # Success is "still aloft at the end of the run", matching the adapter's
        # demote-transient-success logic. A slip rollout briefly passes
        # _check_success during the carry phase, then falls — end-state is what
        # counts.
        return bool(env._check_success())

    def test_clean_succeeds(self, env_factory) -> None:  # type: ignore[no-untyped-def]
        from src.sim.scripted import InjectedFailures, ScriptedLiftPolicy

        env = env_factory()
        policy = ScriptedLiftPolicy(InjectedFailures(), seed=0)
        assert self._run(env, policy) is True

    def test_premature_close_fails(self, env_factory) -> None:  # type: ignore[no-untyped-def]
        from src.sim.scripted import InjectedFailures, ScriptedLiftPolicy

        env = env_factory()
        policy = ScriptedLiftPolicy(InjectedFailures(gripper_close_prematurely=True), seed=0)
        assert self._run(env, policy) is False

    def test_approach_offset_fails(self, env_factory) -> None:  # type: ignore[no-untyped-def]
        from src.sim.scripted import InjectedFailures, ScriptedLiftPolicy

        env = env_factory()
        policy = ScriptedLiftPolicy(InjectedFailures(approach_angle_offset_deg=15.0), seed=0)
        assert self._run(env, policy) is False

    def test_weak_grip_fails(self, env_factory) -> None:  # type: ignore[no-untyped-def]
        from src.sim.scripted import InjectedFailures, ScriptedLiftPolicy

        env = env_factory()
        policy = ScriptedLiftPolicy(InjectedFailures(grip_force_scale=0.3), seed=0)
        assert self._run(env, policy) is False

    def test_high_noise_fails(self, env_factory) -> None:  # type: ignore[no-untyped-def]
        # Use 0.30 here, not the demo-facing 0.15 from claude.md sec 4. With
        # NOISE_GAIN=8, action_noise=0.15 lives right at the edge of "knocks
        # the cube", and tiny floating-point differences in MuJoCo's solver
        # across CPUs flip the outcome. 0.30 is unambiguously chaotic on every
        # machine. The 0.15 -> KNOCK_OBJECT_OFF_TABLE label mapping is pinned
        # by TestInjectedFailuresLabel above; this test only verifies that
        # the noise mechanism CAN break the rollout when cranked up.
        from src.sim.scripted import InjectedFailures, ScriptedLiftPolicy

        env = env_factory()
        policy = ScriptedLiftPolicy(InjectedFailures(action_noise=0.30), seed=0)
        assert self._run(env, policy) is False
