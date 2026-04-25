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
from src.ui.styles import html_escape, num

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


def header_html(mirror_root: Path) -> str:
    """One-line header: progress pill on the left, current rollout id on the right.

    Replaces the previous two stacked elements (status + "Now labeling: …") so
    the labeling pane sits flush to the video and the buttons stay above the
    fold on smaller screens.
    """
    state = load_state(mirror_root)
    if state.skipped:
        return _status_pill("Labeling skipped (--skip-labeling).", rollout_id=None, muted=True)
    if state.n_total == 0:
        return _status_pill("Queue pending…", rollout_id=None, muted=True)
    if state.is_complete:
        return _status_pill(
            f"Done · <b>{num(str(state.n_total))}</b> reviewed.",
            rollout_id=None,
            muted=False,
        )
    return _status_pill(
        f"Labeling: <b>{num(f'{state.n_done} / {state.n_total}')}</b>",
        rollout_id=state.current_rollout_id,
        muted=False,
    )


def _status_pill(html: str, *, rollout_id: str | None, muted: bool) -> str:
    rollout_html = (
        f'<span class="pg-labeling-rid">now labeling <code>{html_escape(rollout_id)}</code></span>'
        if rollout_id
        else ""
    )
    klass = "pg-labeling-header" + (" muted" if muted else "")
    return f'<div class="{klass}"><span>{html}</span>{rollout_html}</div>'


def current_video_path(mirror_root: Path) -> str | None:
    """Absolute path to the pending rollout's mp4, or None if no work."""
    state = load_state(mirror_root)
    rid = state.current_rollout_id
    if rid is None:
        return None
    video = mirror_root / "rollouts" / f"{rid}.mp4"
    return str(video) if video.exists() else None


def current_video_html(mirror_root: Path) -> str:
    """Raw HTML5 <video muted autoplay loop playsinline> for the pending rollout.

    We bypass gr.Video here because (a) it has no `muted` toggle and browsers
    block autoplay on un-muted clips, and (b) injecting a <script> into a
    gr.HTML to mute the player from JS doesn't work — Gradio renders HTML via
    Svelte's {@html ...} which uses innerHTML, and innerHTML never executes
    <script> tags. The gallery cards in src/ui/panes/live.py already use the
    same raw-tag pattern.
    """
    path = current_video_path(mirror_root)
    if path is None:
        return (
            '<div class="pg-labeling__video-empty" '
            'style="height:360px;display:flex;align-items:center;'
            "justify-content:center;background:var(--pg-surface-2);"
            "border-radius:var(--pg-radius-sm);color:var(--pg-ink-4);"
            'font-style:italic;">No rollout pending review.</div>'
        )
    src = f"/gradio_api/file={path}"
    return (
        f'<video src="{src}" autoplay loop muted playsinline preload="auto" '
        'style="width:100%;height:360px;background:#000;'
        'border-radius:var(--pg-radius-sm);object-fit:contain;"></video>'
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
