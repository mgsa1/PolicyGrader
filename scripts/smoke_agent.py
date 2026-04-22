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
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from anthropic import Anthropic  # noqa: E402

from src.orchestrator import run_all_phases, setup  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MIRROR_ROOT = REPO_ROOT / "artifacts" / "smoke" / "agent"
DEFAULT_GOAL = (
    "Smoke run: 5 scripted Lift scenarios — 2 clean and 3 injected (one per "
    "failure knob). Use seeds 0..4. Cap each rollout at 200 steps."
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--goal", default=DEFAULT_GOAL, help="One-line evaluation goal.")
    parser.add_argument(
        "--mirror-root",
        type=Path,
        default=DEFAULT_MIRROR_ROOT,
        help="Local mirror of /memories/ where rollout mp4s land.",
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    client = Anthropic()
    handle = setup(client)
    print(
        f"agent={handle.agent_id} env={handle.environment_id} session={handle.session_id}",
        flush=True,
    )

    stops = run_all_phases(
        client,
        handle,
        user_goal=args.goal,
        mirror_root=args.mirror_root,
    )

    print("\n=== Phase stop reasons ===", flush=True)
    for marker, stop in zip(
        ("PLANNER", "ROLLOUT", "JUDGE", "REPORT"),
        stops,
        strict=False,
    ):
        print(f"  {marker:8s}  {stop}")

    print(f"\nArtifacts mirrored under: {args.mirror_root}", flush=True)
    return 0 if all(s == "end_turn" for s in stops) else 1


if __name__ == "__main__":
    sys.exit(main())
