"""Smoke: end-to-end Plan-A run on a tiny scenario set.

CLAUDE.md sec 7 (Saturday PM): "End-to-end on 5 scenarios (mix of clean +
injected)." This script wires the orchestrator to a small goal and prints
the per-phase stop reasons + a summary of artifacts written.

Cost guardrail: this hits the real Anthropic API (Managed Agents + Messages
for the vision passes). Keep the goal short and the matrix small. The script
prints the artifact root so the user can `ls` it after.

Usage:
  source .venv/bin/activate
  ANTHROPIC_API_KEY=... python scripts/smoke_agent.py
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
from src.orchestrator import run_all_phases, setup  # noqa: E402

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
    """Generate a short, human-readable run ID. 6 hex chars = 16M space."""
    return f"eval_{secrets.token_hex(3)}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--goal", default=DEFAULT_GOAL, help="One-line evaluation goal.")
    parser.add_argument(
        "--runs-root",
        type=Path,
        default=DEFAULT_RUNS_ROOT,
        help="Parent dir for all run artifact trees. Each run lives under <runs-root>/<run_id>/.",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help="Explicit run ID. Defaults to a freshly-minted eval_<6hex>.",
    )
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument(
        "--skip-labeling",
        action="store_true",
        help=(
            "Bypass the host-side human-labeling phase. Useful for unattended "
            "smoke runs. Calibration will render as 'not measured' in the UI."
        ),
    )
    parser.add_argument(
        "--label-seed",
        type=int,
        default=0,
        help="Seed for the labeling-subset sampler.",
    )
    args = parser.parse_args()

    run_id = args.run_id or _mint_run_id()
    mirror_root = args.runs_root / run_id

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    client = Anthropic()
    handle = setup(client)
    print(
        f"run_id={run_id} agent={handle.agent_id} "
        f"env={handle.environment_id} session={handle.session_id}",
        flush=True,
    )
    print(f"mirror_root={mirror_root}", flush=True)

    result = run_all_phases(
        client,
        handle,
        user_goal=args.goal,
        mirror_root=mirror_root,
        run_id=run_id,
        skip_labeling=args.skip_labeling,
        label_seed=args.label_seed,
    )

    print("\n=== Phase stop reasons ===", flush=True)
    for marker, stop in zip(
        ("PLANNER", "ROLLOUT", "JUDGE", "REPORT"),
        result.stops,
        strict=False,
    ):
        print(f"  {marker:8s}  {stop}")

    pipeline_cost = result.cost_tracker.total_cost_usd
    base_cost = baseline_cost_for(result.n_rollouts)
    base_time = baseline_seconds_for(result.n_rollouts)
    print("\n=== Cost & time vs manual-review baseline ===", flush=True)
    print(f"  scenarios:        {result.n_rollouts}")
    print(f"  pipeline cost:    {format_cost(pipeline_cost)}")
    baseline_note = "(manual reviewer @ $75/hr × 3min/rollout)"
    print(f"  baseline cost:    {format_cost(base_cost)}  {baseline_note}")
    print(f"  pipeline time:    {format_duration(result.elapsed_seconds)}")
    print(f"  baseline time:    {format_duration(base_time)}  (sequential reviewer)")

    print(f"\nArtifacts mirrored under: {mirror_root}", flush=True)
    return 0 if all(s == "end_turn" for s in result.stops) else 1


if __name__ == "__main__":
    sys.exit(main())
