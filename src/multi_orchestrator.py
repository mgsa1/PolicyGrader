"""Plan B orchestrator: FOUR specialized Managed Agents.

CLAUDE.md §3:
  Planner (1 session)
    → Rollout worker (1 session, main-thread, sequential sim)
    → Judge workers (K parallel sessions)
    → Reporter (1 session)

The shape mirrors Plan A's phases but each phase is its own agent + session
with a narrow tool surface. Only the judge phase fans out across K worker
sessions via a ThreadPoolExecutor — that's where parallelism pays off,
since judging is API-bound. Rollouts are sim-bound and were previously
serialized by _ROLLOUT_LOCK anyway, so they run sequentially in one
session driven from the host's main thread. The main-thread requirement
is load-bearing on macOS: GLFW's Cocoa init hangs when called from a
worker thread, so the rollout tool call MUST dispatch on the main thread.

Shared state:
  - CostTracker, RuntimeState — locked internally (see src/costing.py,
    src/runtime_state.py).
  - dispatch_log.jsonl appends — locked in src/agents/tools.py.

Artifact hand-off: each session's /memories/ is isolated; agents submit
final artifacts to the host via submit_* custom tools that write to
mirror_root. The reporter receives plan/matrix/results/findings inlined in
its first user message — it never sees other sessions' /memories/.
"""

from __future__ import annotations

import concurrent.futures
import csv
import io
import json
import logging
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from anthropic import Anthropic

from src.agents.multi_agent_prompts import (
    JUDGE_WORKER_SYSTEM_PROMPT,
    PLANNER_SYSTEM_PROMPT,
    REPORTER_SYSTEM_PROMPT,
    ROLLOUT_WORKER_SYSTEM_PROMPT,
)
from src.agents.system_prompts import (
    PHASE_MARKER_JUDGE,
    PHASE_MARKER_PLANNER,
    PHASE_MARKER_REPORT,
    PHASE_MARKER_ROLLOUT,
)
from src.agents.tools import dispatch as dispatch_custom_tool
from src.agents.tools import tool_params_for_role
from src.constants import MANAGED_AGENTS_BETA_HEADER, OPUS_MODEL_ID
from src.costing import (
    BASELINE_HOURLY_RATE_USD,
    BASELINE_SECONDS_PER_ROLLOUT,
    CostTracker,
    baseline_cost_for,
    baseline_seconds_for,
    format_cost,
    format_duration,
)
from src.label_phase import run_label_phase
from src.runtime_state import RuntimeState

logger = logging.getLogger(__name__)

# Phase strings for runtime.json / chat.jsonl. We reuse the Plan A marker
# strings ("BEGIN PHASE N: ...") so the UI's _MARKER_TO_CODE mapping
# (src/ui/panes/chrome.py) lights up both plans' phase chips identically —
# and so the live trace pane can segment Plan B events by phase the same
# way it does Plan A events.
PHASE_PLANNER = PHASE_MARKER_PLANNER
PHASE_ROLLOUT = PHASE_MARKER_ROLLOUT
PHASE_JUDGE = PHASE_MARKER_JUDGE
PHASE_REPORT = PHASE_MARKER_REPORT


@dataclass(frozen=True)
class AgentHandle:
    """IDs needed to drive one session."""

    role: str
    agent_id: str
    environment_id: str
    session_id: str


def _builtin_toolset() -> dict[str, Any]:
    """Built-in read/write/edit/bash/glob/grep with auto-approval.

    Agents use these for scratch work in their private /memories/. The
    submit_* custom tools are how they hand final artifacts back to the host.
    """
    enabled = ["bash", "edit", "read", "write", "glob", "grep"]
    return {
        "type": "agent_toolset_20260401",
        "configs": [
            {"name": name, "enabled": True, "permission_policy": {"type": "always_allow"}}
            for name in enabled
        ],
        "default_config": {
            "enabled": False,
            "permission_policy": {"type": "always_allow"},
        },
    }


_ROLE_CONFIG: dict[str, tuple[str, str]] = {
    # role → (agent_name_prefix, system_prompt)
    "planner": ("planner", PLANNER_SYSTEM_PROMPT),
    "rollout_worker": ("rollout-worker", ROLLOUT_WORKER_SYSTEM_PROMPT),
    "judge_worker": ("judge-worker", JUDGE_WORKER_SYSTEM_PROMPT),
    "reporter": ("reporter", REPORTER_SYSTEM_PROMPT),
}


