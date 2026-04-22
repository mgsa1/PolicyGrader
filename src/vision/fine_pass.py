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
from src.schemas import Pass2Annotation
from src.sim.scripted import FailureMode
from src.vision.frames import encode_png_b64, read_frames, resize_long_edge, sample_indices

FINE_NUM_FRAMES = 10  # midpoint of CLAUDE.md's 8-12 range
FINE_LONG_EDGE_PX = 2576
FINE_MAX_TOKENS = 1024
FINE_RANGE_PADDING_FRAMES = 4  # widen the coarse range by this on each side

ALLOWED_LABELS = sorted(label.value for label in FailureMode if label != FailureMode.NONE)

SYSTEM_PROMPT = f"""\
You are a robot manipulation eval judge. You will be shown a tight sequence of \
high-resolution frames from a SINGLE failed robot rollout (a Franka Panda arm \
attempting to pick up a cube). The frames span the moment the failure became \
visible.

Pick exactly ONE label from this closed set, no exceptions:
  {", ".join(ALLOWED_LABELS)}

Then pick the SINGLE most diagnostic frame in the sequence and a pixel \
coordinate on the visual evidence — the object, the offending finger, the \
misalignment axis, etc. The coordinate is in the resolution of the frame as \
shown to you (long edge {FINE_LONG_EDGE_PX} px).

Respond with ONE valid JSON object and NOTHING else. Schema:
  {{"taxonomy_label": <one of the labels above>,
    "point": [x, y],
    "description": <one short sentence>}}

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
                    "media_type": "image/png",
                    "data": encode_png_b64(frame),
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
) -> Pass2Annotation:
    """Run the Pass-2 fine vision judge on a recorded rollout mp4.

    `coarse_range` is the (start, end) tuple Pass 1 returned, in coarse-sample
    indices. `coarse_total` is the number of frames Pass 1 sampled (so we can
    map back to original-mp4 frame indices for windowing).
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

    raw = "".join(block.text for block in response.content if block.type == "text")
    return _parse_annotation(raw)
