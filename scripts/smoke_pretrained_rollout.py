"""Smoke: run one Lift BC-RNN rollout, optionally as a perturbation sweep.

Two modes:

  (default)  Single rollout at cube_xy_jitter_m=0.0 — sanity check that the
             policy loads and succeeds on its training distribution.

  --sweep    Sweep cube_xy_jitter_m over SWEEP_VALUES with SWEEP_SEEDS_PER_VALUE
             seeds each, reporting the failure rate per value. Used once during
             scope-cut to pick the deployment perturbation (see
             docs/eval_methodology.md).

Bypasses robomimic.utils.env_utils.create_env_from_metadata because robomimic
0.3.0's env_robosuite adapter still imports the legacy `mujoco_py` package,
which is dead on macOS arm64 / Python 3.12. The checkpoint's env_kwargs give
us everything needed to build the env via the adapter instead.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.constants import MUJOCO_GL_ENV_KEY  # noqa: E402

os.environ.setdefault(MUJOCO_GL_ENV_KEY, "glfw")

from src.schemas import RolloutConfig  # noqa: E402
from src.sim.adapter import run_rollout  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
CHECKPOINT = REPO_ROOT / "artifacts" / "checkpoints" / "lift_ph_low_dim.pth"
OUT_DIR = REPO_ROOT / "artifacts" / "smoke"
OUT_MP4 = OUT_DIR / "pretrained_rollout.mp4"

MAX_STEPS = 200  # Lift horizon in robomimic configs is 200

# Sweep parameters — see docs/eval_methodology.md for how the chosen value was
# picked. Keep this list short — each config runs SWEEP_SEEDS_PER_VALUE episodes.
SWEEP_VALUES: list[float] = [0.02, 0.05, 0.08, 0.12]
SWEEP_SEEDS_PER_VALUE = 8


def _one_rollout(jitter_m: float, seed: int, record_video: bool) -> bool:
    """Run one BC-RNN Lift rollout; return True if the policy succeeded."""
    cfg = RolloutConfig(
        rollout_id=f"lift-bcrnn-j{jitter_m:.2f}-s{seed}",
        policy_kind="pretrained",
        env_name="Lift",
        seed=seed,
        max_steps=MAX_STEPS,
        checkpoint_path=CHECKPOINT,
        cube_xy_jitter_m=jitter_m,
    )
    out = OUT_MP4 if record_video else None
    result = run_rollout(cfg, video_out=out)
    return result.success


def _single() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    success = _one_rollout(jitter_m=0.0, seed=0, record_video=True)
    print(
        f"OK  success={success}  path={OUT_MP4.relative_to(REPO_ROOT)}",
        flush=True,
    )
    return 0 if success else 2


def _sweep() -> int:
    print(
        f"Sweep: {len(SWEEP_VALUES)} values × {SWEEP_SEEDS_PER_VALUE} seeds "
        f"= {len(SWEEP_VALUES) * SWEEP_SEEDS_PER_VALUE} rollouts",
        flush=True,
    )
    print(f"{'jitter_m':>10s}  {'n_ok':>4s}  {'n_fail':>6s}  {'fail_rate':>9s}", flush=True)
    for jitter_m in SWEEP_VALUES:
        successes = 0
        for seed in range(SWEEP_SEEDS_PER_VALUE):
            ok = _one_rollout(jitter_m=jitter_m, seed=seed, record_video=False)
            successes += int(ok)
        n_fail = SWEEP_SEEDS_PER_VALUE - successes
        rate = n_fail / SWEEP_SEEDS_PER_VALUE
        print(f"{jitter_m:>10.2f}  {successes:>4d}  {n_fail:>6d}  {rate:>9.0%}", flush=True)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--sweep",
        action="store_true",
        help="Sweep cube_xy_jitter_m instead of running one sanity rollout.",
    )
    args = parser.parse_args()
    if not CHECKPOINT.exists():
        print(f"ERR  checkpoint missing at {CHECKPOINT} — run scripts/fetch_checkpoints.py")
        return 1
    return _sweep() if args.sweep else _single()


if __name__ == "__main__":
    sys.exit(main())
