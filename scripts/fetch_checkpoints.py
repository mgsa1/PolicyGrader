"""Download robomimic pretrained policy checkpoints into artifacts/checkpoints/.

Currently fetches: BC-RNN, Lift, proficient-human dataset, low-dim observations,
~100% success on the trained policy's training distribution. Source: Stanford
rt_benchmark CDN (Mandlekar et al. 2021, robomimic v0.1 model zoo).

Lift is the only task in use post scope-cut to Lift-only. The deployment cohort
runs this policy under environmental perturbations (cube xy jitter) — see
docs/eval_methodology.md. Image-obs variants are larger and 10x slower at
inference; we use low-dim because the policy doesn't need pixels — the rollout
video is rendered separately for the vision judge.
"""

from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CHECKPOINT_DIR = REPO_ROOT / "artifacts" / "checkpoints"

CHECKPOINTS: dict[str, str] = {
    "lift_ph_low_dim.pth": (
        "http://downloads.cs.stanford.edu/downloads/rt_benchmark"
        "/model_zoo/lift/bc_rnn/lift_ph_low_dim_epoch_1000_succ_100.pth"
    ),
}


def fetch(name: str, url: str) -> Path:
    dest = CHECKPOINT_DIR / name
    if dest.exists():
        size_mb = dest.stat().st_size / 1024 / 1024
        print(f"SKIP  {name} already present ({size_mb:.1f} MB)")
        return dest

    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"GET   {url}")
    urllib.request.urlretrieve(url, dest)  # noqa: S310 — Stanford CDN, http url is upstream's choice
    size_mb = dest.stat().st_size / 1024 / 1024
    print(f"OK    {name} -> {dest.relative_to(REPO_ROOT)} ({size_mb:.1f} MB)")
    return dest


def main() -> int:
    for name, url in CHECKPOINTS.items():
        fetch(name, url)
    return 0


if __name__ == "__main__":
    sys.exit(main())
