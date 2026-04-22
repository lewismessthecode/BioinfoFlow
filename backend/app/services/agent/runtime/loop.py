"""Core agent loop with streaming support.

Explicit async loop with between-turn hooks: compaction, nag reminders,
background task draining, and tool dispatch. LLM calls are streamed
and events are pushed to the frontend in real-time via on_event().
"""

from __future__ import annotations

import inspect
import json
import time
from typing import TYPE_CHECKING, Any, Callable, Awaitable

from app.config import settings
from app.services.agent.runtime.compact import (
    auto_compact,
    micro_compact,
    should_auto_compact,
)
from app.services.agent.runtime.messages import (
    make_tool_results,
    make_user_message,
)
from app.services.agent.runtime.stream_events import (
    AgentDone,
    AgentError,
    TextDelta,
    ThinkingDelta,
    ToolCallsAccumulated,
)
from app.services.agent.tools.base import RiskLevel
from app.utils.logging import get_logger

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.services.agent.runtime.dispatch import ToolEntry
    from app.services.agent.runtime.llm_client import LLMClient
    from app.services.agent.runtime.session_state import SessionState
    from app.services.agent.trace import AgentTraceRecorder

logger = get_logger(__name__)


class ToolRejectedError(Exception):
    """Raised when a high-risk tool is rejected by the user."""


_RISK_ORDER = {RiskLevel.READ: 0, RiskLevel.ACT_LOW: 1, RiskLevel.ACT_HIGH: 2}


def _min_risk(a: str, b: str) -> str:
    """Return whichever of ``a`` / ``b`` is *less* privileged.

    Used so a per-invocation resolver can only lower risk, never raise it —
    a buggy resolver raising a declared-READ tool to ACT_HIGH would otherwise
    start demanding approvals for benign reads.
    """
    return a if _RISK_ORDER.get(a, 2) <= _RISK_ORDER.get(b, 2) else b


def _requires_approval_by_policy(
    tool_name: str,
    risk_level: str,
    *,
    policy: str | None = None,
) -> bool:
    """Decide whether a given tool call needs user approval.

    Args:
        tool_name: Name of the tool being invoked.
        risk_level: Declared risk (READ / ACT_LOW / ACT_HIGH).
        policy: Explicit execution policy to apply. When None, falls back to
            ``settings.agent_execution_policy`` (the global default).

    Policies:
        - ``auto`` (default): prompt on ACT_HIGH (except execute_code which
          runs inline in sandbox).
        - ``approve_python``: prompt on every ACT_HIGH, including
          execute_code.
        - ``approve_all``: prompt on ACT_LOW and ACT_HIGH — strict mode.
        - ``bypass``: never prompt. Agent runs all tools without approval.
          Matches Claude Code's ``--dangerously-skip-permissions`` and
          Codex's bypass mode — user has explicitly opted in per-conversation.
    """
    resolved = (
        policy
        if policy is not None
        else getattr(settings, "agent_execution_policy", "auto") or "auto"
    )
    resolved = resolved.strip().lower()

    if resolved == "bypass":
        return False

    if risk_level == RiskLevel.READ:
        return False

    if resolved == "auto":
        return risk_level == RiskLevel.ACT_HIGH and tool_name != "execute_code"

    if resolved == "approve_python":
        return risk_level == RiskLevel.ACT_HIGH

    if resolved == "approve_all":
        return risk_level in (RiskLevel.ACT_LOW, RiskLevel.ACT_HIGH)

    return risk_level == RiskLevel.ACT_HIGH


