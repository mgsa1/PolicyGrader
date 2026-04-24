"""Single-call CoT vision judge over a recorded rollout mp4.

Replaces the former two-pass (coarse 768px → fine 2576px) design on
2026-04-24. Binary success comes from the simulator, so the judge only has to
classify the failure mode and point at it. One Messages-API call per failed
rollout at 2576 px × clamp(video_duration * 3, 12, 36) frames, JPEG q88.

The prompt forces per-frame chain-of-thought (gripper state / cube state /
contact) BEFORE the label — that's what keeps the judge from defaulting to
approach_miss on consequence-frame evidence, which was the #1 driver of
mislabels in the old two-pass pipeline.

The returned `frame_index` is in the ORIGINAL mp4's frame indexing — the
module converts from its sampled-frame indexing internally so downstream
consumers (keyframes, UI) can index the raw video directly. The returned
`point` is (x, y) in the 2576-px grid of that frame, or None when no cube
contact is visible.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, cast

from anthropic import Anthropic

from src.constants import OPUS_MODEL_ID
from src.costing import CostTracker
from src.schemas import FrameObservation, JudgeAnnotation
from src.sim.scripted import FailureMode
from src.vision.frames import encode_jpeg_b64, read_frames, resize_long_edge, sample_indices

# Sampling shape: ~3 frames per second of video, clamped. The upper cap keeps
# the JPEG payload under the 32 MB Messages-API request limit; the lower floor
# keeps short clips (e.g. a rollout that terminated after 40 steps) from being
# under-sampled for CoT reasoning.
JUDGE_LONG_EDGE_PX = 2576
JUDGE_FRAMES_PER_SECOND = 3
JUDGE_MIN_FRAMES = 12
JUDGE_MAX_FRAMES = 36
JUDGE_MAX_TOKENS = 3072  # room for per-frame observations + final answer
DEFAULT_RENDER_FPS = 20  # robosuite's default; overridable via judge(fps=...)

ALLOWED_LABELS = sorted(label.value for label in FailureMode if label != FailureMode.NONE)

_GRIPPER_STATES = ["open", "closing", "closed", "opening"]
_CUBE_STATES = [
    "still_on_table",
    "moving_on_table",
    "in_gripper",
    "falling",
    "off_table",
]
_CONTACT_STATES = ["none", "touching_cube", "grasped"]


def _load_taxonomy() -> str:
    """Embed docs/taxonomy.md verbatim — single source of truth for the label set."""
    return (Path(__file__).resolve().parents[2] / "docs" / "taxonomy.md").read_text()


_TAXONOMY_MARKDOWN = _load_taxonomy()


def _build_system_prompt(n_frames: int) -> str:
    return f"""\
You are a robot manipulation eval judge. A Franka Panda arm is trying to pick \
up a cube on a table (the Lift task). You will be shown {n_frames} \
high-resolution frames from a SINGLE rollout in chronological order, labeled \
"Frame 0" through "Frame {n_frames - 1}".

The simulator has already confirmed that this rollout FAILED. Your job is to \
classify the failure mode and point at the visible evidence — you are NOT \
deciding pass-vs-fail. Do not return `none`.

STEP 1 — per-frame walkthrough. Before choosing a label, walk through EVERY \
frame in order. For each frame, emit one observation with these fields:
  - gripper_state: one of {{{", ".join(_GRIPPER_STATES)}}}
  - cube_state: one of {{{", ".join(_CUBE_STATES)}}}
  - contact: one of {{{", ".join(_CONTACT_STATES)}}}

Be literal. "touching_cube" means the gripper's fingers are visibly in \
contact with the cube but have NOT closed on it. "grasped" means the fingers \
have closed and the cube is between them. "none" means no contact anywhere.

STEP 2 — pick the earliest decisive frame. Which frame first shows the \
failure EVENT itself (the impact, the slip, the missed close), NOT the \
consequence (arm retreating with empty gripper)? Return that index as \
`frame_index`.

STEP 3 — pick exactly ONE label from this closed set:
  {", ".join(ALLOWED_LABELS)}

Common confusions to RESIST:
  - approach_miss vs knock_object_off_table: if the cube visibly moved \
    BEFORE the gripper closed (or while the arm was still descending), it's \
    knock_object_off_table — the impact is the failure, not the later empty \
    close. Check your per-frame cube_state sequence.
  - approach_miss vs slip_during_lift: slip requires VISIBLE partial pickup \
    — at least one frame where `cube_state: in_gripper` is true. No such \
    frame means it was never a slip.
  - Default-to-approach_miss is this judge's failure mode. If your per-frame \
    observations contain any `contact: touching_cube` or `cube_state: \
    moving_on_table` before the gripper closed, the answer is NOT \
    approach_miss.
  - `insertion_misalignment` does not apply to Lift. Do not use it.

STEP 4 — point at the evidence, or abstain. Return `point` as `[x, y]` in \
the pixel coordinates of the frame you named (long edge = {JUDGE_LONG_EDGE_PX} \
px as shown), pointing at the gripper-cube contact site — OR return `null` \
when there is no gripper-cube contact visible anywhere in the rollout (e.g. \
approach_miss with fingers closing on empty air, or a gripper_collision that \
never touched the cube).