def _create_session(
    client: Anthropic,
    role: str,
    *,
    environment_id: str,
    worker_index: int | None = None,
) -> AgentHandle:
    """Create one agent+session for a given role, reusing a shared environment.

    Environments are a container definition, not a container instance — sessions
    sharing an env_id still run in isolated containers with private /memories/.
    One env definition is plenty for all of Plan B's sessions.
    """
    if role not in _ROLE_CONFIG:
        raise ValueError(f"unknown role {role!r}")
    name_prefix, system = _ROLE_CONFIG[role]
    suffix = f"-{worker_index:02d}" if worker_index is not None else ""
    agent_name = f"{name_prefix}{suffix}"

    betas = [MANAGED_AGENTS_BETA_HEADER]
    agent = client.beta.agents.create(
        model=OPUS_MODEL_ID,
        name=agent_name,
        description=f"Plan B {role} for embodied eval.",
        system=system,
        tools=cast(Any, [_builtin_toolset(), *tool_params_for_role(role)]),
        betas=betas,
    )
    session = client.beta.sessions.create(
        agent=agent.id,
        environment_id=environment_id,
        title=f"Embodied eval {role}{suffix}",
        betas=betas,
    )
    return AgentHandle(
        role=role,
        agent_id=agent.id,
        environment_id=environment_id,
        session_id=session.id,
    )


def _create_shared_environment(client: Anthropic) -> str:
    """One env definition shared across all Plan B sessions. Returns its ID."""
    env = client.beta.environments.create(
        name="embodied-eval-env-plan-b",
        config=cast(Any, {"type": "cloud"}),
        description="Shared environment for Plan B multi-agent eval sessions.",
        betas=[MANAGED_AGENTS_BETA_HEADER],
    )
    return env.id


# ---- Session driver (one-turn loop, mirrored from Plan A) -------------------------


def _send_user_message(client: Anthropic, session_id: str, text: str) -> None:
    client.beta.sessions.events.send(
        session_id,
        events=cast(
            Any,
            [{"type": "user.message", "content": [{"type": "text", "text": text}]}],
        ),
        betas=[MANAGED_AGENTS_BETA_HEADER],
    )


def _send_tool_result(
    client: Anthropic,
    session_id: str,
    tool_use_id: str,
    payload: str,
    *,
    is_error: bool = False,
) -> None:
    client.beta.sessions.events.send(
        session_id,
        events=cast(
            Any,
            [
                {
                    "type": "user.custom_tool_result",
                    "custom_tool_use_id": tool_use_id,
                    "content": [{"type": "text", "text": payload}],
                    "is_error": is_error,
                }
            ],
        ),
        betas=[MANAGED_AGENTS_BETA_HEADER],
    )


def _stream_events(client: Anthropic, session_id: str) -> Iterator[Any]:
    with client.beta.sessions.events.stream(
        session_id, betas=[MANAGED_AGENTS_BETA_HEADER]
    ) as stream:
        yield from stream


