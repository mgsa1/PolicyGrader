"""Custom tools the orchestrator exposes to the Managed Agents session.

Two core tools plus Plan-B submit_* hand-offs, all server-side: the Managed
Agents runtime emits `agent.custom_tool_use` events for these names, the
orchestrator dispatches them locally, and posts back `user.custom_tool_result`
events.

  - rollout : runs one scenario via src.sim.adapter.run_rollout
  - judge   : runs the single-call CoT vision judge on a recorded mp4

Plan-B hand-off tools (submit_plan / submit_results / submit_findings /
submit_report) let specialized sub-agents write their final artifacts back to
the host's mirror_root — each sub-agent's /memories/ is isolated, so the
host is the only shared surface.

The input_schema field on each tool description matches the kwargs the
dispatcher reads — keep them in sync. Schemas are JSONSchema-compatible
because that's what the Anthropic SDK expects in BetaManagedAgentsCustomToolParams.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from anthropic import Anthropic

from src.costing import CostTracker
from src.memory_layout import AGENT_MEMORY_ROOT, ROLLOUTS_DIR
from src.schemas import RolloutConfig
from src.sim.adapter import run_rollout
from src.sim.scripted import InjectedFailures
from src.vision.judge import judge

ROLLOUT_TOOL_NAME = "rollout"
JUDGE_TOOL_NAME = "judge"

# Per-role submit_* tools. Each session's /memories/ is isolated, so sub-agents
# hand their final artifacts back to the host via these tools which write into
# mirror_root. See CLAUDE.md §3 "Inter-session artifact hand-off".
SUBMIT_PLAN_TOOL_NAME = "submit_plan"
SUBMIT_RESULTS_TOOL_NAME = "submit_results"
SUBMIT_FINDINGS_TOOL_NAME = "submit_findings"
SUBMIT_REPORT_TOOL_NAME = "submit_report"

# MuJoCo rollout dispatch is serialized process-wide because GLFW's OpenGL
# context is global state — two concurrent run_rollout() calls in the same
# process corrupt each other's env. The rollout phase runs in ONE session on
# the main thread (see src/orchestrator.py docstring: macOS GLFW/Cocoa init
# hangs off the main thread), so in normal operation there is no contention.
# The lock stays as defense-in-depth for tests / future callers. Judge calls
# are pure Messages-API calls and parallelize freely — no lock needed there.
_ROLLOUT_LOCK = threading.Lock()

# dispatch_log.jsonl is appended to from every tool dispatch. Judge-phase
# dispatches are concurrent across worker threads, so interleaved writes would
# corrupt the JSONL format. Single process-wide lock around the append.
_DISPATCH_LOG_LOCK = threading.Lock()

# Default pretrained checkpoints, keyed by env_name. Lets the agent request a
# pretrained rollout by env_name alone — the host substitutes the path so the
# agent never has to know the local filesystem layout. The agent CAN still
# pass `checkpoint_path` explicitly to override.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_CHECKPOINTS: dict[str, Path] = {
    "Lift": _REPO_ROOT / "artifacts" / "checkpoints" / "lift_ph_low_dim.pth",
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
            "enum": ["Lift"],
        },
        "seed": {"type": "integer"},
        "max_steps": {"type": "integer", "minimum": 1, "default": 200},
        "injected_action_noise": {
            "type": "number",
            "default": 0.0,
            "description": (
                "scripted only — std of per-step action noise. Non-zero values "
                "destabilize the approach (graze / knock the cube) and tend to "
                "produce missed_approach. Ground truth is assigned by the "
                "human labeler, not by the knob value."
            ),
        },
        "injected_premature_close": {
            "type": "boolean",
            "default": False,
            "description": (
                "scripted only — gripper is commanded closed from step 0, so "
                "it never opens to grasp. Intended visual: missed_approach "
                "(hand skims the cube with closed fingers; no grip forms)."
            ),
        },
        "injected_angle_deg": {
            "type": "number",
            "default": 0.0,
            "description": (
                "scripted only — radial xy offset on approach. 15°–35° produces "
                "missed_approach (gripper closes beside the cube)."
            ),
        },
        "injected_grip_scale": {
            "type": "number",
            "default": 1.0,
            "description": (
                "scripted only — < 0.7 opens the gripper mid-lift after a few "
                "carry steps. Intended visual: failed_grip."
            ),
        },
        "cube_xy_jitter_m": {
            "type": "number",
            "default": 0.0,
            "minimum": 0.0,
            "description": (
                "Environmental perturbation for deployment (pretrained) rollouts: "
                "widens the cube's initial xy placement range to this half-extent in "
                "metres. 0.0 = robosuite default (~±3 cm, the policy's training "
                "distribution). Elevated values (e.g. 0.08) push the cube to positions "
                "the BC-RNN never saw — that's the deployment stress lever. "
                "Calibration (scripted-policy) rollouts MUST leave this at 0.0 so the "
                "scripted picker's behavior stays invariant across the injected-failure knobs."
            ),
        },
        "checkpoint_path": {
            "type": "string",
            "description": (
                "pretrained only — optional path to a robomimic .pth checkpoint. "
                "If omitted, the host substitutes a default per env_name "
                "(Lift -> a BC-RNN proficient-human checkpoint that ships with "
                "the repo). Pass explicitly only to override."
            ),
        },
    },
    "required": ["rollout_id", "policy_kind", "env_name", "seed", "max_steps"],
}

_JUDGE_INPUT_SCHEMA: dict[str, Any] = {
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


_ROLLOUT_PARAM: dict[str, Any] = {
    "type": "custom",
    "name": ROLLOUT_TOOL_NAME,
    "description": (
        "Run one robot manipulation rollout in simulation and return its outcome. "
        "Writes an mp4 of the rollout to /memories/rollouts/<rollout_id>.mp4."
    ),
    "input_schema": _ROLLOUT_INPUT_SCHEMA,
}

_JUDGE_PARAM: dict[str, Any] = {
    "type": "custom",
    "name": JUDGE_TOOL_NAME,
    "description": (
        "Single-call vision judge on a recorded rollout mp4. Only call on "
        "rollouts where the `rollout` tool returned success=false — "
        "successful rollouts have no failure to classify, so skip them. "
        "Returns a closed-set taxonomy_label (one of missed_approach, "
        "failed_grip, other), the ORIGINAL-mp4 frame_index the judge named "
        "as decisive, a pointing coordinate (or null when no gripper-cube "
        "contact is visible), and a one-sentence description."
    ),
    "input_schema": _JUDGE_INPUT_SCHEMA,
}

# Submit tools. Each takes the final artifact content verbatim so the host can
# persist it under mirror_root. The agent's /memories/ is isolated per-session
# and unreachable from sibling sessions — the host IS the common surface, and
# these tools are how artifacts get there.

_SUBMIT_PLAN_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "plan_md": {
            "type": "string",
            "description": (
                "Full markdown text of plan.md. Will be written verbatim to mirror_root."
            ),
        },
        "test_matrix_csv": {
            "type": "string",
            "description": (
                "Full CSV text for test_matrix.csv, header row included. "
                "Columns per PLANNER phase spec. Will be written verbatim."
            ),
        },
        "taxonomy_md": {
            "type": "string",
            "description": "Full markdown text of the taxonomy (copy from /memories/taxonomy.md).",
        },
    },
    "required": ["plan_md", "test_matrix_csv", "taxonomy_md"],
}

_SUBMIT_RESULTS_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "results_jsonl": {
            "type": "string",
            "description": (
                "One JSON object per line, each a RolloutResult record "
                "(rollout_id, success, steps_taken, video_path). "
                "Host APPENDS to mirror_root/rollouts/results.jsonl."
            ),
        },
    },
    "required": ["results_jsonl"],
}

_SUBMIT_FINDINGS_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "findings_jsonl": {
            "type": "string",
            "description": (
                "One JSON object per line, each a Finding record "
                "({rollout_id, sim_success: bool, annotation: {...}|null}). "
                "`annotation` is null when sim_success=true; otherwise it "
                "carries the judge output {taxonomy_label, frame_index, "
                "point: [x,y]|null, description}. "
                "Host APPENDS these to mirror_root/findings.jsonl — safe for "
                "parallel judge workers to submit their own slices."
            ),
        },
    },
    "required": ["findings_jsonl"],
}

_SUBMIT_REPORT_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "report_md": {
            "type": "string",
            "description": (
                "Full markdown text of report.md. Will be written verbatim to "
                "mirror_root/report.md (overwrites any prior version)."
            ),
        },
    },
    "required": ["report_md"],
}

_SUBMIT_PLAN_PARAM: dict[str, Any] = {
    "type": "custom",
    "name": SUBMIT_PLAN_TOOL_NAME,
    "description": (
        "PLANNER hand-off: submit the plan, test matrix, and taxonomy to "
        "the host in one call. Call this EXACTLY ONCE at the end of the planner "
        "phase, then stop. The host writes the files to mirror_root and the "
        "downstream workers read them from there."
    ),
    "input_schema": _SUBMIT_PLAN_INPUT_SCHEMA,
}

_SUBMIT_RESULTS_PARAM: dict[str, Any] = {
    "type": "custom",
    "name": SUBMIT_RESULTS_TOOL_NAME,
    "description": (
        "ROLLOUT WORKER hand-off: submit the JSONL of RolloutResult records "
        "for this worker's slice. Call this ONCE after all assigned rollouts are "
        "complete, then stop."
    ),
    "input_schema": _SUBMIT_RESULTS_INPUT_SCHEMA,
}

_SUBMIT_FINDINGS_PARAM: dict[str, Any] = {
    "type": "custom",
    "name": SUBMIT_FINDINGS_TOOL_NAME,
    "description": (
        "JUDGE WORKER hand-off: submit the JSONL of Finding records for "
        "this worker's slice. Call this ONCE after judging is done, then stop."
    ),
    "input_schema": _SUBMIT_FINDINGS_INPUT_SCHEMA,
}

_SUBMIT_REPORT_PARAM: dict[str, Any] = {
    "type": "custom",
    "name": SUBMIT_REPORT_TOOL_NAME,
    "description": (
        "REPORTER hand-off: submit the final report markdown. Call this ONCE and stop."
    ),
    "input_schema": _SUBMIT_REPORT_INPUT_SCHEMA,
}


def tool_params_for_role(role: str) -> list[dict[str, Any]]:
    """Narrow per-role tool surface.

    Each specialized agent gets ONLY the tools it needs plus its submit tool.
    A tighter tool surface makes the model's choices more obvious and reduces
    the odds of a rollout worker accidentally calling a vision tool (or vice
    versa). Built-in agent_toolset tools (read/write/edit/bash/glob/grep) are
    added separately in the orchestrator — they're useful for scratch work
    in /memories/ regardless of role.
    """
    if role == "planner":
        return [_SUBMIT_PLAN_PARAM]
    if role == "rollout_worker":
        return [_ROLLOUT_PARAM, _SUBMIT_RESULTS_PARAM]
    if role == "judge_worker":
        return [_JUDGE_PARAM, _SUBMIT_FINDINGS_PARAM]
    if role == "reporter":
        return [_SUBMIT_REPORT_PARAM]
    raise ValueError(
        f"unknown role {role!r}; expected one of "
        "'planner' | 'rollout_worker' | 'judge_worker' | 'reporter'"
    )


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

    cube_jitter = float(args.get("cube_xy_jitter_m", 0.0))

    if policy_kind == "scripted":
        if cube_jitter != 0.0:
            raise ValueError(
                "cube_xy_jitter_m must be 0.0 for scripted rollouts — the calibration "
                "cohort's scripted policy assumes the default Lift placement range."
            )
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
            cube_xy_jitter_m=cube_jitter,
        )

    video_out = mirror_root / ROLLOUTS_DIR / f"{rollout_id}.mp4"
    # GLFW's OpenGL context is process-global. Rollouts run sequentially from
    # one session on the host main thread, so normal operation doesn't
    # contend — but if this is ever called from concurrent threads their sim
    # steps would interleave and corrupt each other's render state. The lock
    # is defense-in-depth; sim time is ~2 s per Lift rollout.
    with _ROLLOUT_LOCK:
        result = run_rollout(config, video_out=video_out)

    # Report the agent-visible path so it can refer back to it from later tools.
    agent_visible = AGENT_MEMORY_ROOT / ROLLOUTS_DIR / f"{rollout_id}.mp4"
    return {
        "rollout_id": result.rollout_id,
        "success": result.success,
        "steps_taken": result.steps_taken,
        "video_path": str(agent_visible),
    }


def _dispatch_judge(
    args: dict[str, Any],
    mirror_root: Path,
    client: Anthropic,
    cost_tracker: CostTracker | None,
) -> dict[str, Any]:
    video_path = _resolve_video_path(args["video_path"], mirror_root)
    # Sibling sidecar written by adapter.run_rollout. Optional: judge falls
    # back to vision-only when missing (e.g. replay of a pre-telemetry run).
    telemetry_path = video_path.with_suffix(".telemetry.json")
    annotation = judge(
        video_path,
        client=client,
        cost_tracker=cost_tracker,
        telemetry_path=telemetry_path if telemetry_path.exists() else None,
    )
    return {
        "rollout_id": args["rollout_id"],
        "taxonomy_label": annotation.taxonomy_label.value,
        "frame_index": annotation.frame_index,
        "point": list(annotation.point) if annotation.point is not None else None,
        "description": annotation.description,
    }


DISPATCH_LOG = "dispatch_log.jsonl"
RESULTS_JSONL = "rollouts/results.jsonl"
FINDINGS_JSONL = "findings.jsonl"


def _append_dispatch_log(
    mirror_root: Path, tool_name: str, args: dict[str, Any], result: dict[str, Any]
) -> None:
    """Append one (tool, args, result) record to mirror_root/dispatch_log.jsonl.

    The Gradio UI / synthesis layer reads this to reconstruct rollout configs
    and judge findings without needing access to /memories/ inside the agent's
    environment. We see every tool call here anyway — logging it costs ~1 ms.

    Lock-protected so concurrent judge-worker threads don't interleave
    partial JSON writes into the same file.
    """
    import time as _time

    record = {"ts": _time.time(), "tool": tool_name, "args": args, "result": result}
    path = mirror_root / DISPATCH_LOG
    path.parent.mkdir(parents=True, exist_ok=True)
    with _DISPATCH_LOG_LOCK, path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def _append_jsonl(path: Path, jsonl_text: str) -> int:
    """Append already-formatted JSONL text to `path`. Returns line count accepted.

    Tolerates trailing whitespace, blank lines, and missing trailing newline.
    Each non-empty line is re-validated as JSON before it lands on disk —
    we'd rather reject a bad line than corrupt the file.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    accepted = 0
    with _DISPATCH_LOG_LOCK, path.open("a", encoding="utf-8") as f:
        for line in jsonl_text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSONL line (not JSON): {line[:120]}... ({exc})") from exc
            f.write(line + "\n")
            accepted += 1
    return accepted