async def _check_risk(
    tool_name: str,
    tool_input: dict[str, Any],
    risk_level: str,
    *,
    on_event: Callable[[dict[str, Any]], Awaitable[None]],
    session: "AsyncSession | None" = None,
    conversation_id: str = "",
    execution_policy: str | None = None,
) -> None:
    """Check tool risk level and enforce approval for high-risk tools.

    Risk enforcement policy:
    - READ: auto-allow silently
    - ACT_LOW: allow with info log
    - ACT_HIGH: require user approval via ApprovalService, unless the
      conversation's ``execution_policy`` is ``"bypass"``.
    """
    if risk_level == RiskLevel.READ:
        return
    if not _requires_approval_by_policy(
        tool_name, risk_level, policy=execution_policy
    ):
        logger.info("risk.auto_allowed", tool=tool_name, risk_level=risk_level)
        return

    logger.warning("risk.requires_approval", tool=tool_name, risk_level=risk_level)

    if session is None or not conversation_id:
        logger.warning("risk.requires_approval.no_session", tool=tool_name)
        return

    from app.services.agent.approval_service import (
        ApprovalService,
        ApprovalTimeoutError,
    )
    from app.enums import ApprovalStatus

    approval_svc = ApprovalService(session)
    approval_type = approval_svc.get_approval_type_for_tool(tool_name)
    approval = await approval_svc.create_approval(
        conversation_id=conversation_id,
        step_id=f"tool:{tool_name}",
        approval_type=approval_type,
        payload={"tool": tool_name, "input": tool_input},
    )

    await on_event({
        "type": "status",
        "content": f"Approval required for {tool_name}",
        "metadata": {
            "approval_id": str(approval.id),
            "approval_type": approval_type,
            "tool": tool_name,
            "input": tool_input,
            "requires_approval": True,
        },
        # Must be stream=True so _persist_and_publish_agent_event publishes
        # the raw metadata (with requires_approval) rather than the merged
        # message.message_metadata — STATUS has no merge branch, so merged
        # metadata drops the approval fields and the frontend falls through
        # to the text branch, leaving the user no way to approve.
        "stream": True,
    })

    try:
        # No timeout — poll until the user responds or the surrounding task
        # is cancelled (Stop button). Claude Code / Codex behave the same way:
        # the user decides when to decide.
        resolved = await approval_svc.wait_for_approval(
            str(approval.id), timeout=None, poll_interval=1.0,
        )
    except ApprovalTimeoutError:
        logger.warning("risk.requires_approval.timeout", tool=tool_name)
        raise ToolRejectedError(f"Approval for {tool_name} timed out")

    if resolved.status != ApprovalStatus.APPROVED:
        logger.info("risk.requires_approval.rejected", tool=tool_name)
        raise ToolRejectedError(f"User rejected {tool_name}")

    logger.info("risk.requires_approval.approved", tool=tool_name)


def _make_cancel_checker(
    is_cancelled: Callable[[], bool | Awaitable[bool]],
) -> Callable[[], Awaitable[bool]]:
    """Wrap an is_cancelled callback so it's always awaitable.

    Handles three shapes safely:
      1. async def → passed through.
      2. sync fn returning bool → wrapped in a coroutine.
      3. sync fn returning an awaitable (e.g. a lambda that calls an async
         method without awaiting it) → awaited inside the wrapper. This third
         case is the easy-to-miss footgun: ``if await checker():`` on a naked
         coroutine object is always truthy, which silently cancels every turn.
    """
    if inspect.iscoroutinefunction(is_cancelled):
        return is_cancelled  # type: ignore[return-value]

    async def _async_wrapper() -> bool:
        result = is_cancelled()
        if inspect.isawaitable(result):
            result = await result
        return bool(result)

    return _async_wrapper