def _drive_session_to_end_turn(
    client: Anthropic,
    session_id: str,
    *,
    label: str,
    mirror_root: Path,
    messages_client: Anthropic,
    cost_tracker: CostTracker,
    runtime: RuntimeState,
) -> str:
    """Stream events from one session until it goes idle with a terminal stop.

    Mirrored from src/orchestrator.py::_run_one_turn — same event contract,
    same requires_action re-streaming loop. `label` is a short prefix
    ("planner", "rollout-03", ...) prepended to chat.jsonl records so the
    live feed can distinguish sibling workers' messages.
    """
    while True:
        terminal: str | None = None
        saw_status_idle = False

        for event in _stream_events(client, session_id):
            ev_type = getattr(event, "type", None)

            # Managed Agents emits per-model-call usage on
            # span.model_request_end events under `model_usage`. None of the
            # agent.* or session.status_idle events carry tokens. The prior
            # code read `event.usage` which doesn't exist, so every Plan B
            # session's planner/rollout/judge/reporter spend was invisible
            # to the cost tracker.
            if ev_type == "span.model_request_end":
                model_usage = getattr(event, "model_usage", None)
                if model_usage is not None:
                    cost_tracker.add_usage(model_usage)

            if ev_type == "agent.message":
                text = "".join(
                    block.text for block in getattr(event, "content", []) if block.type == "text"
                )
                if text:
                    logger.info("[%s] %s", label, text[:500])
                    runtime.append_chat("agent_message", worker=label, text=text)

            elif ev_type == "agent.thinking":
                text = getattr(event, "text", "") or ""
                if text:
                    runtime.append_chat("agent_thinking", worker=label, text=text)

            elif ev_type == "agent.custom_tool_use":
                tool_name = event.name
                tool_input = event.input
                logger.info("[%s] tool_use %s", label, tool_name)
                runtime.append_chat("tool_use", worker=label, tool=tool_name, args=dict(tool_input))
                try:
                    payload = dispatch_custom_tool(
                        tool_name,
                        dict(tool_input),
                        mirror_root=mirror_root,
                        client=messages_client,
                        cost_tracker=cost_tracker,
                    )
                    _send_tool_result(client, session_id, event.id, payload)
                    runtime.append_chat(
                        "tool_result", worker=label, tool=tool_name, payload=payload
                    )
                except Exception as exc:  # noqa: BLE001 — must report back
                    logger.exception("[%s] tool %s failed", label, tool_name)
                    _send_tool_result(
                        client,
                        session_id,
                        event.id,
                        f'{{"error": "{type(exc).__name__}: {exc}"}}',
                        is_error=True,
                    )
                    runtime.append_chat("tool_error", worker=label, tool=tool_name, error=str(exc))

            elif ev_type == "session.status_idle":
                saw_status_idle = True
                stop_type = getattr(getattr(event, "stop_reason", None), "type", "unknown")
                if stop_type == "requires_action":
                    runtime.mark_event()
                    break
                terminal = str(stop_type)
                break

            elif ev_type == "session.error":
                logger.error("[%s] session error: %s", label, event)
                terminal = "error"
                break

            runtime.mark_event()

        if terminal is not None:
            runtime.mark_event()
            return terminal
        if not saw_status_idle:
            return "stream_closed"


# ---- Matrix splitting ------------------------------------------------------------


def _split_rows_round_robin(rows: list[dict[str, str]], k: int) -> list[list[dict[str, str]]]:
    """Round-robin split into k chunks. Balances per-chunk runtime across cohorts.

    Calibration rollouts are ~2 s each, deployment ~3-4 s. Round-robin keeps
    each worker's cohort mix similar so no single worker is stuck with all
    the slow ones.
    """
    if k < 1:
        raise ValueError(f"k must be >= 1, got {k}")
    chunks: list[list[dict[str, str]]] = [[] for _ in range(k)]
    for i, row in enumerate(rows):
        chunks[i % k].append(row)
    return [c for c in chunks if c]  # drop empty chunks if rows < k


def _load_matrix_rows(mirror_root: Path) -> list[dict[str, str]]:
    path = mirror_root / "test_matrix.csv"
    if not path.exists():
        raise FileNotFoundError(f"planner did not produce test_matrix.csv at {path}")
    with path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return [dict(r) for r in reader]


def _load_results(mirror_root: Path) -> list[dict[str, Any]]:
    """Load results.jsonl (aggregated from all rollout workers' submissions)."""
    path = mirror_root / "rollouts" / "results.jsonl"
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        out.append(json.loads(line))
    return out


# ---- Per-role drivers ------------------------------------------------------------


@dataclass(frozen=True)
class PlanBResult:
    """End-of-run summary — mirrors Plan A's SessionResult shape + fan-out detail."""

    stops: dict[str, list[str]]
    cost_tracker: CostTracker
    elapsed_seconds: float
    n_rollouts: int
    k_workers: int


def _run_planner(
    client: Anthropic,
    *,
    environment_id: str,
    user_goal: str,
    mirror_root: Path,
    messages_client: Anthropic,
    cost_tracker: CostTracker,
    runtime: RuntimeState,
) -> str:
    handle = _create_session(client, "planner", environment_id=environment_id)
    runtime.append_chat(
        "session_created", worker="planner", role="planner", session_id=handle.session_id
    )
    _send_user_message(
        client, handle.session_id, f"Evaluation goal: {user_goal}\n\nProduce the plan."
    )
    return _drive_session_to_end_turn(
        client,
        handle.session_id,
        label="planner",
        mirror_root=mirror_root,
        messages_client=messages_client,
        cost_tracker=cost_tracker,
        runtime=runtime,
    )