def _dispatch_submit_plan(args: dict[str, Any], mirror_root: Path) -> dict[str, Any]:
    mirror_root.mkdir(parents=True, exist_ok=True)
    (mirror_root / "plan.md").write_text(args["plan_md"], encoding="utf-8")
    (mirror_root / "test_matrix.csv").write_text(args["test_matrix_csv"], encoding="utf-8")
    (mirror_root / "taxonomy.md").write_text(args["taxonomy_md"], encoding="utf-8")
    return {
        "ok": True,
        "wrote": ["plan.md", "test_matrix.csv", "taxonomy.md"],
        "plan_bytes": len(args["plan_md"]),
        "matrix_bytes": len(args["test_matrix_csv"]),
    }


def _dispatch_submit_results(args: dict[str, Any], mirror_root: Path) -> dict[str, Any]:
    path = mirror_root / RESULTS_JSONL
    n = _append_jsonl(path, args["results_jsonl"])
    return {"ok": True, "appended": n, "path": str(path.relative_to(mirror_root))}


def _dispatch_submit_findings(args: dict[str, Any], mirror_root: Path) -> dict[str, Any]:
    path = mirror_root / FINDINGS_JSONL
    n = _append_jsonl(path, args["findings_jsonl"])
    return {"ok": True, "appended": n, "path": str(path.relative_to(mirror_root))}