async def agent_loop(
    *,
    user_message: str,
    session_state: "SessionState",
    dispatch_map: dict[str, "ToolEntry"],
    llm: "LLMClient",
    system_prompt: str | Callable[[], str],
    on_event: Callable[[dict[str, Any]], Awaitable[None]],
    is_cancelled: Callable[[], bool | Awaitable[bool]],
    trace_recorder: "AgentTraceRecorder | None" = None,
    max_rounds: int | None = None,
    compact_threshold: int | None = None,
    db_session: "AsyncSession | None" = None,
    conversation_id: str = "",
    execution_policy: str | None = None,
) -> None:
    """Run the agent loop until completion, cancellation, or round limit.

    Streams LLM responses in real-time via on_event() using StreamEvent types.

    ``execution_policy``, when provided, overrides the global
    ``settings.agent_execution_policy`` for this turn only. Use it to
    implement per-conversation execution modes (e.g. ``"bypass"``).
    """
    if max_rounds is None:
        max_rounds = getattr(settings, "agent_max_rounds", 50)
    if compact_threshold is None:
        compact_threshold = getattr(settings, "agent_compact_threshold", 50_000)

    messages = session_state.messages
    tool_schemas = _get_tool_schemas(dispatch_map)

    messages.append(make_user_message(user_message))

    compact_requested = False
    _check_cancelled = _make_cancel_checker(is_cancelled)

    for _round in range(max_rounds):
        if await _check_cancelled():
            return

        session_state.increment_round()

        # --- Between-turn hooks ---

        # Drain background task notifications
        if session_state.background_manager:
            bg_results = session_state.background_manager.drain_notifications()
            if bg_results:
                parts = []
                for r in bg_results:
                    parts.append(
                        f"[{r.task_id}] `{r.command}` "
                        f"exit={r.exit_code} ({r.elapsed_seconds}s)\n"
                        f"stdout: {r.stdout[:2000]}\n"
                        f"stderr: {r.stderr[:500]}"
                    )
                messages.append(
                    make_user_message(
                        f"<background-results>\n{'---\n'.join(parts)}\n</background-results>"
                    )
                )

        # Layer 1: micro-compact stale tool results
        micro_compact(messages, session_state.current_round)

        resolved_prompt = system_prompt() if callable(system_prompt) else system_prompt

        # Layer 2/3: auto-compact if over threshold or manually requested
        if compact_requested or should_auto_compact(messages, compact_threshold):
            logger.info(
                "loop.compact",
                round=session_state.current_round,
                reason="manual" if compact_requested else "auto",
            )
            messages = await auto_compact(
                messages,
                llm=llm,
                system_prompt=resolved_prompt,
                transcript_dir=session_state.transcript_dir,
            )
            session_state.messages = messages
            compact_requested = False

        # Nag reminder for stale todos
        if session_state.todo.should_nag():
            nag = session_state.todo.nag_message()
            messages.append(make_user_message(nag))
            session_state.todo.rounds_since_update = 0

        # --- LLM call (streaming) ---
        if trace_recorder and settings.agent_observability:
            await trace_recorder.record_prompt(
                {
                    "round": session_state.current_round,
                    "messages_count": len(messages),
                }
            )

        # Accumulate the full response while streaming deltas
        text_acc = ""
        thinking_acc = ""
        tool_calls: list[dict[str, Any]] = []
        usage: dict[str, int] = {}
        had_error = False

        async for event in llm.create_stream(
            system=resolved_prompt,
            messages=messages,
            tools=tool_schemas,
            max_tokens=settings.agent_max_tokens,
        ):
            if await _check_cancelled():
                return

            if isinstance(event, TextDelta):
                text_acc += event.text
                await on_event({
                    "type": "text_delta",
                    "content": event.text,
                    "stream": True,
                })
            elif isinstance(event, ThinkingDelta):
                thinking_acc += event.text
                await on_event({
                    "type": "thinking_delta",
                    "content": event.text,
                    "stream": True,
                })
            elif isinstance(event, ToolCallsAccumulated):
                tool_calls = event.tool_calls
            elif isinstance(event, AgentDone):
                usage = event.usage
            elif isinstance(event, AgentError):
                had_error = True
                await on_event({
                    "type": "error",
                    "content": event.message,
                    "metadata": {},
                })

        if had_error:
            if trace_recorder:
                await trace_recorder.flush()
            return

        session_state.accumulate_usage(usage)

        # Emit thinking_content event with accumulated thinking
        if thinking_acc:
            await on_event({
                "type": "thinking_content",
                "content": thinking_acc,
                "metadata": {"thinking_tokens": usage.get("thinking_tokens", 0)},
            })

        if trace_recorder and settings.agent_observability:
            await trace_recorder.record_response(
                {
                    "round": session_state.current_round,
                    "stop_reason": "tool_use" if tool_calls else "end_turn",
                    "usage": usage,
                }
            )

        # Build and append assistant message (OpenAI format)
        assistant_msg: dict[str, Any] = {
            "role": "assistant",
            "content": text_acc,
        }
        if tool_calls:
            assistant_msg["tool_calls"] = [
                {
                    "id": tc["id"],
                    "type": "function",
                    "function": {
                        "name": tc["name"],
                        "arguments": json.dumps(tc["input"]),
                    },
                }
                for tc in tool_calls
            ]
        messages.append(assistant_msg)

        # --- Handle response ---
        if not tool_calls:
            # Final text response — emit completion event and exit
            await on_event({
                "type": "text",
                "content": text_acc,
                "metadata": {"usage": usage},
            })
            if trace_recorder:
                await trace_recorder.flush()
            return

        # --- Tool dispatch ---
        results: list[str] = []

        for call in tool_calls:
            if await _check_cancelled():
                return

            tool_name = call["name"]
            tool_input = call.get("input", {})
            tool_id = call["id"]
            entry = dispatch_map.get(tool_name)

            # Emit tool_call_start
            await on_event({
                "type": "tool_call_start",
                "content": tool_name,
                "metadata": {"id": tool_id, "name": tool_name, "args": tool_input},
                "stream": True,
            })

            start_time = time.perf_counter()

            if not entry:
                result_str = json.dumps({"error": f"Unknown tool: {tool_name}"})
                is_error = True
            else:
                is_error = False
                # Let the tool resolve risk from the concrete input (e.g. shell
                # downgrades "git status" to ACT_LOW). Resolvers must only
                # lower the declared risk — never raise it — so we clamp to
                # the stricter of the two as a defence against buggy resolvers.
                declared_risk = entry.risk_level
                if entry.risk_resolver is not None:
                    try:
                        resolved_risk = entry.risk_resolver(tool_input) or declared_risk
                    except Exception as exc:  # pragma: no cover - defensive
                        logger.warning(
                            "risk.resolver_failed",
                            tool=tool_name,
                            error=str(exc),
                        )
                        resolved_risk = declared_risk
                else:
                    resolved_risk = declared_risk
                effective_risk = _min_risk(declared_risk, resolved_risk)
                try:
                    await _check_risk(
                        tool_name,
                        tool_input,
                        effective_risk,
                        on_event=on_event,
                        session=db_session,
                        conversation_id=conversation_id,
                        execution_policy=execution_policy,
                    )
                except ToolRejectedError as exc:
                    result_str = json.dumps({"error": str(exc)})
                    is_error = True
                    results.append(result_str)

                    elapsed = (time.perf_counter() - start_time) * 1000
                    await on_event({
                        "type": "tool_call_end",
                        "content": tool_name,
                        "metadata": {
                            "id": tool_id, "name": tool_name,
                            "result": result_str, "is_error": True,
                            "duration_ms": round(elapsed, 2),
                        },
                        "stream": True,
                    })
                    continue

                result_str = await entry.handler(**tool_input)

            elapsed = (time.perf_counter() - start_time) * 1000
            results.append(result_str)

            if tool_name == "compact":
                compact_requested = True

            # Emit tool_call_end
            await on_event({
                "type": "tool_call_end",
                "content": tool_name,
                "metadata": {
                    "id": tool_id, "name": tool_name,
                    "result": result_str[:2000],  # Truncate for SSE
                    "is_error": is_error,
                    "duration_ms": round(elapsed, 2),
                },
                "stream": True,
            })

            if trace_recorder:
                trace_recorder.queue_tool(
                    {
                        "tool": tool_name,
                        "args": tool_input,
                        "status": "error" if is_error else "ok",
                    }
                )

        # Append tool results as individual tool messages (OpenAI format)
        tool_result_msgs = make_tool_results(tool_calls, results)
        for msg in tool_result_msgs:
            msg["_round"] = session_state.current_round
            messages.append(msg)

    # Safety: max rounds exceeded
    logger.warning("loop.max_rounds", max_rounds=max_rounds)
    await on_event(
        {
            "type": "text",
            "content": "I've reached the maximum number of processing rounds. Please send a new message to continue.",
            "metadata": {"max_rounds_exceeded": True},
        }
    )
    if trace_recorder:
        await trace_recorder.flush()


def _get_tool_schemas(dispatch_map: dict[str, "ToolEntry"]) -> list[dict[str, Any]]:
    """Extract tool schemas from the dispatch map."""
    return [entry.schema for entry in dispatch_map.values()]
