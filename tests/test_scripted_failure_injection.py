"""Tests for src.sim.scripted: failure-mode label priority and injected-failure outcomes.

The label tests are pure (no sim) and verify the knob -> label mapping documented
in src/sim/scripted.py. The integration test is marked and runs a real Lift episode
with one failure injected to check it actually breaks the rollout — this is what
guarantees ground-truth labels we feed the vision judge are meaningful.
"""

from __future__ import annotations

import pytest

from src.sim.scripted import FailureMode, InjectedFailures


class TestInjectedFailuresLabel:
    def test_clean_config_is_none(self) -> None:
        assert InjectedFailures().to_label() == FailureMode.NONE

    def test_high_action_noise_wins(self) -> None:
        # Noise has highest priority: even with other failures set, noise dominates.
        f = InjectedFailures(
            action_noise=0.15,
            approach_angle_offset_deg=15.0,
            gripper_close_prematurely=True,
            grip_force_scale=0.3,
        )
        assert f.to_label() == FailureMode.KNOCK_OBJECT_OFF_TABLE

    def test_low_action_noise_does_not_trigger(self) -> None:
        # Below the 0.1 threshold the noise is small enough that the policy
        # should still succeed, so it must NOT label as a knock failure.
        assert InjectedFailures(action_noise=0.05).to_label() == FailureMode.NONE

    def test_approach_angle_labels_approach_miss(self) -> None:
        f = InjectedFailures(approach_angle_offset_deg=15.0)
        assert f.to_label() == FailureMode.APPROACH_MISS

    def test_premature_close_labels_approach_miss(self) -> None:
        # Closes before reaching cube => never grasps => same observable failure.
        f = InjectedFailures(gripper_close_prematurely=True)
        assert f.to_label() == FailureMode.APPROACH_MISS

    def test_weak_grip_labels_slip(self) -> None:
        f = InjectedFailures(grip_force_scale=0.3)
        assert f.to_label() == FailureMode.SLIP_DURING_LIFT

    def test_full_grip_is_clean(self) -> None:
        assert InjectedFailures(grip_force_scale=1.0).to_label() == FailureMode.NONE

    def test_approach_offset_beats_grip_scale(self) -> None:
        # Priority: approach_angle > premature_close > grip_force.
        f = InjectedFailures(approach_angle_offset_deg=15.0, grip_force_scale=0.3)
        assert f.to_label() == FailureMode.APPROACH_MISS


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
        from robosuite.controllers import load_composite_controller_config

        controller_cfg = load_composite_controller_config(controller="BASIC", robot="Panda")

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
        obs = env.reset()
        policy.reset()
        for _ in range(max_steps):
            obs, _r, _d, _i = env.step(policy.act(obs))
            if env._check_success():
                return True
        return False

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
