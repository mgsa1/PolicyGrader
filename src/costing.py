"""Cost and wall-time accounting for one eval session.

Two distinct cost lines, NEVER conflate them:

1. **PolicyGrader cost** — the Anthropic API spend incurred by THIS pipeline.
   Starts accumulating the moment the first rollout is dispatched to Claude
   Opus 4.7 (i.e. when API communication begins) and stops when the last
   tool call completes. Empirically a flat ~$0.19 per rollout amortised
   across planner + rollout-worker + judges + reporter sessions. Phases
   that never call into Claude (idle, sim-only host work, the human-labeling
   phase) contribute $0.

2. **Human-reviewer baseline** — what the same eval would cost if a
   robotics engineer watched and classified each rollout video manually.
   Modeled as $75/hr × 2 min/rollout × N. The 2-minute figure is the
   average wall-time to view + classify one rollout video (a Lift clip
   is ~10 s, but the reviewer also scrubs back, reads notes, and writes
   the label). $75/hr is mid-band loaded labor cost for a robotics
   engineer doing eval review.

The demo headline is `PolicyGrader cost / human baseline cost` — without
the baseline, a 91% label accuracy is a vibes-number; with it, the line
reads "we matched a human reviewer at N× lower cost."
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field

# Per-rollout PolicyGrader API cost. Empirical anchor (2026-04-24): the
# 30-rollout end-to-end agent run on the post-single-pass-judge stack
# spent ~$5.70 of Anthropic API budget, i.e. ~$0.19 amortised per rollout.
# Re-baseline on the next clean full-length smoke and update if we drift.
COST_PER_ROLLOUT_USD = 0.19

# Industry-baseline parameters. 2 min/rollout is the average wall-time to
# view + classify one rollout video — quick on obvious successes, slower on
# ambiguous failures, plus scrub-back / note-taking overhead. $75/hr is
# mid-band for a robotics engineer doing eval review (loaded cost including
# benefits/overhead is typically higher than raw salary). Adjust in the
# report writer if the demo narrative wants a different framing.
BASELINE_HOURLY_RATE_USD = 75.0
BASELINE_SECONDS_PER_ROLLOUT = 120


@dataclass
class CostTracker:
    """PolicyGrader-side cost only — counts rollouts dispatched and
    prices them at COST_PER_ROLLOUT_USD.

    Pass the same instance to every dispatch path; call `record_rollout()`
    once per `_dispatch_rollout` invocation. The counter is the sole driver
    of `total_cost_usd` — phases that never call `record_rollout()` (planner
    setup before the first rollout, sim-only host work, the human-labeling
    phase) leave the cost at $0. This matches the framing that PolicyGrader
    cost only counts when we're actually communicating with Claude.

    The human-reviewer baseline is computed separately by `baseline_cost_for`
    and is NOT touched by this tracker — the baseline accumulates on
    wall-time / rollout-count regardless of whether any API call has fired.

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
    """Manual-review baseline cost: $75/hr × 2 min/rollout × N."""
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
