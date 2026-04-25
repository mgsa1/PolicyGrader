"""Labeling pane — the human reviewer's interface during the calibration phase.

Sits at the top of the Judge Calibration tab. When the orchestrator is in
PHASE_LABEL and there are still rollouts in `labeling_queue.json` without a
corresponding line in `human_labels.jsonl`, this pane shows one pending
rollout at a time (video + keyframe) and a closed-set radio for the reviewer
to label it.

Once the queue is exhausted (or labeling was skipped at --skip-labeling),
the pane renders a completion banner and the metrics view below becomes the
main surface.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.human_labels import labels_by_rollout, submit_label
from src.label_phase import read_queue
from src.schemas import HumanLabelValue
from src.ui.styles import empty, html_escape, num

# Radio choices are (display label, stored value). `none` appears first because
# it's the expected outcome on the successes in the sampled set; the
# failure modes appear in taxonomy order. `other` is the escape hatch for
# anything that doesn't fit the named modes.
LABELING_CHOICES: list[tuple[str, HumanLabelValue]] = [
    ("success (clean pick)", "none"),
    ("missed_approach", "missed_approach"),
    ("failed_grip", "failed_grip"),
    ("other", "other"),
]


@dataclass(frozen=True)
class LabelingState:
    """Snapshot of labeling progress for the pane's renderers."""

    queue: list[str]
    skipped: bool
    done_ids: set[str]

    @property
    def pending(self) -> list[str]:
        return [rid for rid in self.queue if rid not in self.done_ids]

    @property
    def current_rollout_id(self) -> str | None:
        pending = self.pending
        return pending[0] if pending else None

    @property
    def n_done(self) -> int:
        return sum(1 for rid in self.queue if rid in self.done_ids)

    @property
    def n_total(self) -> int:
        return len(self.queue)

    @property
    def is_complete(self) -> bool:
        return self.n_done >= self.n_total and self.n_total > 0

    @property
    def has_work(self) -> bool:
        return bool(self.pending) and not self.skipped


def load_state(mirror_root: Path) -> LabelingState:
    queue, skipped = read_queue(mirror_root)
    done_ids = set(labels_by_rollout(mirror_root).keys())
    return LabelingState(queue=queue, skipped=skipped, done_ids=done_ids)


def panel_visible(mirror_root: Path) -> bool:
    """True when the labeling panel should be shown — there's a queue with work
    left to do AND the user hasn't opted out via --skip-labeling."""
    return load_state(mirror_root).has_work


def queue_status_html(mirror_root: Path) -> str:
    """Single-line status pill at the top of the labeling panel."""
    state = load_state(mirror_root)
    if state.skipped:
        return _status_pill("Labeling skipped (--skip-labeling).", muted=True)
    if state.n_total == 0:
        return _status_pill("Queue pending…", muted=True)
    if state.is_complete:
        return _status_pill(f"Done · <b>{num(str(state.n_total))}</b> reviewed.", muted=False)
    return _status_pill(
        f"Labeling: <b>{num(f'{state.n_done} / {state.n_total}')}</b>",
        muted=False,
    )


def _status_pill(html: str, *, muted: bool) -> str:
    base = "padding:8px 12px;border-radius:8px;margin-bottom:8px;font-size:13px;"
    if muted:
        style = base + "background:var(--pg-surface-2);color:var(--pg-ink-3);"
    else:
        style = (
            base + "background:var(--pg-cal-bg);border-left:3px solid var(--pg-cal);"
            "color:var(--pg-ink-1);"
        )
    return f'<div class="pg-cal-status" style="{style}">{html}</div>'


def current_video_path(mirror_root: Path) -> str | None:
    """Absolute path to the pending rollout's mp4, or None if no work."""
    state = load_state(mirror_root)
    rid = state.current_rollout_id
    if rid is None:
        return None
    video = mirror_root / "rollouts" / f"{rid}.mp4"
    return str(video) if video.exists() else None


def current_rollout_header_html(mirror_root: Path) -> str:
    """Small block identifying the rollout currently up for labeling."""
    state = load_state(mirror_root)
    rid = state.current_rollout_id
    if rid is None:
        if state.is_complete:
            return ""
        return empty("No rollout queued for labeling.", small=True)
    return (
        '<div class="pg-cal-current" '
        'style="padding:8px 12px;font-size:13px;color:var(--pg-ink-2);">'
        f"Now labeling: <code>{html_escape(rid)}</code>"
        "</div>"
    )


def submit_and_advance(
    mirror_root: Path,
    *,
    label: HumanLabelValue,
    note: str | None,
) -> None:
    """Persist the current rollout's label, bumping the queue forward.

    The UI callback maps (label_choice, note) → this function. The next tick
    of the page pulls the freshly-labeled-minus-one pending list and refreshes.
    """
    state = load_state(mirror_root)
    rid = state.current_rollout_id
    if rid is None:
        return
    cleaned_note = (note or "").strip() or None
    submit_label(mirror_root, rollout_id=rid, label=label, note=cleaned_note)