def _dispatch_submit_report(args: dict[str, Any], mirror_root: Path) -> dict[str, Any]:
    mirror_root.mkdir(parents=True, exist_ok=True)
    (mirror_root / "report.md").write_text(args["report_md"], encoding="utf-8")
    return {"ok": True, "wrote": ["report.md"], "bytes": len(args["report_md"])}


def dispatch(
    tool_name: str,
    tool_input: dict[str, Any],
    *,
    mirror_root: Path,
    client: Anthropic,
    cost_tracker: CostTracker | None = None,
) -> str:
    """Execute one custom-tool call and return its JSON-serialized result.

    Returning a string lets the caller stuff it directly into a
    `user.custom_tool_result` event content block. `cost_tracker`, if provided,
    is forwarded to the judge so its token usage is summed into the
    session-wide ledger. Every call is also appended to dispatch_log.jsonl so
    the synthesis UI can reconstruct rollout configs and judge findings.
    """
    if tool_name == ROLLOUT_TOOL_NAME:
        result = _dispatch_rollout(tool_input, mirror_root)
    elif tool_name == JUDGE_TOOL_NAME:
        result = _dispatch_judge(tool_input, mirror_root, client, cost_tracker)
    elif tool_name == SUBMIT_PLAN_TOOL_NAME:
        result = _dispatch_submit_plan(tool_input, mirror_root)
    elif tool_name == SUBMIT_RESULTS_TOOL_NAME:
        result = _dispatch_submit_results(tool_input, mirror_root)
    elif tool_name == SUBMIT_FINDINGS_TOOL_NAME:
        result = _dispatch_submit_findings(tool_input, mirror_root)
    elif tool_name == SUBMIT_REPORT_TOOL_NAME:
        result = _dispatch_submit_report(tool_input, mirror_root)
    else:
        raise ValueError(f"unknown custom tool: {tool_name}")
    _append_dispatch_log(mirror_root, tool_name, dict(tool_input), result)
    return json.dumps(result)
