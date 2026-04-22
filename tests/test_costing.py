"""Pure-arithmetic tests for src.costing. No API, no sim."""

from __future__ import annotations

from dataclasses import dataclass

from src.costing import (
    BASELINE_HOURLY_RATE_USD,
    BASELINE_SECONDS_PER_ROLLOUT,
    CostTracker,
    baseline_cost_for,
    baseline_seconds_for,
    format_cost,
    format_duration,
)


@dataclass
class _UsageStub:
    """Stand-in for an Anthropic SDK Usage object — only the fields we read."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0


class TestCostTracker:
    def test_zero_initial_cost(self) -> None:
        assert CostTracker().total_cost_usd == 0.0

    def test_input_only(self) -> None:
        # 1M input tokens at $15/M.
        t = CostTracker()
        t.add_usage(_UsageStub(input_tokens=1_000_000))
        assert t.total_cost_usd == 15.0

    def test_output_only(self) -> None:
        # 1M output tokens at $75/M.
        t = CostTracker()
        t.add_usage(_UsageStub(output_tokens=1_000_000))
        assert t.total_cost_usd == 75.0

    def test_mixed_with_cache(self) -> None:
        # 100k input + 10k output + 50k cache_read + 5k cache_create.
        t = CostTracker()
        t.add_usage(
            _UsageStub(
                input_tokens=100_000,
                output_tokens=10_000,
                cache_read_input_tokens=50_000,
                cache_creation_input_tokens=5_000,
            )
        )
        # 100k * 15/M = 1.50, 10k * 75/M = 0.75, 50k * 1.5/M = 0.075,
        # 5k * 18.75/M = 0.09375 -> 2.41875
        assert abs(t.total_cost_usd - 2.41875) < 1e-9

    def test_accumulates_across_calls(self) -> None:
        t = CostTracker()
        t.add_usage(_UsageStub(input_tokens=500_000, output_tokens=1_000))
        t.add_usage(_UsageStub(input_tokens=500_000, output_tokens=1_000))
        assert t.input_tokens == 1_000_000
        assert t.output_tokens == 2_000

    def test_missing_attrs_tolerated(self) -> None:
        # An object exposing only some of the expected attrs (e.g. an old
        # SDK shape) should not crash.
        @dataclass
        class _Partial:
            input_tokens: int = 1_000

        t = CostTracker()
        t.add_usage(_Partial())
        assert t.input_tokens == 1_000
        assert t.output_tokens == 0


class TestBaseline:
    def test_baseline_cost_for_zero_rollouts(self) -> None:
        assert baseline_cost_for(0) == 0.0

    def test_baseline_cost_one_rollout(self) -> None:
        # 3 min / 60 = 0.05 hr * $50/hr = $2.50
        assert abs(baseline_cost_for(1) - 2.50) < 1e-9

    def test_baseline_cost_thirty_rollouts(self) -> None:
        # 30 * 3 min = 90 min = 1.5 hr * $50/hr = $75
        assert abs(baseline_cost_for(30) - 75.0) < 1e-9

    def test_baseline_seconds(self) -> None:
        assert baseline_seconds_for(10) == 10 * BASELINE_SECONDS_PER_ROLLOUT

    def test_constants_consistent(self) -> None:
        # Sanity check: $50/hr × 3min × N matches the helper.
        n = 7
        expected = n * BASELINE_SECONDS_PER_ROLLOUT / 3600 * BASELINE_HOURLY_RATE_USD
        assert abs(baseline_cost_for(n) - expected) < 1e-9


class TestFormatters:
    def test_format_cost(self) -> None:
        assert format_cost(0) == "$0.00"
        assert format_cost(1.234) == "$1.23"
        assert format_cost(75) == "$75.00"

    def test_format_duration_minutes(self) -> None:
        assert format_duration(0) == "0m 0s"
        assert format_duration(45) == "0m 45s"
        assert format_duration(125) == "2m 5s"

    def test_format_duration_hours(self) -> None:
        # 1h 1m 5s = 3665 seconds
        assert format_duration(3665) == "1h 1m 5s"

    def test_format_duration_truncates_fractional(self) -> None:
        assert format_duration(59.9) == "0m 59s"
