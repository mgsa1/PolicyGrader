"""Pass-1 vision judge: cheap binary verdict + failure frame range.

CLAUDE.md sec 7 (Saturday PM): "sample 12-16 evenly-spaced frames at ~768px,
ask for {verdict: pass|fail, failure_frame_range: [start, end]|null}."

This is a pure function called as an orchestrator tool, NOT a Managed Agents
tool. It uses the Messages API directly so we control the model + image budget
per call. Token cost dominates here, hence the small-frame coarse stage that
filters before Pass 2 spends 2576px tokens.

Frame-range coordinates are returned in COARSE-PASS frame indices (i.e. into
the 12-16-frame sample, not into the original mp4). Pass 2 widens that range
back to the original mp4 timeline before sampling — see fine_pass.py.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from anthropic import Anthropic

from src.constants import OPUS_MODEL_ID
from src.schemas import Pass1Verdict
from src.vision.frames import encode_png_b64, read_frames, resize_long_edge, sample_indices

COARSE_NUM_FRAMES = 14  # midpoint of CLAUDE.md's 12-16 range
COARSE_LONG_EDGE_PX = 768
COARSE_MAX_TOKENS = 1024

# Strict JSON-only response so json.loads() works without scrubbing prose.
SYSTEM_PROMPT = """\
You are a robot manipulation eval judge. You will be shown a sequence of \
evenly-spaced frames from a SINGLE robot rollout (a Franka Panda arm \
attempting to pick up a cube on a table). The frames are ordered chronologically \
and indexed 0 through N-1 in the order shown.

Decide whether the rollout succeeded. Success means the cube was lifted clear \
of the table and held there at the end. Anything else — gripper missed, \
gripper closed on air, object slid out, object knocked off the table, \
collision, no-op — is a failure.

If the rollout failed, also report the index range of the frames in which the \
failure became visible (inclusive). Use the smallest tight range you can.

Respond with ONE valid JSON object and NOTHING else. Schema:
  {"verdict": "pass" | "fail", "failure_frame_range": [start, end] | null}

`failure_frame_range` MUST be null when verdict is "pass". When verdict is \
"fail", `start` and `end` are integers in [0, N-1] with start <= end.
"""


def _build_image_blocks(video_path: Path) -> tuple[list[dict[str, object]], int]:
    """Sample frames, resize, base64-encode. Returns (blocks, num_sampled)."""
    frames = read_frames(video_path)
    indices = sample_indices(len(frames), COARSE_NUM_FRAMES)
    blocks: list[dict[str, object]] = []
    for sampled_index, original_index in enumerate(indices):
        frame = resize_long_edge(frames[original_index], COARSE_LONG_EDGE_PX)
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
    return blocks, len(indices)


def _parse_verdict(raw: str, num_sampled: int) -> Pass1Verdict:
    """Extract Pass1Verdict from the model's JSON. Tolerates ```json fences."""
    text = raw.strip()
    if text.startswith("```"):
        # Strip leading ```json or ``` and trailing ```
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
        if text.endswith("```"):
            text = text[:-3].strip()

    payload = json.loads(text)
    verdict = payload["verdict"]
    range_field = payload.get("failure_frame_range")

    failure_range: tuple[int, int] | None
    if range_field is None:
        failure_range = None
    else:
        start, end = int(range_field[0]), int(range_field[1])
        # Clamp to the sample we sent. The judge sometimes hallucinates +1
        # off-the-end; that's a small enough error to fix here rather than
        # bouncing the whole verdict.
        start = max(0, min(start, num_sampled - 1))
        end = max(start, min(end, num_sampled - 1))
        failure_range = (start, end)

    return Pass1Verdict(verdict=verdict, failure_frame_range=failure_range)


def coarse_pass(video_path: Path, *, client: Anthropic | None = None) -> Pass1Verdict:
    """Run the Pass-1 coarse vision judge on a recorded rollout mp4."""
    if client is None:
        client = Anthropic()

    image_blocks, num_sampled = _build_image_blocks(video_path)

    response = client.messages.create(
        model=OPUS_MODEL_ID,
        max_tokens=COARSE_MAX_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": cast(Any, image_blocks)}],
    )

    # Concatenate text blocks; Opus 4.7 may interleave thinking summaries which
    # we ignore here (we only asked for a JSON answer).
    raw = "".join(block.text for block in response.content if block.type == "text")
    return _parse_verdict(raw, num_sampled)
