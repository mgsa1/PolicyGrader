"""H4 smoke: run 4 scripted Lift rollouts in parallel via spawn pool.

Acceptance: all 4 workers complete without crashing, results carry the right
ground-truth labels, and wall time is meaningfully shorter than 4x sequential.

Why spawn (claude.md sec 16): MuJoCo contexts are not fork-safe. Each worker
must build its own env. Pydantic configs and pathlib.Path arguments pickle
cleanly across the spawn boundary; the env itself never crosses it.

If this fails on Saturday, the documented fallback is sequential — 30 scripted
rollouts at ~3 s each is < 2 min, well within demo budget.
"""

from __future__ import annotations

import multiprocessing as mp
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.schemas import RolloutConfig, RolloutResult  # noqa: E402
from src.sim.scripted import InjectedFailures  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "artifacts" / "smoke" / "parallel"

CONFIGS: list[tuple[str, InjectedFailures]] = [
    ("clean-0", InjectedFailures()),
    ("approach-miss", InjectedFailures(approach_angle_offset_deg=15.0)),
    ("weak-grip", InjectedFailures(grip_force_scale=0.3)),
    ("noisy", InjectedFailures(action_noise=0.15)),
]


def _build_configs() -> list[RolloutConfig]:
    return [
        RolloutConfig(
            rollout_id=name,
            policy_kind="scripted",
            env_name="Lift",
            seed=i,
            max_steps=200,
            injected_failures=failures,
        )
        for i, (name, failures) in enumerate(CONFIGS)
    ]


def _worker(args: tuple[RolloutConfig, Path]) -> RolloutResult:
    """Top-level (picklable) worker. Imports happen inside the spawned interpreter."""
    config, video_out = args
    from src.sim.adapter import run_rollout

    return run_rollout(config, video_out=video_out)


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    configs = _build_configs()
    work = [(cfg, OUT_DIR / f"{cfg.rollout_id}.mp4") for cfg in configs]

    ctx = mp.get_context("spawn")
    t0 = time.perf_counter()
    with ctx.Pool(processes=len(work)) as pool:
        results = pool.map(_worker, work)
    elapsed = time.perf_counter() - t0

    print(f"OK  {len(results)} rollouts in {elapsed:.1f}s ({elapsed / len(results):.1f}s/each)")
    for r in results:
        flag = "PASS" if r.success else "FAIL"
        print(f"  {flag}  {r.rollout_id:20s}  steps={r.steps_taken:3d}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