def _run_rollout_worker(
    client: Anthropic,
    *,
    environment_id: str,
    rows: list[dict[str, str]],
    mirror_root: Path,
    messages_client: Anthropic,
    cost_tracker: CostTracker,
    runtime: RuntimeState,
) -> str:
    """Run ONE rollout worker session, synchronously, on the caller's thread.

    The caller's thread MUST be the process main thread on macOS: the sim
    adapter's first env.reset() triggers GLFW's Cocoa init, which wedges in
    an infinite [NSApplication reportException:] loop when called from a
    worker thread. Rollouts do not benefit from fan-out anyway — MuJoCo was
    already serialized by _ROLLOUT_LOCK — so keeping this phase single-
    session and single-threaded is the right shape regardless of platform.
    Only the judge phase (API-bound) parallelizes.
    """
    handle = _create_session(client, "rollout_worker", environment_id=environment_id)
    runtime.append_chat(
        "session_created",
        worker="rollout",
        role="rollout_worker",
        session_id=handle.session_id,
    )
    payload = (
        f"Your assigned matrix rows ({len(rows)} rollouts) are below as JSON. "
        "Run each one sequentially via the `rollout` tool, then submit_results "
        "exactly once.\n\n"
        f"{json.dumps(rows, indent=2)}"
    )
    _send_user_message(client, handle.session_id, payload)
    return _drive_session_to_end_turn(
        client,
        handle.session_id,
        label="rollout",
        mirror_root=mirror_root,
        messages_client=messages_client,
        cost_tracker=cost_tracker,
        runtime=runtime,
    )


def _run_judge_workers(
    client: Anthropic,
    *,
    environment_id: str,
    chunks: list[list[dict[str, Any]]],
    mirror_root: Path,
    messages_client: Anthropic,
    cost_tracker: CostTracker,
    runtime: RuntimeState,
) -> list[str]:
    """Fan out K judge workers, one per chunk of completed rollouts.

    This is the phase where parallelism actually pays off — the judge
    calls are API-bound and fully parallelize across workers.
    """
    results: list[str] = [""] * len(chunks)

    def _worker(i: int, chunk: list[dict[str, Any]]) -> str:
        handle = _create_session(
            client, "judge_worker", environment_id=environment_id, worker_index=i
        )
        runtime.append_chat(
            "session_created",
            worker=f"judge-{i:02d}",
            role="judge_worker",
            session_id=handle.session_id,
        )
        payload = (
            f"You are judge worker {i + 1} of {len(chunks)}. "
            f"Your assigned rollouts ({len(chunk)} records) are below as JSON. "
            "For each rollout: if success=true, emit a Finding with "
            "sim_success=true and annotation=null (no judge call). "
            "If success=false, call `judge` on the mp4 and emit a Finding with "
            "sim_success=false and annotation=<judge output>. "
            "Then submit_findings exactly once with every rollout's Finding row.\n\n"
            f"{json.dumps(chunk, indent=2)}"
        )
        _send_user_message(client, handle.session_id, payload)
        return _drive_session_to_end_turn(
            client,
            handle.session_id,
            label=f"judge-{i:02d}",
            mirror_root=mirror_root,
            messages_client=messages_client,
            cost_tracker=cost_tracker,
            runtime=runtime,
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(chunks)) as pool:
        futures = {pool.submit(_worker, i, chunk): i for i, chunk in enumerate(chunks)}
        for fut in concurrent.futures.as_completed(futures):
            i = futures[fut]
            results[i] = fut.result()
    return results


