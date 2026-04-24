"""Plan-A orchestrator: ONE Managed Agents session, four phases via markers.

CLAUDE.md sec 3 (Plan A):
  - One agent, one environment, one session
  - Four phases (planner / rollout / judge / report) inside the same session,
    triggered by sending phase-marker user messages between them
  - The agent thinks to /memories/; we read along by mirroring artifacts to
    artifacts/sessions/<id>/

Loop shape per phase:
  1) Send the phase marker as a user message.
  2) Stream events. For each `agent.custom_tool_use`, dispatch locally and
     send back a `user.custom_tool_result`.
  3) Stop when the session goes idle with stop_reason=end_turn (the agent
     decided this phase is done) — then advance.

This keeps the four phases legible (you can read /memories/plan.md, then
test_matrix.csv, then results.jsonl, then findings.jsonl, then report.md
in order to see the run) without needing four separate sessions.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from anthropic import Anthropic

from src.agents.system_prompts import (
    PHASE_MARKER_JUDGE,
    PHASE_MARKER_PLANNER,
    PHASE_MARKER_REPORT,
    PHASE_MARKER_ROLLOUT,
    SYSTEM_PROMPT,
)
from src.agents.tools import dispatch as dispatch_custom_tool
from src.agents.tools import tool_params
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
from src.runtime_state import RuntimeState

logger = logging.getLogger(__name__)

# Goals tend to mention "N scenarios", "N rollouts", or "N <env> ..." somewhere.
# Sum every match so a goal like "2 clean + 3 injected + 5 pretrained" reports 10.
import re as _re  # noqa: E402

_PLANNED_TOTAL_PATTERN = _re.compile(
    r"(\d+)\s+(?:scripted|pretrained|mixed|clean|injected|calibration|deployment)?\s*"
    r"(?:Lift|scenarios|rollouts|rows)",
    _re.IGNORECASE,
)


def _parse_planned_total(goal: str) -> int | None:
    """Best-effort: sum all 'N <something>' counts in the goal string.

    Returns None if no number-like phrase matches. The progress strip in the
    UI then renders without a denominator until ROLLOUT phase finishes (at
    which point the actual dispatched count becomes the denominator).
    """
    matches = [int(m.group(1)) for m in _PLANNED_TOTAL_PATTERN.finditer(goal)]
    return sum(matches) if matches else None


@dataclass(frozen=True)
class SessionHandle:
    """Wires together the three IDs we need to drive a session."""

    agent_id: str
    environment_id: str
    session_id: str


def _builtin_toolset() -> dict[str, Any]:
    """Built-in agent toolset (read/edit/write/bash etc.) with auto-approval.

    The orchestrator runs unattended, so we use always_allow on all built-ins.
    Each tool is enabled explicitly so the agent gets exactly the surface we
    described in the system prompt — no surprise web_fetch/web_search calls.
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


def _all_tools() -> list[dict[str, Any]]:
    return [_builtin_toolset(), *tool_params()]


def setup(
    client: Anthropic,
    *,
    agent_name: str = "embodied-eval-orchestrator",
    environment_name: str = "embodied-eval-env",
    title: str = "Embodied eval run",
) -> SessionHandle:
    """Create the agent + environment + session. Returns IDs for driving the loop.

    The Anthropic SDK reads the `betas` arg as a header on each call. Only the
    Managed Agents beta header is needed here.
    """
    betas = [MANAGED_AGENTS_BETA_HEADER]

    agent = client.beta.agents.create(
        model=OPUS_MODEL_ID,
        name=agent_name,
        description="Designs, runs, and reports on robot manipulation policy evals.",
        system=SYSTEM_PROMPT,
        tools=cast(Any, _all_tools()),
        betas=betas,
    )

    env = client.beta.environments.create(
        name=environment_name,
        config=cast(Any, {"type": "cloud"}),
        description="MuJoCo + robosuite + robomimic for the eval orchestrator.",
        betas=betas,
    )

    session = client.beta.sessions.create(
        agent=agent.id,
        environment_id=env.id,
        title=title,
        betas=betas,
    )

    handle = SessionHandle(agent_id=agent.id, environment_id=env.id, session_id=session.id)
    logger.info(
        "session ready agent=%s env=%s session=%s",
        handle.agent_id,
        handle.environment_id,
        handle.session_id,
    )
    return handle


