"""Smoke: end-to-end Plan-B run with four specialized agents in parallel.

CLAUDE.md §3 Plan B. Four roles, K-way fan-out on the rollout + judge phases.
Same artifact tree as Plan A's smoke (plan.md, test_matrix.csv, rollouts/*,
findings.jsonl, report.md under mirror_root) so the Gradio UI reads it
without changes.

Cost guardrail: hits the real Anthropic API on ~2+2K sessions. Keep the goal
modest until you've confirmed the 16-rollout budget. Plan B's wall-clock is
~1/3 of Plan A's; cost is roughly equal.

Usage:
  source .venv/bin/activate
  ANTHROPIC_API_KEY=... python scripts/smoke_agent_parallel.py
  ANTHROPIC_API_KEY=... python scripts/smoke_agent_parallel.py --k-workers 4
"""

from __future__ import annotations

import argparse
import logging
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from anthropic import Anthropic  # noqa: E402

from src.costing import (  # noqa: E402
    baseline_cost_for,
    baseline_seconds_for,
    format_cost,
    format_duration,
)
from src.multi_orchestrator import run_multi_agent  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_RUNS_ROOT = REPO_ROOT / "artifacts" / "runs"
DEFAULT_GOAL = (
    "Mixed Lift eval: 8 calibration rollouts (scripted policy on Lift — "
    "3 clean, 5 with injected failures covering all four failure-injection "
    "parameters) and 8 deployment rollouts (pretrained BC-RNN on Lift under "
    "cube_xy_jitter_m=0.15 m perturbation). Use seeds 0..7. Cap each rollout "
    "at 200 steps."
)


def _mint_run_id() -> str:
    return f"evalb_{secrets.token_hex(3)}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--goal", default=DEFAULT_GOAL, help="One-line evaluation goal.")
    parser.add_argument(
        "--runs-root",
        type=Path,
        default=DEFAULT_RUNS_ROOT,
        help="Parent dir for run artifact trees. Each run lives under <runs-root>/<run_id>/.",
    )
    parser.add_argument("--run-id", default=None, help="Explicit run ID; defaults to evalb_<6hex>.")
    parser.add_argument(
        "--k-workers",
        type=int,
        default=4,
        help="Parallel-worker count for both rollout and judge phases (default 4).",
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    run_id = args.run_id or _mint_run_id()
    mirror_root = args.runs_root / run_id

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    client = Anthropic()
    print(f"run_id={run_id}  k_workers={args.k_workers}", flush=True)
    print(f"mirror_root={mirror_root}", flush=True)

    result = run_multi_agent(
        client,
        user_goal=args.goal,
        mirror_root=mirror_root,
        k_workers=args.k_workers,
        run_id=run_id,
    )

    print("\n=== Per-phase stop reasons ===", flush=True)
    for phase, stops in result.stops.items():
        if not stops:
            print(f"  {phase:8s}  (skipped)")
        elif len(stops) == 1:
            print(f"  {phase:8s}  {stops[0]}")
        else:
            summary = ", ".join(f"w{i}:{s}" for i, s in enumerate(stops))
            print(f"  {phase:8s}  [{summary}]")

    pipeline_cost = result.cost_tracker.total_cost_usd
    base_cost = baseline_cost_for(result.n_rollouts)
    base_time = baseline_seconds_for(result.n_rollouts)
    print("\n=== Cost & time vs manual-review baseline ===", flush=True)
    print(f"  scenarios:        {result.n_rollouts}")
    print(f"  k_workers:        {result.k_workers}")
    print(f"  pipeline cost:    {format_cost(pipeline_cost)}")
    print(f"  baseline cost:    {format_cost(base_cost)}  (manual reviewer @ $75/hr × 3min)")
    print(f"  pipeline time:    {format_duration(result.elapsed_seconds)}")
    print(f"  baseline time:    {format_duration(base_time)}  (sequential reviewer)")

    print(f"\nArtifacts mirrored under: {mirror_root}", flush=True)
    all_ok = all(s == "end_turn" for stops in result.stops.values() for s in stops)
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
