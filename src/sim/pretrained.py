"""Wraps a robomimic BC-RNN checkpoint as a Policy.

Robomimic owns the actual policy class (RNN hidden state, normalization,
torch device handling). This module is the boundary that hides those
specifics — the orchestrator only sees `Policy.reset()` / `Policy.act(obs)`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import robomimic.utils.file_utils as FileUtils

from src.sim.policies import Policy


def _patch_legacy_algo_config(ckpt_dict: dict[str, Any]) -> dict[str, Any]:
    """Inject keys added in robomimic v0.3 algo schema that v0.1/v0.2 checkpoints lack.

    The Stanford BC-RNN checkpoints were saved against the v0.1 schema. The v0.3
    BC algo factory probes `algo.transformer.enabled` to dispatch BC vs BC-RNN vs
    BC-Transformer. With a locked legacy config that key is missing and access
    raises. update_config() in robomimic only migrates obs modality keys, not algo.
    """
    config_dict = json.loads(ckpt_dict["config"])
    algo = config_dict.setdefault("algo", {})
    if "transformer" not in algo:
        algo["transformer"] = {"enabled": False}
    ckpt_dict["config"] = json.dumps(config_dict)
    return ckpt_dict


def _upgrade_legacy_controller(legacy: dict[str, Any], robot: str) -> dict[str, Any]:
    """Wrap a v1.4-era arm controller dict in robosuite v1.5's composite format.

    Delegates to robosuite's own migration helper (used by their demo_control.py)
    so we inherit the canonical translation of damping->damping_ratio,
    control_delta->input_type, gripper defaults, etc. Robosuite ships the helper
    but does not call it automatically — env users must invoke it themselves.

    Known limitation: on robosuite 1.5 the upgraded OSC_POSE controller produces
    delta actions in base frame by default, while robomimic 0.1's BC-RNN
    checkpoints were collected under 1.4's world-frame default. Forcing
    input_ref_frame="world" here was tried and did not recover task success
    across Lift or Square, so the upgrade is left at library defaults. See
    docs/eval_methodology.md for the downstream implication on deployment
    failure rate.
    """
    from robosuite.controllers.composite.composite_controller_factory import (
        refactor_composite_controller_config,
    )

    upgraded: dict[str, Any] = refactor_composite_controller_config(
        legacy, robot_type=robot, arms=["right"]
    )
    return upgraded


class RobomimicPolicy(Policy):
    def __init__(self, checkpoint_path: Path, device: str = "cpu") -> None:
        self._checkpoint_path = checkpoint_path
        ckpt_dict = FileUtils.maybe_dict_from_checkpoint(ckpt_path=str(checkpoint_path))
        ckpt_dict = _patch_legacy_algo_config(ckpt_dict)
        self._policy, self._ckpt_dict = FileUtils.policy_from_checkpoint(
            ckpt_dict=ckpt_dict,
            device=device,
            verbose=False,
        )

    @property
    def env_name(self) -> str:
        name = self._ckpt_dict["env_metadata"]["env_name"]
        assert isinstance(name, str)
        return name

    def env_kwargs_for_robosuite(self) -> dict[str, Any]:
        """Return env_kwargs ready to pass into `robosuite.make(...)`.

        Differs from the raw checkpoint env_kwargs only in the controller
        config, which is upgraded to robosuite v1.5's composite format.
        """
        kwargs: dict[str, Any] = dict(self._ckpt_dict["env_metadata"]["env_kwargs"])
        legacy_ctrl = kwargs.get("controller_configs")
        if isinstance(legacy_ctrl, dict) and legacy_ctrl.get("type") != "BASIC":
            robot = kwargs.get("robots", ["Panda"])[0]
            kwargs["controller_configs"] = _upgrade_legacy_controller(legacy_ctrl, robot)
        return kwargs

    def reset(self) -> None:
        self._policy.start_episode()

    def act(self, obs: dict[str, Any]) -> np.ndarray[Any, Any]:
        # robosuite 1.5 emits "object-state" where v0.1-trained policies expect
        # "object". Alias rather than mutate, so callers keep both keys.
        if "object-state" in obs and "object" not in obs:
            obs = {**obs, "object": obs["object-state"]}
        action = self._policy(ob=obs)
        return np.asarray(action, dtype=np.float32)
