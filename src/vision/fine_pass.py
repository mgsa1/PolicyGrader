"""Pass-2 vision judge: 2576px windowed taxonomy label + pointing.

CLAUDE.md sec 7 (Saturday PM): "sample 8-12 frames at 2576px windowed on the
failure range, ask for {taxonomy_label, point: [x,y], one_line_description}."

The taxonomy is the closed set in docs/taxonomy.md / src.sim.scripted.FailureMode.
The model MUST emit one of those labels — we re-validate via the FailureMode
StrEnum so a fuzzy answer fails loudly rather than corrupting metrics.

The `point` coordinate is in the FINE-PASS frame's pixel grid (2576px on the
long edge). Downstream UI overlays must scale from that grid, not from the
coarse 768px grid.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from anthropic import Anthropic

from src.constants import OPUS_MODEL_ID
from src.costing import CostTracker
from src.schemas import Pass2Annotation
from src.sim.scripted import FailureMode
from src.vision.frames import encode_jpeg_b64, read_frames, resize_long_edge, sample_indices

FINE_NUM_FRAMES = 14  # denser temporal coverage of the failure window
FINE_LONG_EDGE_PX = 2576
FINE_MAX_TOKENS = 1024
FINE_RANGE_PADDING_FRAMES = 8  # widen the coarse range by this on each side
# (catches the failure even when Pass-1's range is off by 1 second or so)

ALLOWED_LABELS = sorted(label.value for label in FailureMode if label != FailureMode.NONE)


def _load_taxonomy() -> str:
    """Embed docs/taxonomy.md verbatim — single source of truth for the label set."""
    return (Path(__file__).resolve().parents[2] / "docs" / "taxonomy.md").read_text()


_TAXONOMY_MARKDOWN = _load_taxonomy()

SYSTEM_PROMPT = f"""\
You are a robot manipulation eval judge. You will be shown {FINE_NUM_FRAMES} \
high-resolution frames from a SINGLE failed robot rollout. The task is one of:
  - Lift: a Franka Panda arm picks up a cube from a table.
  - NutAssemblySquare: a Franka Panda arm picks a square nut and places it on a square peg.
Identify the task from the first frame, then watch how it fails across the sequence.

Pick exactly ONE label from this closed set: {", ".join(ALLOWED_LABELS)}.
Do NOT pick `none` — Pass-2 only runs on confirmed failures.

CRITICAL — temporal reasoning. The decisive evidence may span only 2-3 \
consecutive frames and is often subtle. Walk through the frames in order and \
ask, between each adjacent pair:
  1. Did the cube move WITHOUT the arm touching it? (object moved on its own)
  2. Did the gripper fingers come together (close)? If yes, did they close \
     ON the cube or in empty space NEAR the cube?
  3. Did the cube briefly rise with the gripper, then drop?
  4. Did the arm visibly bump or jostle the cube before any grasp attempt?

The "obvious final state" frame (e.g. arm retreating with no cube held) is \
NOT the failure event itself — it's the consequence. Pick the label based \
on the EVENT (the contact, the close, the slip, the impact), not on the \
end state. If the only evidence you have is the end state, you've likely \
been given the wrong window — pick the closest specific label rather than \
defaulting to approach_miss.

Read the "Visual cue" column in the table below carefully — those are the \
discriminating features between modes that look similar:

{_TAXONOMY_MARKDOWN}

Common confusions to avoid (these have caused mis-labels in past runs):
  - approach_miss vs knock_object_off_table: if the cube visibly moves \
    BEFORE the gripper closes (or moves while the arm is still descending), \
    it's knock_object_off_table — even if the arm later closes on empty \
    space and retreats. The IMPACT is the failure, not the empty close.
  - approach_miss vs slip_during_lift: if the gripper visibly contacted the \
    cube and lifted it briefly before losing it, it's slip_during_lift, \
    NOT approach_miss. slip requires evidence of partial pickup — look for \
    the cube briefly above the table surface in any frame.
  - approach_miss vs insertion_misalignment: insertion_misalignment requires \
    a SUCCESSFUL pick followed by a failed PLACEMENT (only relevant for \
    NutAssemblySquare — nut held above peg but offset).

Default-to-approach_miss is the failure mode of this judge — resist it. \
If you're unsure, look one more time for cube motion or gripper-cube contact.

