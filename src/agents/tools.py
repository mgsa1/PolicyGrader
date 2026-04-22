"""Custom tools the orchestrator exposes to the Managed Agents session.

Three tools, all server-side: the Managed Agents runtime emits
`agent.custom_tool_use` events for these names, the orchestrator dispatches
them locally, and posts back `user.custom_tool_result` events.

  - rollout : runs one scenario via src.sim.adapter.run_rollout
  - coarse  : runs Pass-1 vision judge on a recorded mp4
  - fine    : runs Pass-2 vision judge on a windowed slice

The input_schema field on each tool description matches the kwargs the
dispatcher reads — keep them in sync. Schemas are JSONSchema-compatible
because that's what the Anthropic SDK expects in BetaManagedAgentsCustomToolParams.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from anthropic import Anthropic

from src.memory_layout import AGENT_MEMORY_ROOT, ROLLOUTS_DIR
from src.schemas import RolloutConfig
from src.sim.adapter import run_rollout
from src.sim.scripted import InjectedFailures
from src.vision.coarse_pass import COARSE_NUM_FRAMES, coarse_pass
from src.vision.fine_pass import fine_pass

ROLLOUT_TOOL_NAME = "rollout"
COARSE_TOOL_NAME = "coarse"
FINE_TOOL_NAME = "fine"

# Default pretrained checkpoints, keyed by env_name. Lets the agent request a
# pretrained rollout by env_name alone — the host substitutes the path so the
# agent never has to know the local filesystem layout. The agent CAN still
# pass `checkpoint_path` explicitly to override.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_CHECKPOINTS: dict[str, Path] = {
    "NutAssemblySquare": _REPO_ROOT / "artifacts" / "checkpoints" / "square_ph_low_dim.pth",
}


def _resolve_checkpoint(env_name: str, explicit: str | None) -> Path:
    """Return the host path of the checkpoint to load for a pretrained rollout."""
    if explicit:
        return Path(explicit)
    if env_name in _DEFAULT_CHECKPOINTS:
        return _DEFAULT_CHECKPOINTS[env_name]
    raise ValueError(
        f"no default pretrained checkpoint registered for env_name={env_name!r}; "
        f"either register one in _DEFAULT_CHECKPOINTS or pass checkpoint_path explicitly"
    )


# JSONSchema definitions used as `input_schema` on each custom tool. We hand
# the agent flat scalar kwargs because nested objects make the model's tool
# calls noisier — flat is easier to validate and easier for the model to fill in.

_ROLLOUT_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "rollout_id": {
            "type": "string",
            "description": "Stable ID for this scenario; matches the matrix row.",
        },
        "policy_kind": {
            "type": "string",
            "enum": ["pretrained", "scripted"],
        },
        "env_name": {
            "type": "string",
            "enum": ["Lift", "NutAssemblySquare"],
        },
        "seed": {"type": "integer"},
        "max_steps": {"type": "integer", "minimum": 1, "default": 200},
        "injected_action_noise": {
            "type": "number",
            "default": 0.0,
            "description": "scripted only — std of per-step action noise; "
            "values >= 0.10 label as knock_object_off_table.",
        },
        "injected_premature_close": {
            "type": "boolean",
            "default": False,
            "description": (
                "scripted only — closes the gripper during approach; labels approach_miss."
            ),
        },
        "injected_angle_deg": {
            "type": "number",
            "default": 0.0,
            "description": "scripted only — radial xy offset on approach; labels approach_miss.",
        },
        "injected_grip_scale": {
            "type": "number",
            "default": 1.0,
            "description": "scripted only — < 0.7 opens gripper at lift; labels slip_during_lift.",
        },
        "checkpoint_path": {
            "type": "string",
            "description": (
                "pretrained only — optional path to a robomimic .pth checkpoint. "
                "If omitted, the host substitutes a default per env_name "
                "(NutAssemblySquare -> a BC-RNN proficient-human checkpoint that "
                "ships with the repo). Pass explicitly only to override."
            ),
        },
    },
    "required": ["rollout_id", "policy_kind", "env_name", "seed", "max_steps"],
}

_COARSE_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "rollout_id": {"type": "string"},
        "video_path": {
            "type": "string",
            "description": (
                "Absolute path to the rollout mp4 (typically /memories/rollouts/<id>.mp4)."
            ),
        },
    },
    "required": ["rollout_id", "video_path"],
}

_FINE_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "rollout_id": {"type": "string"},
        "video_path": {"type": "string"},
        "failure_frame_range": {
            "type": "array",
            "items": {"type": "integer"},
            "minItems": 2,
            "maxItems": 2,
            "description": "[start, end] inclusive, in COARSE-PASS frame indices "
            "(0..coarse_total_frames-1). Pass null if Pass 1 returned no range.",
        },
        "coarse_total_frames": {
            "type": "integer",
            "description": "Number of frames Pass 1 sampled; needed to map the "
            "coarse range back to original mp4 indices.",
        },
    },
    "required": ["rollout_id", "video_path", "coarse_total_frames"],
}


def tool_params() -> list[dict[str, Any]]:
    """Return the three custom-tool dicts to pass to client.beta.agents.create(tools=...)."""
    return [
        {
            "type": "custom",
            "name": ROLLOUT_TOOL_NAME,
            "description": (
                "Run one robot manipulation rollout in simulation and return its outcome. "
                "Writes an mp4 of the rollout to /memories/rollouts/<rollout_id>.mp4."
            ),
            "input_schema": _ROLLOUT_INPUT_SCHEMA,
        },
        {
            "type": "custom",
            "name": COARSE_TOOL_NAME,
            "description": (
                "Pass-1 coarse vision judge on a recorded rollout mp4. Returns a "
                "binary verdict and (on fail) a frame-range estimate in coarse-pass "
                "indices."
            ),
            "input_schema": _COARSE_INPUT_SCHEMA,
        },
        {
            "type": "custom",
            "name": FINE_TOOL_NAME,
            "description": (
                "Pass-2 fine vision judge on a windowed slice of a rollout mp4. "
                "Returns a closed-set taxonomy label, a 2576px pointing coordinate, "
                "and a one-line description. Only call this on rollouts where coarse "
                "returned verdict='fail'."
            ),
            "input_schema": _FINE_INPUT_SCHEMA,
        },
    ]


def _resolve_video_path(raw: str, mirror_root: Path) -> Path:
    """Translate the agent-visible /memories/rollouts/<id>.mp4 to a host path.

    The agent thinks in terms of /memories/. On the host we mirror to
    `mirror_root` (the orchestrator's session artifact dir). This lets the
    same orchestrator run with or without an actual managed environment —
    in smoke mode we point mirror_root at a local folder.
    """
    p = Path(raw)
    try:
        rel = p.relative_to(AGENT_MEMORY_ROOT)
    except ValueError:
        return p
    return mirror_root / rel


def _dispatch_rollout(args: dict[str, Any], mirror_root: Path) -> dict[str, Any]:
    policy_kind = args["policy_kind"]
    rollout_id = args["rollout_id"]

    if policy_kind == "scripted":
        failures = InjectedFailures(
            action_noise=float(args.get("injected_action_noise", 0.0)),
            gripper_close_prematurely=bool(args.get("injected_premature_close", False)),
            approach_angle_offset_deg=float(args.get("injected_angle_deg", 0.0)),
            grip_force_scale=float(args.get("injected_grip_scale", 1.0)),
        )
        config = RolloutConfig(
            rollout_id=rollout_id,
            policy_kind="scripted",
            env_name=args["env_name"],
            seed=int(args["seed"]),
            max_steps=int(args["max_steps"]),
            injected_failures=failures,
        )
    else:
        ckpt = _resolve_checkpoint(args["env_name"], args.get("checkpoint_path"))
        config = RolloutConfig(
            rollout_id=rollout_id,
            policy_kind="pretrained",
            env_name=args["env_name"],
            seed=int(args["seed"]),
            max_steps=int(args["max_steps"]),
            checkpoint_path=ckpt,
        )

    video_out = mirror_root / ROLLOUTS_DIR / f"{rollout_id}.mp4"
    result = run_rollout(config, video_out=video_out)

    # Report the agent-visible path so it can refer back to it from later tools.
    agent_visible = AGENT_MEMORY_ROOT / ROLLOUTS_DIR / f"{rollout_id}.mp4"
    return {
        "rollout_id": result.rollout_id,
        "success": result.success,
        "steps_taken": result.steps_taken,
        "video_path": str(agent_visible),
        "ground_truth_label": (
            result.ground_truth_label.value if result.ground_truth_label is not None else None
        ),
    }


def _dispatch_coarse(args: dict[str, Any], mirror_root: Path, client: Anthropic) -> dict[str, Any]:
    video_path = _resolve_video_path(args["video_path"], mirror_root)
    verdict = coarse_pass(video_path, client=client)
    return {
        "rollout_id": args["rollout_id"],
        "verdict": verdict.verdict,
        "failure_frame_range": list(verdict.failure_frame_range)
        if verdict.failure_frame_range is not None
        else None,
        "coarse_total_frames": COARSE_NUM_FRAMES,
    }


def _dispatch_fine(args: dict[str, Any], mirror_root: Path, client: Anthropic) -> dict[str, Any]:
    video_path = _resolve_video_path(args["video_path"], mirror_root)
    raw_range = args.get("failure_frame_range")
    coarse_range: tuple[int, int] | None = (
        None if raw_range is None else (int(raw_range[0]), int(raw_range[1]))
    )
    annotation = fine_pass(
        video_path,
        coarse_range,
        coarse_total=int(args["coarse_total_frames"]),
        client=client,
    )
    return {
        "rollout_id": args["rollout_id"],
        "taxonomy_label": annotation.taxonomy_label.value,
        "point": list(annotation.point),
        "description": annotation.description,
    }


def dispatch(
    tool_name: str,
    tool_input: dict[str, Any],
    *,
    mirror_root: Path,
    client: Anthropic,
) -> str:
    """Execute one custom-tool call and return its JSON-serialized result.

    Returning a string lets the caller stuff it directly into a
    `user.custom_tool_result` event content block.
    """
    if tool_name == ROLLOUT_TOOL_NAME:
        result = _dispatch_rollout(tool_input, mirror_root)
    elif tool_name == COARSE_TOOL_NAME:
        result = _dispatch_coarse(tool_input, mirror_root, client)
    elif tool_name == FINE_TOOL_NAME:
        result = _dispatch_fine(tool_input, mirror_root, client)
    else:
        raise ValueError(f"unknown custom tool: {tool_name}")
    return json.dumps(result)
