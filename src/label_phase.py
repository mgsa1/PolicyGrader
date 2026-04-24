"""Host-side human labeling phase, shared between Plan A and Plan B.

Sits between rollout and judge. No Managed Agents session, no API calls — the
host reads the completed rollouts from dispatch_log.jsonl, asks the sampler
which ones the human should see, writes the queue to labeling_queue.json for
the Gradio UI to pick up, then blocks until every queued rollout has a
corresponding line in human_labels.jsonl.

`--skip-labeling` bypasses the blocking wait and writes a "skipped" queue
file — the dashboard then shows "calibration not measured (0 labels)".
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from src.human_labels import read_labels, sample_for_labeling
from src.runtime_state import RuntimeState

logger = logging.getLogger(__name__)

# Runtime.phase string shown on the progress strip between rollout and judge.
PHASE_LABEL = "BEGIN PHASE 2.5: LABELING"

# Host → UI handoff. Written once per run when the label phase starts.
LABELING_QUEUE_FILE = "labeling_queue.json"

DEFAULT_POLL_INTERVAL_SECONDS = 1.0


def _enumerate_completed_rollouts(mirror_root: Path) -> list[tuple[str, bool, str]]:
    """(rollout_id, sim_success, policy_kind) for every rollout in dispatch_log."""
    path = mirror_root / "dispatch_log.jsonl"
    if not path.exists():
        return []
    out: list[tuple[str, bool, str]] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if rec.get("tool") != "rollout":
            continue
        result = rec.get("result") or {}
        args = rec.get("args") or {}
        rid = result.get("rollout_id") or args.get("rollout_id")
        if not rid:
            continue
        out.append(
            (
                str(rid),
                bool(result.get("success", False)),
                str(args.get("policy_kind", "")),
            )
        )
    return out


def _write_queue(mirror_root: Path, queue: list[str], *, skipped: bool) -> None:
    path = mirror_root / LABELING_QUEUE_FILE
    path.write_text(
        json.dumps(
            {
                "queue": queue,
                "skipped": skipped,
                "created_at": time.time(),
            },
            indent=2,
        )
    )


def read_queue(mirror_root: Path) -> tuple[list[str], bool]:
    """Return (queue, skipped). ([], False) when no queue has been written yet."""
    path = mirror_root / LABELING_QUEUE_FILE
    if not path.exists():
        return [], False
    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError:
        return [], False
    return list(payload.get("queue") or []), bool(payload.get("skipped"))


def run_label_phase(
    runtime: RuntimeState,
    mirror_root: Path,
    *,
    skip_labeling: bool,
    sample_seed: int = 0,
    poll_interval_seconds: float = DEFAULT_POLL_INTERVAL_SECONDS,
) -> int:
    """Run the host-side label phase. Returns the number of labels collected.

    Blocks until every rollout in the sampled queue has a matching record in
    human_labels.jsonl, or returns 0 immediately when skip_labeling is True.
    `runtime.set_phase(PHASE_LABEL)` is called before blocking so the UI
    progress strip switches to the labeling chip; `runtime.n_labels_done`
    ticks up each poll so the UI banner updates live.
    """
    runtime.set_phase(PHASE_LABEL)
    runtime.append_chat("phase_marker", marker=PHASE_LABEL, skipped=skip_labeling)

    if skip_labeling:
        _write_queue(mirror_root, [], skipped=True)
        runtime.n_labels_target = 0
        runtime.n_labels_done = 0
        runtime.write_snapshot()
        logger.info("label phase skipped")
        return 0

    candidates = _enumerate_completed_rollouts(mirror_root)
    queue = sample_for_labeling(candidates, seed=sample_seed)
    _write_queue(mirror_root, queue, skipped=False)
    runtime.n_labels_target = len(queue)
    runtime.n_labels_done = 0
    runtime.write_snapshot()

    if not queue:
        logger.info("label phase: no scripted rollouts to sample; skipping")
        return 0

    logger.info(
        "label phase waiting for %d human labels on rollouts: %s",
        len(queue),
        ", ".join(queue),
    )
    queued_set = set(queue)
    while True:
        done_ids = {rec.rollout_id for rec in read_labels(mirror_root)}
        n_done = sum(1 for rid in queue if rid in done_ids)
        if n_done != runtime.n_labels_done:
            runtime.n_labels_done = n_done
            runtime.mark_event()
        if n_done >= len(queue):
            break
        # Anything labeled outside the queue is fine (resume across restarts);
        # only queued rollouts gate progression.
        _ = queued_set
        time.sleep(poll_interval_seconds)

    logger.info("label phase complete: %d labels collected", len(queue))
    return len(queue)
