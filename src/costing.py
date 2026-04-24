"""Cost and wall-time accounting for one eval session.

Tracks tokens across every Anthropic call made during a session — the
Managed Agents reasoning phases plus the two Messages API vision passes —
multiplies by published Opus 4.7 pricing, and produces a single number the
report writer can quote against an industry baseline.

The industry baseline is the comparison frame for the demo: "a human
reviewer at $50/hr × 3 min/rollout doing the same judgement work." This is
what makes precision/recall mean something — without a baseline denominator,
a 91% label accuracy is a vibes-number. With the baseline, it's "we matched
a human reviewer at N× lower cost."
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field

# Opus 4.7 pricing per million tokens. Published on
# https://www.anthropic.com/pricing — update when the price sheet moves.
OPUS_4_7_INPUT_PER_MTOK = 15.0
OPUS_4_7_OUTPUT_PER_MTOK = 75.0
OPUS_4_7_CACHE_READ_PER_MTOK = 1.5  # 10% of input
OPUS_4_7_CACHE_WRITE_PER_MTOK = 18.75  # 1.25× input

# Industry-baseline parameters. 3 min/rollout is a sympathetic estimate —
# quick to confirm obvious successes, slower to diagnose ambiguous failures.
# $75/hr is mid-band for a robotics engineer doing eval review (loaded cost
# including benefits/overhead is typically higher than raw salary). Adjust
# in the report writer if the demo narrative wants a different framing.
BASELINE_HOURLY_RATE_USD = 75.0
BASELINE_SECONDS_PER_ROLLOUT = 180


@dataclass
class CostTracker:
    """Running sum of token usage across one session. Mutable.

    Pass the same instance to every call site that touches an Anthropic
    response (Managed Agents event stream + each Messages API vision call).
    Call `add_usage(response.usage)` on any object that exposes the usual
    `*_tokens` attributes; missing attrs are tolerated.

    Thread-safe: the orchestrator runs ~10 Managed Agents sessions
    concurrently, each dispatching token-accumulating events from its own
    thread. The internal lock serializes add_usage() so increments don't race.
    total_cost_usd is a pure read of scalar fields — Python's GIL guarantees
    torn reads can only miss the last increment, which is acceptable for a
    live banner.
    """

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    def add_usage(self, usage: object) -> None:
        """Accumulate tokens from an Anthropic SDK Usage-shaped object."""
        with self._lock:
            for src_attr, tgt_attr in (
                ("input_tokens", "input_tokens"),
                ("output_tokens", "output_tokens"),
                ("cache_read_input_tokens", "cache_read_tokens"),
                ("cache_creation_input_tokens", "cache_creation_tokens"),
            ):
                val = getattr(usage, src_attr, None)
                if val is not None:
                    setattr(self, tgt_attr, getattr(self, tgt_attr) + int(val))

    @property
    def total_cost_usd(self) -> float:
        return (
            self.input_tokens * OPUS_4_7_INPUT_PER_MTOK
            + self.output_tokens * OPUS_4_7_OUTPUT_PER_MTOK
            + self.cache_read_tokens * OPUS_4_7_CACHE_READ_PER_MTOK
            + self.cache_creation_tokens * OPUS_4_7_CACHE_WRITE_PER_MTOK
        ) / 1_000_000


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
