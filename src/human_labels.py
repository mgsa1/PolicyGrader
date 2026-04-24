"""Human-label source of calibration ground truth.

The host writes one HumanLabel per rollout the human reviewer has classified
during the calibration phase (between rollout and judge — see
src/orchestrator.py::_run_label_phase). This module owns:

  - sampling which rollouts go to the labeler (scripted-cohort only,
    stratified roughly 1/3 successes + 2/3 failures);
  - append-only persistence to mirror_root/human_labels.jsonl;
  - resume-from-disk reads for the labeling UI;
  - per-label calibration computation that joins human labels with the judge
    findings, producing the precision/recall numbers the dashboard
    decorates deployment findings with.

Deployment rollouts never enter the human labeler's queue — they're the
subjects of calibration trust, not inputs to it.
"""

from __future__ import annotations

import json
import random
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path

from src.memory_layout import HUMAN_LABELS_FILE
from src.schemas import HumanLabel, HumanLabelValue

# On-disk human_labels.jsonl files from prior taxonomies carry labels that no
# longer exist in the HumanLabelValue Literal. We remap on READ — disk artifacts
# are never rewritten — so old runs open cleanly in the UI without requiring a
# migration script. In-memory typed values are always the current 2-mode set.
# Keep this table synced with the FailureMode enum + the taxonomy collapse
# history; see the "judge simplification history" pitfall in claude.md §16.
_LEGACY_LABEL_MAP: dict[str, HumanLabelValue] = {
    "gripper_slipped": "failed_grip",
    "gripper_not_open": "missed_approach",  # see semantic boundary in docs/taxonomy.md
    "knock_object_off_table": "missed_approach",
    "premature_release": "failed_grip",
    "approach_miss": "missed_approach",  # older alias for missed_approach
    "insertion_misalignment": "other",
    "wrong_object_selected": "other",
    "gripper_collision": "other",
    "slip_during_lift": "failed_grip",  # older alias
}


def remap_legacy_label(raw: str) -> str:
    """Return the current-taxonomy label string for `raw`.

    Applied at every read site so past-run artifacts render with 2-mode
    labels without requiring on-disk migration. Unknown labels pass through
    unchanged — Pydantic validation downstream will reject them loudly
    rather than silently coercing.
    """
    return _LEGACY_LABEL_MAP.get(raw, raw)


# Default sample-size policy: clamp(10% of scripted rollouts, 6, 20). The floor
# keeps small runs labelable; the cap keeps big runs from overwhelming the
# human reviewer.
DEFAULT_FRAC = 0.10
DEFAULT_FLOOR = 6
DEFAULT_CAP = 20

# Stratification: 1/3 successes, 2/3 failures. Failures carry more diversity
# (multiple modes); successes are included to test whether the judge, when
# eventually presented with a pass label by the human, holds its tongue (the
# judge never emits `none`, but human `none` labels are coverage signal).
SUCCESS_SHARE = 1.0 / 3.0


def sample_for_labeling(
    candidates: Iterable[tuple[str, bool, str]],
    *,
    frac: float = DEFAULT_FRAC,
    floor: int = DEFAULT_FLOOR,
    cap: int = DEFAULT_CAP,
    seed: int = 0,
) -> list[str]:
    """Pick which rollouts the human labels.

    `candidates` is an iterable of `(rollout_id, sim_success, policy_kind)`.
    Only scripted rollouts are considered. Returns a list of rollout_ids the
    host will queue for human review.

    Stratification is best-effort: if one stratum is short, the deficit is
    filled from the other. Ordering of the result is successes-first then
    failures, preserved as the labeler's queue order.
    """
    scripted = [(rid, ok) for rid, ok, kind in candidates if kind == "scripted"]
    if not scripted:
        return []

    n_total = min(cap, max(floor, round(frac * len(scripted))))
    n_total = min(n_total, len(scripted))

    successes = [rid for rid, ok in scripted if ok]
    failures = [rid for rid, ok in scripted if not ok]

    # Target split — round so we hit n_total exactly even on odd totals.
    n_success_target = round(n_total * SUCCESS_SHARE)
    n_failure_target = n_total - n_success_target

    rng = random.Random(seed)
    rng.shuffle(successes)
    rng.shuffle(failures)

    picked_success = successes[: min(n_success_target, len(successes))]
    picked_failure = failures[: min(n_failure_target, len(failures))]

    # Fill any deficit from the other stratum.
    deficit = n_total - len(picked_success) - len(picked_failure)
    if deficit > 0:
        remaining_success = successes[len(picked_success) :]
        remaining_failure = failures[len(picked_failure) :]
        fill = (remaining_success + remaining_failure)[:deficit]
        # Preserve successes-first ordering when filling.
        picked_success.extend(f for f in fill if f in remaining_success)
        picked_failure.extend(f for f in fill if f in remaining_failure)

    return picked_success + picked_failure


def labels_path(mirror_root: Path) -> Path:
    return mirror_root / HUMAN_LABELS_FILE


def append_label(mirror_root: Path, label: HumanLabel) -> None:
    """Append one HumanLabel line to human_labels.jsonl (create if missing)."""
    path = labels_path(mirror_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(label.model_dump_json() + "\n")


def submit_label(
    mirror_root: Path,
    *,
    rollout_id: str,
    label: HumanLabelValue,
    note: str | None = None,
) -> HumanLabel:
    """Construct + persist a HumanLabel. Returns the record that was written."""
    record = HumanLabel(
        rollout_id=rollout_id,
        label=label,
        note=note,
        labeled_at=datetime.now(UTC),
    )
    append_label(mirror_root, record)
    return record


def read_labels(mirror_root: Path) -> list[HumanLabel]:
    """Read all HumanLabel records. Malformed lines are skipped silently.

    Legacy labels from prior taxonomies (e.g. `gripper_slipped`) are remapped
    to the current 2-mode set at read time — see `_LEGACY_LABEL_MAP`. The
    JSONL file itself is never rewritten; old runs open cleanly in the UI.
    """
    path = labels_path(mirror_root)
    if not path.exists():
        return []
    out: list[HumanLabel] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        raw_label = payload.get("label")
        if isinstance(raw_label, str):
            payload["label"] = remap_legacy_label(raw_label)
        try:
            out.append(HumanLabel.model_validate(payload))
        except Exception:
            # Tolerate hand-edits / partial flushes / labels that don't map
            # into the current taxonomy — the labeling UI is the canonical
            # writer and emits well-formed lines.
            continue
    return out


def labels_by_rollout(mirror_root: Path) -> dict[str, HumanLabel]:
    """Return {rollout_id: latest HumanLabel}. Last-write-wins on duplicates."""
    out: dict[str, HumanLabel] = {}
    for rec in read_labels(mirror_root):
        out[rec.rollout_id] = rec  # later records clobber earlier
    return out


def pending_rollouts(queue: list[str], mirror_root: Path) -> list[str]:
    """From a labeling queue, return the rollout_ids not yet labeled.

    Used by the labeling UI to resume where the human left off.
    """
    done = set(labels_by_rollout(mirror_root).keys())
    return [rid for rid in queue if rid not in done]
