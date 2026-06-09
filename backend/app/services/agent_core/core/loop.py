from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from litellm import acompletion
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.agent_core import AgentActionStatus, AgentTurnStatus
from app.repositories.agent_core_repo import (
    AgentActionRepository,
    AgentSessionRepository,
    AgentTurnRepository,
)
from app.services.agent_core.context import AgentContextAssembler
from app.services.agent_core.core.budget import IterationBudget
from app.services.agent_core.core.interrupt import is_interrupt_requested
from app.services.agent_core.core.types import LoopResult
from app.services.agent_core.events import AgentEventType
from app.services.agent_core.ledger import AgentEventLedger
from app.services.agent_core.tools import AgentToolContext, build_default_tool_registry
from app.services.agent_core.tools.executor import AgentToolExecutor, ToolExecutionResult
from app.services.agent_core.tools.toolsets import (
    decode_provider_tool_name,
    provider_tool_specs,
)
from app.services.agent_core.transcript import AgentTranscriptStore, text_part, tool_calls_part
from app.services.llm.providers import litellm_model_name


class AgentLoopController:
    def __init__(self, session: AsyncSession):
        self.db = session
        self.sessions = AgentSessionRepository(session)
        self.turns = AgentTurnRepository(session)
        self.actions = AgentActionRepository(session)
        self.ledger = AgentEventLedger(session)
        self.context = AgentContextAssembler(session)
        self.transcript = AgentTranscriptStore(session)
        self.registry = build_default_tool_registry()
        self.executor = AgentToolExecutor(session, self.registry)

    async def run_turn(
        self,
        *,
        turn_id: str,
        provider: str,
        model: str,
        request_args: dict[str, Any],
        supports_tools: bool = True,
    ) -> LoopResult:
        turn = await self.turns.get(turn_id)
        if turn is None:
            return LoopResult(
                termination_reason="model_failed",
                final_text=None,
                iteration_count=0,
                error_code="turn_not_found",
                error_message="Agent turn could not be loaded.",
            )
        agent_session = await self.sessions.get(str(turn.session_id))
        if agent_session is None:
            return LoopResult(
                termination_reason="model_failed",
                final_text=None,
                iteration_count=0,
                error_code="session_not_found",
                error_message="Agent session could not be loaded.",
            )

        budget = IterationBudget(max_iterations=_max_iterations())
        visible_tools = (
            self.executor.exposure.exposed_specs(
                policy=agent_session.toolset_policy,
                role="orchestrator",
            )
            if supports_tools
            else []
        )
        tool_payload = provider_tool_specs(visible_tools) if supports_tools else []
        token_usage: dict[str, Any] | None = None

        while budget.consume():
            turn = await self.turns.get(turn_id)
            if turn is None or is_interrupt_requested(turn):
                return LoopResult(
                    termination_reason="interrupted",
                    final_text=None,
                    iteration_count=budget.used_iterations,
                )

            try:
                completion_kwargs = {
                    "model": litellm_model_name(provider, model),
                    "messages": await self.context.provider_messages(
                        agent_session=agent_session,
                        turn=turn,
                    ),
                    "max_tokens": settings.agent_max_tokens,
                    **request_args,
                }
                if supports_tools and tool_payload:
                    completion_kwargs["tools"] = tool_payload
                response = await acompletion(**completion_kwargs)
            except Exception as exc:
                return LoopResult(
                    termination_reason="model_failed",
                    final_text=None,
                    iteration_count=budget.used_iterations,
                    error_code="model_request_failed",
                    error_message=str(exc),
                )

            token_usage = _merge_usage(token_usage, _extract_token_usage(response))
            tool_calls = _extract_tool_calls(response)
            if tool_calls:
                await self._append_assistant_tool_calls(
                    agent_session=agent_session,
                    turn=turn,
                    provider=provider,
                    model=model,
                    tool_calls=tool_calls,
                )
                waiting = await self._execute_tool_calls(
                    agent_session=agent_session,
                    turn=turn,
                    tool_calls=tool_calls,
                )
                if waiting:
                    return LoopResult(
                        termination_reason="waiting_approval",
                        final_text=None,
                        iteration_count=budget.used_iterations,
                        token_usage=token_usage,
                    )
                continue

            final_text = _extract_response_text(response)
            if not final_text:
                return LoopResult(
                    termination_reason="model_failed",
                    final_text=None,
                    iteration_count=budget.used_iterations,
                    token_usage=token_usage,
                    error_code="empty_model_response",
                    error_message="The selected model completed without returning visible text.",
                )
            await self.transcript.append_parts(
                session_id=str(agent_session.id),
                turn_id=str(turn.id),
                role="assistant",
                parts=[text_part(final_text)],
                metadata={"provider": provider, "model": model},
            )
            await self.ledger.append(
                session_id=str(agent_session.id),
                turn_id=str(turn.id),
                type=AgentEventType.ASSISTANT_TEXT_COMPLETED,
                payload={"text": final_text},
            )
            return LoopResult(
                termination_reason="assistant_final",
                final_text=final_text,
                iteration_count=budget.used_iterations,
                token_usage=token_usage,
            )

        return LoopResult(
            termination_reason="budget_exhausted",
            final_text=None,
            iteration_count=budget.used_iterations,
            token_usage=token_usage,
            error_code="iteration_budget_exhausted",
            error_message="Agent turn exhausted its iteration budget.",
        )

    async def _execute_tool_calls(self, *, agent_session, turn, tool_calls: list[dict]) -> bool:
        waiting = False
        for tool_call in tool_calls:
            tool_name = decode_provider_tool_name(tool_call["name"])
            result = await self.executor.execute(
                tool_name=tool_name,
                input=tool_call["arguments"],
                context=AgentToolContext(
                    db=self.db,
                    workspace_id=str(turn.workspace_id),
                    user_id=turn.user_id,
                    session_id=str(agent_session.id),
                    turn_id=str(turn.id),
                ),
                toolset_policy=agent_session.toolset_policy,
                permission_mode=agent_session.permission_mode,
                automation_mode=agent_session.automation_mode,
                tool_call_id=tool_call.get("id"),
            )
            if result.requires_resume:
                waiting = True
                continue
            await self._append_tool_result(
                agent_session=agent_session,
                turn=turn,
                tool_name=tool_name,
                tool_call_id=tool_call.get("id"),
                result=result,
            )
        return waiting

    async def resume_turn_from_action(
        self,
        *,
        action_id: str,
        provider: str,
        model: str,
        request_args: dict[str, Any],
        supports_tools: bool = True,
    ) -> LoopResult:
        action = await self.actions.get(action_id)
        if action is None:
            return LoopResult(
                termination_reason="model_failed",
                final_text=None,
                iteration_count=0,
                error_code="action_not_found",
                error_message="Agent action could not be loaded for resume.",
            )
        turn = await self.turns.get(str(action.turn_id))
        if turn is None:
            return LoopResult(
                termination_reason="model_failed",
                final_text=None,
                iteration_count=0,
                error_code="turn_not_found",
                error_message="Agent turn could not be loaded for resume.",
            )
        agent_session = await self.sessions.get(str(action.session_id))
        if agent_session is None:
            return LoopResult(
                termination_reason="model_failed",
                final_text=None,
                iteration_count=0,
                error_code="session_not_found",
                error_message="Agent session could not be loaded for resume.",
            )

        if action.status == AgentActionStatus.REJECTED:
            result = ToolExecutionResult(
                action_id=str(action.id),
                status=action.status,
                error={"type": "UserRejected", "message": "The user rejected this tool call."},
            )
        else:
            result = await self.executor.resume_action(
                action_id=action_id,
                context=AgentToolContext(
                    db=self.db,
                    workspace_id=str(turn.workspace_id),
                    user_id=turn.user_id,
                    session_id=str(agent_session.id),
                    turn_id=str(turn.id),
                ),
            )
        await self._append_tool_result(
            agent_session=agent_session,
            turn=turn,
            tool_name=action.name,
            tool_call_id=action.tool_call_id,
            result=result,
        )
        if result.status not in {"completed", AgentActionStatus.REJECTED}:
            return LoopResult(
                termination_reason="model_failed",
                final_text=None,
                iteration_count=0,
                error_code="tool_resume_failed",
                error_message=f"Approved tool action finished with status: {result.status}",
            )
        return await self.run_turn(
            turn_id=str(turn.id),
            provider=provider,
            model=model,
            supports_tools=supports_tools,
            request_args=request_args,
        )

    async def _append_assistant_tool_calls(
        self,
        *,
        agent_session,
        turn,
        provider: str,
        model: str,
        tool_calls: list[dict[str, Any]],
    ) -> None:
        await self.transcript.append_parts(
            session_id=str(agent_session.id),
            turn_id=str(turn.id),
            role="assistant",
            parts=[tool_calls_part([_provider_tool_call(call) for call in tool_calls])],
            metadata={"provider": provider, "model": model, "kind": "tool_calls"},
        )

    async def _append_tool_result(
        self,
        *,
        agent_session,
        turn,
        tool_name: str,
        tool_call_id: str | None,
        result,
    ) -> None:
        await self.transcript.append_parts(
            session_id=str(agent_session.id),
            turn_id=str(turn.id),
            role="tool",
            parts=[
                text_part(
                    json.dumps(
                        {
                            "tool": tool_name,
                            "status": result.status,
                            "result": result.result,
                            "error": result.error,
                        },
                        separators=(",", ":"),
                        default=str,
                    )
                )
            ],
            metadata={"tool_call_id": tool_call_id, "tool": tool_name},
        )

    async def complete_turn_from_result(self, *, turn, result: LoopResult):
        if result.termination_reason == "assistant_final":
            status = AgentTurnStatus.COMPLETED
            event_type = AgentEventType.TURN_COMPLETED
        elif result.termination_reason == "waiting_approval":
            status = AgentTurnStatus.WAITING_APPROVAL
            event_type = None
        elif result.termination_reason == "interrupted":
            status = AgentTurnStatus.CANCELLED
            event_type = AgentEventType.TURN_INTERRUPTED
        else:
            status = AgentTurnStatus.FAILED
            event_type = AgentEventType.TURN_FAILED

        updated = await self.turns.update_all(
            turn,
            status=status,
            final_text=result.final_text,
            token_usage=result.token_usage,
            termination_reason=result.termination_reason,
            iteration_count=result.iteration_count,
            budget_snapshot={
                "used_iterations": result.iteration_count,
                "max_iterations": _max_iterations(),
            },
            loop_state={"termination_reason": result.termination_reason},
            error_code=result.error_code,
            error_message=result.error_message,
            completed_at=datetime.now(timezone.utc)
            if status in {AgentTurnStatus.COMPLETED, AgentTurnStatus.FAILED, AgentTurnStatus.CANCELLED}
            else None,
        )
        if result.termination_reason == "assistant_final":
            payload = {"final_text": result.final_text}
        elif result.termination_reason == "interrupted":
            payload = {"termination_reason": result.termination_reason}
        elif result.error_code or result.error_message:
            payload = {
                "error_message": result.error_message,
                "error_code": result.error_code,
            }
        else:
            payload = {"termination_reason": result.termination_reason}
        if event_type is not None:
            await self.ledger.append(
                session_id=str(updated.session_id),
                turn_id=str(updated.id),
                type=event_type,
                payload=payload,
            )
        return updated