def _build_reporter_message(
    *,
    mirror_root: Path,
    n_rollouts: int,
    elapsed_seconds: float,
    cost_tracker: CostTracker,
) -> str:
    """Compose the reporter's first message with ALL upstream artifacts inlined.

    The reporter session has its own /memories/ — it cannot read the planner's
    or judges' files. We inline plan.md, test_matrix.csv, results.jsonl,
    findings.jsonl, and the runtime numbers so the reporter has everything
    it needs in one message.
    """
    plan_md = (mirror_root / "plan.md").read_text(encoding="utf-8")
    matrix_csv = (mirror_root / "test_matrix.csv").read_text(encoding="utf-8")
    results_jsonl_path = mirror_root / "rollouts" / "results.jsonl"
    findings_jsonl_path = mirror_root / "findings.jsonl"
    results_jsonl = (
        results_jsonl_path.read_text(encoding="utf-8") if results_jsonl_path.exists() else ""
    )
    findings_jsonl = (
        findings_jsonl_path.read_text(encoding="utf-8") if findings_jsonl_path.exists() else ""
    )

    pipeline_cost = cost_tracker.total_cost_usd
    base_cost = baseline_cost_for(n_rollouts)
    base_time = baseline_seconds_for(n_rollouts)

    buf = io.StringIO()
    buf.write("The planner, rollout worker, and judge workers have finished. ")
    buf.write("Write the final report.md and submit it via submit_report.\n\n")
    buf.write("=== plan.md ===\n")
    buf.write(plan_md.rstrip() + "\n\n")
    buf.write("=== test_matrix.csv ===\n")
    buf.write(matrix_csv.rstrip() + "\n\n")
    buf.write("=== results.jsonl ===\n")
    buf.write(results_jsonl.rstrip() + "\n\n")
    buf.write("=== findings.jsonl ===\n")
    buf.write(findings_jsonl.rstrip() + "\n\n")
    buf.write("=== Runtime numbers (use these EXACTLY) ===\n")
    buf.write(f"- Total cost (this pipeline): {format_cost(pipeline_cost)}\n")
    buf.write(f"- Wall time (this pipeline): {format_duration(elapsed_seconds)}\n")
    buf.write(f"- Scenarios run: {n_rollouts}\n")
    buf.write(
        f"- Baseline cost (manual reviewer at ${BASELINE_HOURLY_RATE_USD:.0f}/hr × "
        f"{BASELINE_SECONDS_PER_ROLLOUT // 60} min/rollout): {format_cost(base_cost)}\n"
    )
    buf.write(f"- Baseline wall time (sequential reviewer): {format_duration(base_time)}\n\n")
    buf.write("=== Token breakdown (for methodology) ===\n")
    buf.write(f"- input_tokens: {cost_tracker.input_tokens}\n")
    buf.write(f"- output_tokens: {cost_tracker.output_tokens}\n")
    buf.write(f"- cache_read_tokens: {cost_tracker.cache_read_tokens}\n")
    buf.write(f"- cache_creation_tokens: {cost_tracker.cache_creation_tokens}\n")
    return buf.getvalue()


def _run_reporter(
    client: Anthropic,
    *,
    environment_id: str,
    mirror_root: Path,
    n_rollouts: int,
    elapsed_seconds: float,
    messages_client: Anthropic,
    cost_tracker: CostTracker,
    runtime: RuntimeState,
) -> str:
    handle = _create_session(client, "reporter", environment_id=environment_id)
    runtime.append_chat(
        "session_created", worker="reporter", role="reporter", session_id=handle.session_id
    )
    _send_user_message(
        client,
        handle.session_id,
        _build_reporter_message(
            mirror_root=mirror_root,
            n_rollouts=n_rollouts,
            elapsed_seconds=elapsed_seconds,
            cost_tracker=cost_tracker,
        ),
    )
    return _drive_session_to_end_turn(
        client,
        handle.session_id,
        label="reporter",
        mirror_root=mirror_root,
        messages_client=messages_client,
        cost_tracker=cost_tracker,
        runtime=runtime,
    )


# ---- Top-level entry point -------------------------------------------------------


