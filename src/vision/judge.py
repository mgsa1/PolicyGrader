"""Single-call vision judge over a recorded rollout mp4.

Two named failure labels (`missed_approach` / `failed_grip`) plus `other`,
no rigid per-frame CoT, no anti-default heuristics. The judge gets the
failure-mode question + the frames + (optional) sim telemetry rows, and
returns one label, the earliest decisive frame, an optional pixel point,
and a short description. That's it.

The prior version forced a per-frame gripper/cube/contact table over ≤36
frames and then chained deterministic label rules off those observations —
which turned every hallucinated observation into a wrong label. Opus 4.7 on
1920 px frames with telemetry as a supporting table is strong enough without
the scaffolding.

The returned `frame_index` is in the ORIGINAL mp4's frame indexing — the
module converts from its sampled-frame indexing internally. `point` is (x, y)
in the shown-frame's grid, or None when there is no gripper-cube contact to
point at.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, cast

from anthropic import Anthropic

from src.constants import OPUS_MODEL_ID
from src.schemas import JudgeAnnotation, RolloutTelemetry
from src.sim.scripted import FailureMode
from src.vision.frames import encode_jpeg_b64, read_frames, resize_long_edge, sample_indices

# Sampling shape: ~3 frames per second of video, clamped. The upper cap keeps
# the JPEG payload under the 32 MB Messages-API request limit; the lower floor
# keeps short clips (e.g. a rollout that terminated after 40 steps) from being
# under-sampled.
#
# IMPORTANT: Anthropic enforces a 2000 px max-dimension cap on **many-image**
# requests (distinct from the 2576 px cap they advertise for single-image
# calls). Sending frames at 2576 px in a multi-image request returns 400:
# "image dimensions exceed max allowed size for many-image requests".
JUDGE_LONG_EDGE_PX = 1920
JUDGE_FRAMES_PER_SECOND = 3
JUDGE_MIN_FRAMES = 12
JUDGE_MAX_FRAMES = 36
JUDGE_MAX_TOKENS = 1024
DEFAULT_RENDER_FPS = 20  # robosuite's default; overridable via judge(fps=...)

ALLOWED_LABELS = sorted(label.value for label in FailureMode if label != FailureMode.NONE)


def _load_taxonomy() -> str:
    """Embed docs/taxonomy.md verbatim — single source of truth for the label set."""
    return (Path(__file__).resolve().parents[2] / "docs" / "taxonomy.md").read_text()


_TAXONOMY_MARKDOWN = _load_taxonomy()


def _build_system_prompt(n_frames: int, *, has_telemetry: bool) -> str:
    telemetry_anchor = (
        "\nA sim-telemetry table is appended after the frames — one row per "
        "shown frame, exact from the simulator (gripper aperture, "
        "end-effector→cube distance, cube height above the table, cube xy "
        "drift, contact flag). Use it as ground-truth physical evidence when "
        "the pixels are ambiguous.\n"
        if has_telemetry
        else ""
    )
    return f"""\
You are grading one failed rollout of a Franka Panda arm trying to pick up a \
cube on a table (the robosuite Lift task). You will see {n_frames} frames \
from ONE rollout in chronological order, labeled "Frame 0" through \
"Frame {n_frames - 1}".

The simulator has already confirmed this rollout FAILED. Your only job is to \
name the failure mode, point to the decisive frame, and (when applicable) \
pixel-point at the evidence.
{telemetry_anchor}
There are two named failure modes. Pick the one that matches the visual \
evidence:

  missed_approach — The arm never established a grip. Visual signature: the \
    gripper closes on empty space, OR stays closed throughout the descent \
    (pushing or scratching the cube), OR passes by the cube without contact. \
    The cube does not visibly leave the table surface during the rollout.

  failed_grip — The arm gripped the cube but lost it during the lift. Visual \
    signature: the cube briefly rises with the gripper before falling. There \
    is at least one frame where the cube is above the table surface, held \
    by closed gripper fingers.

The decisive cue is: did the cube ever leave the table surface? If yes → \
failed_grip. If no → missed_approach. Use `other` only for genuine failures \
that fit neither (very rare on Lift).