Scoring rule: `point = null` on a no-contact failure is CORRECT. A wrong \
pixel is scored STRICTLY WORSE than a null. Abstain when in doubt.

STEP 5 — one-sentence description of the EVENT (not the end state).

{_TAXONOMY_MARKDOWN}

Respond with ONE valid JSON object and NOTHING else. Schema:
{{
  "per_frame_observations": [
    {{"frame_index": 0, "gripper_state": "...", "cube_state": "...", "contact": "..."}},
    ...
    {{"frame_index": {n_frames - 1}, "gripper_state": "...", "cube_state": "...", "contact": "..."}}
  ],
  "frame_index": <integer in [0, {n_frames - 1}]>,
  "taxonomy_label": "<one of the labels above>",
  "point": [<x>, <y>] OR null,
  "description": "<short sentence naming the EVENT>"
}}

Prefer `other` ONLY for genuinely unrecognized failures — if any specific label fits, use it.
"""


def _choose_frame_count(n_frames: int, fps: int) -> int:
    """clamp(ceil(duration_seconds * 3), MIN, MAX)."""
    if n_frames <= 0:
        return 0
    duration_seconds = n_frames / max(1, fps)
    target = math.ceil(duration_seconds * JUDGE_FRAMES_PER_SECOND)
    return max(JUDGE_MIN_FRAMES, min(JUDGE_MAX_FRAMES, target))


def _build_image_blocks(
    video_path: Path,
    fps: int,
) -> tuple[list[dict[str, object]], list[int]]:
    """Sample frames, resize to 2576 px, encode JPEG. Returns (blocks, original_indices)."""
    frames = read_frames(video_path)
    n = len(frames)
    target = _choose_frame_count(n, fps)
    original_indices = sample_indices(n, target)

    blocks: list[dict[str, object]] = []
    for sampled_index, original_index in enumerate(original_indices):
        frame = resize_long_edge(frames[original_index], JUDGE_LONG_EDGE_PX)
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
    return blocks, original_indices


def _strip_json_fence(raw: str) -> str:
    """Tolerate ```json ... ``` fences around the model's JSON reply."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
        if text.endswith("```"):
            text = text[:-3].strip()
    return text


def _parse_observations(raw_list: Any) -> list[FrameObservation]:
    if not isinstance(raw_list, list):
        return []
    out: list[FrameObservation] = []
    for row in raw_list:
        if not isinstance(row, dict):
            continue
        try:
            out.append(
                FrameObservation(
                    frame_index=int(row["frame_index"]),
                    gripper_state=row["gripper_state"],
                    cube_state=row["cube_state"],
                    contact=row["contact"],
                )
            )
        except (KeyError, ValueError, TypeError):
            # Skip malformed observations rather than failing the whole call —
            # the label + frame_index + point carry the load-bearing information.
            continue
    return out


def _parse_annotation(raw: str, original_indices: list[int]) -> JudgeAnnotation:
    """Convert the model's JSON reply into a JudgeAnnotation.

    The model answers in sampled-frame indices (0..N-1 of what we sent).
    Convert to ORIGINAL mp4 indices before returning.
    """
    payload = json.loads(_strip_json_fence(raw))

    label = FailureMode(payload["taxonomy_label"])

    sampled_idx = int(payload["frame_index"])
    sampled_idx = max(0, min(sampled_idx, len(original_indices) - 1))
    original_frame_index = original_indices[sampled_idx]

    point_raw = payload.get("point")
    point: tuple[int, int] | None = (
        None if point_raw is None else (int(point_raw[0]), int(point_raw[1]))
    )

    description = str(payload["description"]).strip()
    observations = _parse_observations(payload.get("per_frame_observations"))

    return JudgeAnnotation(
        taxonomy_label=label,
        frame_index=original_frame_index,
        point=point,
        description=description,
        per_frame_observations=observations,
    )


def judge(
    video_path: Path,
    *,
    client: Anthropic | None = None,
    cost_tracker: CostTracker | None = None,
    fps: int = DEFAULT_RENDER_FPS,
) -> JudgeAnnotation:
    """Run the single-call CoT judge on a recorded rollout mp4.

    Only call on sim-confirmed failures. `cost_tracker`, if provided,
    accumulates this call's token usage into the session-wide ledger so Phase
    4 can report against the manual-review baseline.
    """
    if client is None:
        client = Anthropic()

    image_blocks, original_indices = _build_image_blocks(video_path, fps)
    if not original_indices:
        raise ValueError(f"video has no frames: {video_path}")

    response = client.messages.create(
        model=OPUS_MODEL_ID,
        max_tokens=JUDGE_MAX_TOKENS,
        system=_build_system_prompt(n_frames=len(original_indices)),
        messages=[{"role": "user", "content": cast(Any, image_blocks)}],
    )

    if cost_tracker is not None:
        cost_tracker.add_usage(response.usage)

    raw = "".join(block.text for block in response.content if block.type == "text")
    return _parse_annotation(raw, original_indices)