def run_multi_agent(
    client: Anthropic,
    *,
    user_goal: str,
    mirror_root: Path,
    k_workers: int = 4,
    run_id: str = "",
    messages_client: Anthropic | None = None,
    cost_tracker: CostTracker | None = None,
    skip_labeling: bool = False,
    label_seed: int = 0,
) -> PlanBResult:
    """Drive the full Plan B flow end-to-end.

    Phases:
      1. Planner (1 session). Must produce plan.md + test_matrix.csv.
      2. Rollout worker (1 session, sequential on main thread). Must produce
         results.jsonl for every matrix row.
      2.5. Human labeling (host-side, no agent). Samples a subset of scripted
           rollouts, blocks until the Gradio UI has collected labels. Skipped
           when `skip_labeling=True`.
      3. Judge workers (K parallel). Must produce findings.jsonl for every
         rollout.
      4. Reporter (1 session). Must produce report.md.

    Returns per-phase stop reasons + cost + timing + scenario count.
    """
    if messages_client is None:
        messages_client = client
    if cost_tracker is None:
        cost_tracker = CostTracker()

    mirror_root.mkdir(parents=True, exist_ok=True)
    start_time = time.time()

    runtime = RuntimeState(
        mirror_root=mirror_root,
        cost_tracker=cost_tracker,
        start_time=start_time,
        session_id="plan-b-multi",
        planned_total=None,  # populated after planner finishes
        run_id=run_id,
        goal=user_goal,
    )
    runtime.write_meta()
    runtime.set_phase("starting")

    environment_id = _create_shared_environment(client)
    logger.info("plan-b shared env=%s", environment_id)

    stops: dict[str, list[str]] = {"planner": [], "rollout": [], "judge": [], "report": []}

    # 1) Planner — single session.
    runtime.set_phase(PHASE_PLANNER)
    runtime.append_chat("phase_marker", marker=PHASE_PLANNER)
    stop = _run_planner(
        client,
        environment_id=environment_id,
        user_goal=user_goal,
        mirror_root=mirror_root,
        messages_client=messages_client,
        cost_tracker=cost_tracker,
        runtime=runtime,
    )
    stops["planner"].append(stop)
    if stop != "end_turn":
        logger.warning("planner ended with %s — bailing", stop)
        return PlanBResult(
            stops=stops,
            cost_tracker=cost_tracker,
            elapsed_seconds=time.time() - start_time,
            n_rollouts=0,
            k_workers=k_workers,
        )

    # 2) Rollout worker — ONE session, sequential, main-thread (see the
    #    module docstring for the GLFW / Cocoa main-thread requirement).
    matrix_rows = _load_matrix_rows(mirror_root)
    runtime.planned_total = len(matrix_rows)
    runtime.write_snapshot()
    runtime.set_phase(PHASE_ROLLOUT)
    runtime.append_chat("phase_marker", marker=PHASE_ROLLOUT)
    rollout_stop = _run_rollout_worker(
        client,
        environment_id=environment_id,
        rows=matrix_rows,
        mirror_root=mirror_root,
        messages_client=messages_client,
        cost_tracker=cost_tracker,
        runtime=runtime,
    )
    stops["rollout"].append(rollout_stop)
    if rollout_stop != "end_turn":
        logger.warning("rollout worker ended non-end_turn: %s", rollout_stop)

    # 2.5) Human labeling phase — host-side, no Managed Agents session. Reads
    #      dispatch_log.jsonl, samples a subset of completed scripted rollouts,
    #      writes the queue, and blocks until the Gradio UI has logged a
    #      HumanLabel for every queued rollout. `skip_labeling=True` bypasses
    #      the block (smoke / CI path).
    run_label_phase(
        runtime,
        mirror_root,
        skip_labeling=skip_labeling,
        sample_seed=label_seed,
    )

    # 3) Judge workers — parallel.
    results = _load_results(mirror_root)
    if not results:
        logger.warning("no rollout results; skipping judge + report")
        return PlanBResult(
            stops=stops,
            cost_tracker=cost_tracker,
            elapsed_seconds=time.time() - start_time,
            n_rollouts=0,
            k_workers=k_workers,
        )
    judge_chunks = _split_rows_round_robin(cast(Any, results), k_workers)
    runtime.set_phase(PHASE_JUDGE)
    runtime.append_chat("phase_marker", marker=PHASE_JUDGE)
    stops["judge"] = _run_judge_workers(
        client,
        environment_id=environment_id,
        chunks=judge_chunks,
        mirror_root=mirror_root,
        messages_client=messages_client,
        cost_tracker=cost_tracker,
        runtime=runtime,
    )
    if not all(s == "end_turn" for s in stops["judge"]):
        logger.warning("some judge workers ended non-end_turn: %s", stops["judge"])

    # 4) Reporter — single session.
    runtime.set_phase(PHASE_REPORT)
    runtime.append_chat("phase_marker", marker=PHASE_REPORT)
    stop = _run_reporter(
        client,
        environment_id=environment_id,
        mirror_root=mirror_root,
        n_rollouts=len(results),
        elapsed_seconds=time.time() - start_time,
        messages_client=messages_client,
        cost_tracker=cost_tracker,
        runtime=runtime,
    )
    stops["report"].append(stop)

    runtime.set_phase("complete")
    return PlanBResult(
        stops=stops,
        cost_tracker=cost_tracker,
        elapsed_seconds=time.time() - start_time,
        n_rollouts=len(results),
        k_workers=k_workers,
    )