def _send_user_message(client: Anthropic, session_id: str, text: str) -> None:
    client.beta.sessions.events.send(
        session_id,
        events=cast(
            Any,
            [
                {
                    "type": "user.message",
                    "content": [{"type": "text", "text": text}],
                }
            ],
        ),
        betas=[MANAGED_AGENTS_BETA_HEADER],
    )


def _send_tool_result(
    client: Anthropic, session_id: str, tool_use_id: str, payload: str, *, is_error: bool = False
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
    """Yield events from the session stream until it closes."""
    with client.beta.sessions.events.stream(
        session_id, betas=[MANAGED_AGENTS_BETA_HEADER]
    ) as stream:
        yield from stream


def _run_one_turn(
    client: Anthropic,
    session_id: str,
    *,
    mirror_root: Path,
    messages_client: Anthropic,
    cost_tracker: CostTracker,
    runtime: RuntimeState,
) -> str:
    """Drive one phase of the session to completion. Returns the terminal stop_reason.

    `requires_action` is non-terminal: the session paused for tool results,
    which we already sent inline when the `agent.custom_tool_use` event
    arrived. We reopen the stream and let the agent continue. Only
    `end_turn` / `retries_exhausted` (or `session.error`) actually stops a
    phase. Token usage on every event with a `usage` field is summed into
    `cost_tracker`; runtime.json + chat.jsonl are updated on every event
    so the UI can read along.
    """
    while True:
        terminal: str | None = None
        saw_status_idle = False

        for event in _stream_events(client, session_id):
            ev_type = getattr(event, "type", None)
            logger.debug("event %s", ev_type)

            # Some session events carry a usage field (esp. agent.message and
            # session.status_idle); accumulate defensively whenever present.
            usage = getattr(event, "usage", None)
            if usage is not None:
                cost_tracker.add_usage(usage)

            if ev_type == "agent.message":
                text = "".join(
                    block.text for block in getattr(event, "content", []) if block.type == "text"
                )
                if text:
                    logger.info("agent: %s", text[:500])
                    runtime.append_chat("agent_message", text=text)

            elif ev_type == "agent.thinking":
                text = getattr(event, "text", "") or ""
                if text:
                    logger.debug("thinking: %s", text[:500])
                    runtime.append_chat("agent_thinking", text=text)

            elif ev_type == "agent.custom_tool_use":
                tool_name = event.name
                tool_input = event.input
                logger.info("tool_use %s args=%s", tool_name, tool_input)
                runtime.append_chat("tool_use", tool=tool_name, args=dict(tool_input))
                try:
                    payload = dispatch_custom_tool(
                        tool_name,
                        dict(tool_input),
                        mirror_root=mirror_root,
                        client=messages_client,
                        cost_tracker=cost_tracker,
                    )
                    _send_tool_result(client, session_id, event.id, payload)
                    runtime.append_chat("tool_result", tool=tool_name, payload=payload)
                except Exception as exc:  # noqa: BLE001 — must report back to the agent
                    logger.exception("tool %s failed", tool_name)
                    _send_tool_result(
                        client,
                        session_id,
                        event.id,
                        f'{{"error": "{type(exc).__name__}: {exc}"}}',
                        is_error=True,
                    )
                    runtime.append_chat("tool_error", tool=tool_name, error=str(exc))

            elif ev_type == "session.status_idle":
                saw_status_idle = True
                stop_type = getattr(getattr(event, "stop_reason", None), "type", "unknown")
                logger.info("idle stop_reason=%s", stop_type)
                if stop_type == "requires_action":
                    # Tool results were sent inline above; reopen the stream
                    # so the agent can pick up where it left off.
                    runtime.mark_event()
                    break
                terminal = str(stop_type)
                break

            elif ev_type == "session.error":
                logger.error("session error: %s", event)
                terminal = "error"
                break

            runtime.mark_event()

        if terminal is not None:
            runtime.mark_event()
            return terminal
        if not saw_status_idle:
            # Stream closed without a status_idle event — unusual, bail out
            # rather than reopen indefinitely.
            return "stream_closed"
        # else: requires_action — outer while reopens the stream.


PHASE_MARKERS = (
    PHASE_MARKER_PLANNER,
    PHASE_MARKER_ROLLOUT,
    PHASE_MARKER_JUDGE,
    PHASE_MARKER_REPORT,
)


@dataclass(frozen=True)
class SessionResult:
    """End-of-run summary the caller (e.g. scripts/smoke_agent.py) consumes."""

    stops: list[str]
    cost_tracker: CostTracker
    elapsed_seconds: float
    n_rollouts: int


def _build_report_marker(n_rollouts: int, elapsed_seconds: float, cost_tracker: CostTracker) -> str:
    """Compose the REPORT phase marker with runtime numbers inlined.

    The agent uses these exact numbers in the report rather than fabricating
    its own — without this the cost/time/baseline columns would be either
    invented or left as placeholders.
    """
    pipeline_cost = cost_tracker.total_cost_usd
    baseline_cost = baseline_cost_for(n_rollouts)
    baseline_time_s = baseline_seconds_for(n_rollouts)
    return f"""{PHASE_MARKER_REPORT}

Runtime numbers from the orchestrator (use these EXACTLY — do not invent or
estimate cost/time figures, do not round more than necessary):

- Total cost (this pipeline): {format_cost(pipeline_cost)}
- Wall time (this pipeline): {format_duration(elapsed_seconds)}
- Scenarios run: {n_rollouts}
- Baseline cost (manual reviewer at ${BASELINE_HOURLY_RATE_USD:.0f}/hr × \
{BASELINE_SECONDS_PER_ROLLOUT // 60} min/rollout): {format_cost(baseline_cost)}
- Baseline wall time (one reviewer working sequentially): {format_duration(baseline_time_s)}

Token breakdown (for the methodology section):
- input_tokens: {cost_tracker.input_tokens}
- output_tokens: {cost_tracker.output_tokens}
- cache_read_tokens: {cost_tracker.cache_read_tokens}
- cache_creation_tokens: {cost_tracker.cache_creation_tokens}

The Summary section MUST include a side-by-side comparison row putting our
pipeline against the manual-review baseline (cost ratio and time ratio),
because that comparison is the demo's headline number.
"""


def run_all_phases(
    client: Anthropic,
    handle: SessionHandle,
    *,
    user_goal: str,
    mirror_root: Path,
    run_id: str = "",
    messages_client: Anthropic | None = None,
    cost_tracker: CostTracker | None = None,
) -> SessionResult:
    """Drive all four phases in order. Returns stops + cost + time + scenario count.

    The user_goal is sent together with the PLANNER marker so the agent has
    a one-line objective for the test matrix. The REPORT marker is enriched
    with measured runtime numbers so the agent doesn't fabricate them.
    """
    if messages_client is None:
        messages_client = client
    if cost_tracker is None:
        cost_tracker = CostTracker()

    mirror_root.mkdir(parents=True, exist_ok=True)
    rollouts_dir = mirror_root / "rollouts"

    start_time = time.time()
    runtime = RuntimeState(
        mirror_root=mirror_root,
        cost_tracker=cost_tracker,
        start_time=start_time,
        session_id=handle.session_id,
        planned_total=_parse_planned_total(user_goal),
        run_id=run_id,
        goal=user_goal,
    )
    runtime.write_meta()
    runtime.set_phase("starting")

    stops: list[str] = []
    for marker in PHASE_MARKERS:
        runtime.set_phase(marker)
        runtime.append_chat("phase_marker", marker=marker)
        if marker == PHASE_MARKER_PLANNER:
            payload = f"{marker}\n\nEvaluation goal: {user_goal}"
        elif marker == PHASE_MARKER_REPORT:
            n_rollouts = len(list(rollouts_dir.glob("*.mp4"))) if rollouts_dir.exists() else 0
            payload = _build_report_marker(
                n_rollouts=n_rollouts,
                elapsed_seconds=time.time() - start_time,
                cost_tracker=cost_tracker,
            )
        else:
            payload = marker
        _send_user_message(client, handle.session_id, payload)
        stop = _run_one_turn(
            client,
            handle.session_id,
            mirror_root=mirror_root,
            messages_client=messages_client,
            cost_tracker=cost_tracker,
            runtime=runtime,
        )
        stops.append(stop)
        if stop != "end_turn":
            logger.warning("phase %s ended with %s — stopping orchestrator", marker, stop)
            break

    runtime.set_phase("complete")
    n_rollouts_final = len(list(rollouts_dir.glob("*.mp4"))) if rollouts_dir.exists() else 0
    return SessionResult(
        stops=stops,
        cost_tracker=cost_tracker,
        elapsed_seconds=time.time() - start_time,
        n_rollouts=n_rollouts_final,
    )
