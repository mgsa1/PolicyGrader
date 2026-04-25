"""Cost and wall-time accounting for one eval session.

Cost model: a flat $0.20 per rollout dispatched, summed across the run.
Empirical: a 30-rollout end-to-end agent run (planner + rollout-worker +
judges + reporter) lands around $6 of Anthropic API spend, i.e. ~$0.20
amortised per rollout. The tracker only ticks inside `_dispatch_rollout` —
phases that don't talk to Claude (idle, sim execution on the host, the
human-labeling phase) leave it at zero.

The industry baseline for the demo's "savings" framing is unchanged:
"a human reviewer at $75/hr × 3 min/rollout doing the same judgement
work." Without it, a 91% label accuracy is a vibes-number; with it,
it's "we matched a human reviewer at N× lower cost."
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field

# Per-rollout API cost. Empirical from the post-single-pass-judge runs:
# planner + rollout-worker + judges (only on failures) + reporter, all
# Managed Agents sessions, summed and divided by total rollouts.
COST_PER_ROLLOUT_USD = 0.20

# Industry-baseline parameters. 3 min/rollout is a sympathetic estimate —
# quick to confirm obvious successes, slower to diagnose ambiguous failures.
# $75/hr is mid-band for a robotics engineer doing eval review (loaded cost
# including benefits/overhead is typically higher than raw salary). Adjust
# in the report writer if the demo narrative wants a different framing.
BASELINE_HOURLY_RATE_USD = 75.0
BASELINE_SECONDS_PER_ROLLOUT = 180


@dataclass
class CostTracker:
    """Counts rollouts dispatched and prices them at COST_PER_ROLLOUT_USD.

    Pass the same instance to every dispatch path; call `record_rollout()`
    once per `_dispatch_rollout` invocation. The counter is the sole driver
    of `total_cost_usd` — phases that never call `record_rollout()` (planner
    setup, sim-only host work, human labeling) leave the cost at $0.

    Thread-safe: the orchestrator runs ~10 Managed Agents sessions
    concurrently. The internal lock serialises increments.
    """

    n_rollouts: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    def record_rollout(self) -> None:
        """Tick the rollout counter by one. Call once per dispatched rollout."""
        with self._lock:
            self.n_rollouts += 1

    @property
    def total_cost_usd(self) -> float:
        return self.n_rollouts * COST_PER_ROLLOUT_USD


def baseline_cost_for(n_rollouts: int) -> float:
    """Manual-review baseline cost: $75/hr × 3 min/rollout × N."""
    hours = n_rollouts * BASELINE_SECONDS_PER_ROLLOUT / 3600
    return hours * BASELINE_HOURLY_RATE_USD


def baseline_seconds_for(n_rollouts: int) -> int:
    """Manual-review baseline wall time if a single reviewer works sequentially."""
    return n_rollouts * BASELINE_SECONDS_PER_ROLLOUT


# Per-rollout review overhead beyond just watching: scrubbing back, reading
# notes, jotting a label. 60s is a sympathetic single-pass estimate.
BASELINE_REVIEW_OVERHEAD_S = 60


def estimated_video_duration_s(env_name: str, steps_taken: int | None = None) -> float:
    """Estimate a rollout video's playback duration in seconds.

    Uses steps_taken when provided (each rollout records at the env's
    control frequency, default 20 Hz, plus our 1 s post-success hold).
    Falls back to the Lift max if steps_taken is unknown (env_name is
    accepted for forward-compat but currently unused — we're Lift-only).
    """
    del env_name  # reserved for future multi-env support
    if steps_taken is not None and steps_taken > 0:
        return steps_taken / 20.0 + 1.0  # +1s for the post-success hold
    return 10.0  # Lift default (200 max_steps / 20 Hz)


def baseline_time_seconds_for_videos(durations_s: list[float]) -> float:
    """Time baseline = sum of clip durations + BASELINE_REVIEW_OVERHEAD_S per clip.

    Closer to a real reviewer's wall time than the flat 3 min/rollout cost
    baseline — they only need to watch each clip once + take a note.
    """
    return sum(d + BASELINE_REVIEW_OVERHEAD_S for d in durations_s)


def format_duration(seconds: float) -> str:
    """Render a wall-clock duration as 'Hh Mm Ss' (or 'Mm Ss' when under 1 h)."""
    total = int(seconds)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m}m {s}s"
    return f"{m}m {s}s"


def format_cost(usd: float) -> str:
    """Render a dollar cost as '$X.XX' (two decimals, no thousands separator)."""
    return f"${usd:.2f}"
