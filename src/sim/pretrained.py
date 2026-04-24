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


def _controller_passthrough(legacy: dict[str, Any], robot: str) -> dict[str, Any]:
    """No-op on robosuite 1.4: the checkpoint's OSC_POSE dict is already native.

    Robomimic 0.3.0's pretrained checkpoints were trained against robosuite
    1.4.x, whose `load_controller_config(default_controller="OSC_POSE")`
    schema matches what the checkpoint's env_metadata ships. We pin
    robosuite==1.4.1 in requirements.txt so no format translation is needed.
    """
    del robot  # retained kwarg for call-site stability
    return legacy


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

        On robosuite 1.4.1 the checkpoint's own controller_configs dict is
        the native OSC_POSE format — no translation needed, just pass through.
        """
        kwargs: dict[str, Any] = dict(self._ckpt_dict["env_metadata"]["env_kwargs"])
        legacy_ctrl = kwargs.get("controller_configs")
        if isinstance(legacy_ctrl, dict):
            robot = kwargs.get("robots", ["Panda"])[0]
            kwargs["controller_configs"] = _controller_passthrough(legacy_ctrl, robot)
        return kwargs

    def reset(self) -> None:
        self._policy.start_episode()

    def act(self, obs: dict[str, Any]) -> np.ndarray[Any, Any]:
        # Robosuite emits "object-state" as the concatenated object observable
        # key, but the checkpoint's obs_encoder was saved expecting "object".
        # Alias rather than mutate so callers keep both keys.
        if "object-state" in obs and "object" not in obs:
            obs = {**obs, "object": obs["object-state"]}
        action = self._policy(ob=obs)
        return np.asarray(action, dtype=np.float32)
