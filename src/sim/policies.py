from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

import numpy as np


@runtime_checkable
class Policy(Protocol):
    """Per-rollout policy interface.

    Both pretrained (robomimic BC-RNN) and scripted (IK picker with injected
    failures) policies implement this. The orchestrator is the only consumer.
    """

    def reset(self) -> None:
        """Reset internal state (e.g. RNN hidden state) at the start of an episode."""

    def act(self, obs: dict[str, Any]) -> np.ndarray[Any, Any]:
        """Return one action vector for the current observation dict."""