Return `frame_index` as the earliest frame that shows the decisive event \
(the missed close, the slip, the impact with closed fingers) — NOT the \
aftermath of the arm retreating empty.

Return `point` as [x, y] in the pixel grid of that frame (long edge = \
{JUDGE_LONG_EDGE_PX} px), pointing at the gripper-cube contact site. Return \
`null` when there is no gripper-cube contact visible anywhere in the \
rollout — e.g. a clean miss where the fingers close on air. A null is \
CORRECT for no-contact failures; a wrong pixel is strictly worse than a null.

Return `description` as one short sentence naming the event (not the end state).

{_TAXONOMY_MARKDOWN}

Respond with ONE valid JSON object and NOTHING else. Schema:
{{
  "taxonomy_label": "<one of: {", ".join(ALLOWED_LABELS)}>",
  "frame_index": <integer in [0, {n_frames - 1}]>,
  "point": [<x>, <y>] OR null,
  "description": "<short sentence naming the event>"
}}
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
    """Sample frames, resize, encode JPEG. Returns (blocks, original_indices)."""
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


def _load_telemetry(path: Path) -> RolloutTelemetry:
    return RolloutTelemetry.model_validate_json(path.read_text())


def _render_telemetry_block(
    telemetry: RolloutTelemetry,
    original_indices: list[int],
) -> str:
    """ASCII table of telemetry rows aligned to the sampled frames.

    Frame labels match the image labels ("Frame 0".."Frame N-1"); each row is
    the telemetry for the underlying sim step (`original_indices[i]`). Skips
    rows whose step index is out of bounds rather than failing the call —
    telemetry presence is best-effort, not load-bearing.
    """
    header = "Frame  gripper  ee→cube   cube_z    cube_xy   contact"
    lines = [
        "Sim telemetry (one row per shown frame — exact, from simulator):",
        header,
    ]
    for sampled_idx, step_idx in enumerate(original_indices):
        if step_idx >= len(telemetry.rows):
            continue
        r = telemetry.rows[step_idx]
        contact = "✓" if r.contact_flag else "-"
        lines.append(
            f"{sampled_idx:5d}  {r.gripper_aperture:6.2f}  "
            f"{r.ee_to_cube_m:5.3f}m   {r.cube_z_above_table_m:+.3f}m   "
            f"{r.cube_xy_drift_m:.3f}m   {contact}"
        )
    return "\n".join(lines)


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

    return JudgeAnnotation(
        taxonomy_label=label,
        frame_index=original_frame_index,
        point=point,
        description=description,
    )


def judge(
    video_path: Path,
    *,
    client: Anthropic | None = None,
    fps: int = DEFAULT_RENDER_FPS,
    telemetry_path: Path | None = None,
) -> JudgeAnnotation:
    """Run the single-call judge on a recorded rollout mp4.

    Only call on sim-confirmed failures.

    `telemetry_path`, if provided AND the file exists, loads the per-step sim
    telemetry sidecar and inlines the rows aligned to the sampled frames as a
    text block in the user message — supporting evidence for the judge when
    pixels are ambiguous.
    """
    if client is None:
        client = Anthropic()

    image_blocks, original_indices = _build_image_blocks(video_path, fps)
    if not original_indices:
        raise ValueError(f"video has no frames: {video_path}")

    telemetry = (
        _load_telemetry(telemetry_path)
        if telemetry_path is not None and telemetry_path.exists()
        else None
    )

    user_blocks: list[dict[str, object]] = list(image_blocks)
    if telemetry is not None:
        user_blocks.append(
            {"type": "text", "text": _render_telemetry_block(telemetry, original_indices)}
        )

    response = client.messages.create(
        model=OPUS_MODEL_ID,
        max_tokens=JUDGE_MAX_TOKENS,
        system=_build_system_prompt(
            n_frames=len(original_indices),
            has_telemetry=telemetry is not None,
        ),
        messages=[{"role": "user", "content": cast(Any, user_blocks)}],
    )

    raw = "".join(block.text for block in response.content if block.type == "text")
    return _parse_annotation(raw, original_indices)