def _extract_response_text(response: Any) -> str:
    choices = getattr(response, "choices", None) or []
    if not choices:
        return ""
    message = getattr(choices[0], "message", None)
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            text = item.get("text") if isinstance(item, dict) else getattr(item, "text", None)
            if isinstance(text, str) and text.strip():
                parts.append(text.strip())
        return "\n".join(parts).strip()
    return ""


def _extract_tool_calls(response: Any) -> list[dict[str, Any]]:
    choices = getattr(response, "choices", None) or []
    if not choices:
        return []
    message = getattr(choices[0], "message", None)
    raw_tool_calls = getattr(message, "tool_calls", None) or []
    calls: list[dict[str, Any]] = []
    for raw in raw_tool_calls:
        function = getattr(raw, "function", None)
        name = getattr(function, "name", None)
        arguments = getattr(function, "arguments", None)
        call_id = getattr(raw, "id", None)
        if isinstance(raw, dict):
            function = raw.get("function") or {}
            name = function.get("name")
            arguments = function.get("arguments")
            call_id = raw.get("id")
        if not isinstance(name, str):
            continue
        if isinstance(arguments, str):
            try:
                parsed_arguments = json.loads(arguments or "{}")
            except json.JSONDecodeError:
                parsed_arguments = {}
        elif isinstance(arguments, dict):
            parsed_arguments = arguments
        else:
            parsed_arguments = {}
        calls.append(
            {
                "id": call_id or f"tool_call_{len(calls) + 1}",
                "name": name,
                "arguments": parsed_arguments,
            }
        )
    return calls


def _provider_tool_call(tool_call: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(tool_call["id"]),
        "type": "function",
        "function": {
            "name": tool_call["name"],
            "arguments": json.dumps(
                tool_call["arguments"],
                separators=(",", ":"),
                default=str,
            ),
        },
    }


def _extract_token_usage(response: Any) -> dict[str, Any] | None:
    usage = getattr(response, "usage", None)
    if usage is None:
        return None
    if hasattr(usage, "model_dump"):
        return usage.model_dump()
    if isinstance(usage, dict):
        return usage
    return {key: value for key, value in vars(usage).items() if not key.startswith("_")}


def _merge_usage(
    current: dict[str, Any] | None,
    next_usage: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not next_usage:
        return current
    if not current:
        return dict(next_usage)
    merged = dict(current)
    for key, value in next_usage.items():
        if isinstance(value, int) and isinstance(merged.get(key), int):
            merged[key] += value
        else:
            merged[key] = value
    return merged


def _max_iterations() -> int:
    return int(getattr(settings, "agent_max_iterations", None) or settings.agent_max_rounds or 6)
