"""Pure-arithmetic tests for src.costing. No API, no sim."""

from __future__ import annotations

from src.costing import (
    BASELINE_HOURLY_RATE_USD,
    BASELINE_SECONDS_PER_ROLLOUT,
    COST_PER_ROLLOUT_USD,
    CostTracker,
    baseline_cost_for,
    baseline_seconds_for,
    format_cost,
    format_duration,
)


class TestCostTracker:
    def test_zero_initial_cost(self) -> None:
        assert CostTracker().total_cost_usd == 0.0
        assert CostTracker().n_rollouts == 0

    def test_record_rollout_bumps_counter(self) -> None:
        t = CostTracker()
        t.record_rollout()
        assert t.n_rollouts == 1
        assert t.total_cost_usd == COST_PER_ROLLOUT_USD

    def test_accumulates_across_calls(self) -> None:
        t = CostTracker()
        for _ in range(30):
            t.record_rollout()
        assert t.n_rollouts == 30
        # 30 × $0.19 = $5.70 — the empirical full-run cost we use as the model.
        assert abs(t.total_cost_usd - 30 * COST_PER_ROLLOUT_USD) < 1e-9


class TestBaseline:
    def test_baseline_cost_for_zero_rollouts(self) -> None:
        assert baseline_cost_for(0) == 0.0

    def test_baseline_cost_one_rollout(self) -> None:
        # 2 min / 60 = 0.0333 hr * $75/hr = $2.50
        assert abs(baseline_cost_for(1) - 2.50) < 1e-9

    def test_baseline_cost_thirty_rollouts(self) -> None:
        # 30 * 2 min = 60 min = 1.0 hr * $75/hr = $75.00
        assert abs(baseline_cost_for(30) - 75.00) < 1e-9

    def test_baseline_seconds(self) -> None:
        assert baseline_seconds_for(10) == 10 * BASELINE_SECONDS_PER_ROLLOUT

    def test_constants_consistent(self) -> None:
        # Sanity check: $75/hr × 3min × N matches the helper.
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