Then pick the SINGLE most diagnostic frame and a pixel coordinate on the \
visual evidence — the object, the offending finger, the misalignment axis. \
The coordinate is in the resolution of the frame as shown to you (long edge \
{FINE_LONG_EDGE_PX} px).

Respond with ONE valid JSON object and NOTHING else. Schema:
  {{"taxonomy_label": <one of the labels above>,
    "point": [x, y],
    "description": <one short sentence naming the EVENT, not the end state>}}

x and y are integers in pixel coordinates of the chosen frame. Prefer "other" \
ONLY for genuinely unrecognized failures — if any specific label fits, use it.
"""


def _coarse_indices_to_original(
    coarse_range: tuple[int, int],
    coarse_total: int,
    original_total: int,
) -> tuple[int, int]:
    """Map [start, end] from coarse-sample indices back to original-mp4 indices."""
    coarse_indices = sample_indices(original_total, coarse_total)
    if not coarse_indices:
        return 0, 0
    start = coarse_indices[max(0, min(coarse_range[0], len(coarse_indices) - 1))]
    end = coarse_indices[max(0, min(coarse_range[1], len(coarse_indices) - 1))]
    return start, end


def _build_image_blocks(
    video_path: Path,
    coarse_range: tuple[int, int] | None,
    coarse_total: int,
) -> list[dict[str, object]]:
    """Sample 2576px frames from a window around the coarse failure range."""
    frames = read_frames(video_path)
    n = len(frames)

    if coarse_range is None or n == 0:
        # Defensive: coarse said "fail" with no range, or empty video. Just
        # sample across the whole clip — better than crashing.
        window_start, window_end = 0, max(0, n - 1)
    else:
        orig_start, orig_end = _coarse_indices_to_original(coarse_range, coarse_total, n)
        window_start = max(0, orig_start - FINE_RANGE_PADDING_FRAMES)
        window_end = min(n - 1, orig_end + FINE_RANGE_PADDING_FRAMES)

    window_len = window_end - window_start + 1
    local_indices = sample_indices(window_len, FINE_NUM_FRAMES)
    indices = [window_start + i for i in local_indices]

    blocks: list[dict[str, object]] = []
    for sampled_index, original_index in enumerate(indices):
        frame = resize_long_edge(frames[original_index], FINE_LONG_EDGE_PX)
        blocks.append({"type": "text", "text": f"Frame {sampled_index}:"})
        blocks.append(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": encode_jpeg_b64(frame),
                },
            }
        )
    return blocks


def _parse_annotation(raw: str) -> Pass2Annotation:
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
        if text.endswith("```"):
            text = text[:-3].strip()

    payload = json.loads(text)
    label_str = payload["taxonomy_label"]
    # Re-validate against the closed set. FailureMode(label_str) raises
    # ValueError on an unknown label, which is exactly what we want.
    label = FailureMode(label_str)
    if label == FailureMode.NONE:
        raise ValueError("Pass 2 must not emit 'none' — that's a Pass-1 verdict")

    point = payload["point"]
    x, y = int(point[0]), int(point[1])
    description = str(payload["description"]).strip()

    return Pass2Annotation(taxonomy_label=label, point=(x, y), description=description)


def fine_pass(
    video_path: Path,
    coarse_range: tuple[int, int] | None,
    *,
    coarse_total: int,
    client: Anthropic | None = None,
    cost_tracker: CostTracker | None = None,
) -> Pass2Annotation:
    """Run the Pass-2 fine vision judge on a recorded rollout mp4.

    `coarse_range` is the (start, end) tuple Pass 1 returned, in coarse-sample
    indices. `coarse_total` is the number of frames Pass 1 sampled (so we can
    map back to original-mp4 frame indices for windowing).

    `cost_tracker`, if provided, accumulates this call's token usage into the
    session-wide ledger that Phase 4 reports against the manual-review baseline.
    """
    if client is None:
        client = Anthropic()

    image_blocks = _build_image_blocks(video_path, coarse_range, coarse_total)

    response = client.messages.create(
        model=OPUS_MODEL_ID,
        max_tokens=FINE_MAX_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": cast(Any, image_blocks)}],
    )

    if cost_tracker is not None:
        cost_tracker.add_usage(response.usage)

    raw = "".join(block.text for block in response.content if block.type == "text")
    return _parse_annotation(raw)
