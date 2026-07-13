from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import NAMESPACE_URL, uuid5

import app.database as app_database
from litellm import acompletion
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings
from app.models.agent_core import AgentActionStatus, AgentTurnStatus
from app.repositories.agent_core_repo import (
    AgentActionRepository,
    AgentSessionRepository,
    AgentTurnRepository,
)
from app.services.agent_core.context import AgentContextAssembler
from app.services.agent_core.core.budget import IterationBudget
from app.services.agent_core.core.guardrails import (
    next_repeat_count,
    no_progress_detected,
)
from app.services.agent_core.core.interrupt import is_interrupt_requested
from app.services.agent_core.core.retry import RetryPolicy, run_with_retry
from app.services.agent_core.core.runtime_strategy import (
    RuntimeCapabilities,
    RuntimeStrategy,
)
from app.services.agent_core.core.stream_adapter import (
    StreamCompletionResult,
    StreamToolCall,
    extract_reasoning_delta,
    extract_text_delta,
    extract_tool_call_deltas,
    extract_response_thinking,
)
from app.services.agent_core.core.types import LoopResult
from app.services.agent_core.events import AgentEventType
from app.services.agent_core.execution_target import execution_target_from_session
from app.services.agent_core.ledger import AgentEventLedger
from app.services.agent_core.metrics import agent_metrics
from app.services.agent_core.observability import truncate_log_value
from app.services.agent_core.tools import AgentToolContext, build_default_tool_registry
from app.services.agent_core.tools.approval import action_matches_pending_observation
from app.services.agent_core.tools.executor import (
    AgentToolExecutor,
    ToolExecutionResult,
)
from app.services.agent_core.tools.toolsets import (
    decode_provider_tool_name,
    provider_tool_specs,
)
from app.services.agent_core.transcript import (
    AgentTranscriptStore,
    text_part,
    tool_calls_part,
)
from app.services.llm.provider_templates import litellm_model_name
from app.utils.exceptions import PermissionDeniedError
from app.utils.logging import get_logger


logger = get_logger(__name__)


class _ExecutionTargetChanged(Exception):
    pass


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
        capabilities: RuntimeCapabilities = RuntimeCapabilities(),
        strategy: RuntimeStrategy = RuntimeStrategy(),
        max_tokens: int | None = None,
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

        persisted_budget = dict(getattr(turn, "budget_snapshot", None) or {})
        persisted_max_iterations = int(persisted_budget.get("max_iterations") or 0)
        budget = IterationBudget(
            max_iterations=persisted_max_iterations or _max_iterations(),
            used_iterations=int(getattr(turn, "iteration_count", 0) or 0),
        )
        tools_enabled = capabilities.supports_tools and strategy.allow_tools
        token_usage = dict(getattr(turn, "token_usage", None) or {}) or None
        progress = _progress_state(getattr(turn, "loop_state", None))
        previous_tool_call_signatures = progress["previous_tool_calls"]
        previous_tool_result_signatures = progress["previous_tool_results"]
        repeated_tool_call_count = progress["repeat_count"]
        empty_response_retries_remaining = 1

        while budget.consume():
            turn = await self.turns.get(turn_id)
            if turn is None:
                return LoopResult(
                    termination_reason="model_failed",
                    final_text=None,
                    iteration_count=budget.used_iterations,
                    error_code="turn_not_found",
                    error_message="Agent turn could not be loaded.",
                )
            turn = await self._checkpoint_loop_state(
                turn,
                budget=budget,
                token_usage=token_usage,
                progress=_progress_payload(
                    previous_tool_call_signatures,
                    previous_tool_result_signatures,
                    repeated_tool_call_count,
                ),
            )
            if turn.status == AgentTurnStatus.CANCELLED or is_interrupt_requested(turn):
                return LoopResult(
                    termination_reason=_cancellation_reason(turn),
                    final_text=None,
                    iteration_count=budget.used_iterations,
                    token_usage=token_usage,
                )
            turn = await self._renew_turn_lease(turn)

            agent_session = await self.sessions.get_fresh(str(turn.session_id))
            if agent_session is None:
                return LoopResult(
                    termination_reason="model_failed",
                    final_text=None,
                    iteration_count=budget.used_iterations,
                    error_code="session_not_found",
                    error_message="Agent session could not be loaded.",
                    token_usage=token_usage,
                )
            role = _tool_role(agent_session)
            execution_target = execution_target_from_session(agent_session)
            visible_tools = (
                self.executor.exposure.exposed_specs(
                    policy=agent_session.toolset_policy,
                    role=role,
                    execution_target=execution_target,
                )
                if tools_enabled
                else []
            )
            tool_payload = provider_tool_specs(visible_tools) if tools_enabled else []

            completion_kwargs = {
                "model": litellm_model_name(provider, model),
                "messages": await self.context.provider_messages(
                    agent_session=agent_session,
                    turn=turn,
                ),
                "max_tokens": max_tokens or settings.agent_max_tokens,
                **request_args,
            }
            if tools_enabled and tool_payload:
                completion_kwargs["tools"] = tool_payload
            if capabilities.supports_streaming and strategy.use_streaming:
                completion_kwargs["stream"] = True

            try:
                response = await self._call_model_with_retry(
                    turn=turn,
                    completion_kwargs=completion_kwargs,
                    iteration_count=budget.used_iterations,
                )
            except asyncio.CancelledError:
                return LoopResult(
                    termination_reason=_cancellation_reason(turn),
                    final_text=None,
                    iteration_count=budget.used_iterations,
                    token_usage=token_usage,
                )
            except Exception as exc:
                return LoopResult(
                    termination_reason="model_failed",
                    final_text=None,
                    iteration_count=budget.used_iterations,
                    error_code="model_request_failed",
                    error_message=str(exc),
                    token_usage=token_usage,
                )

            turn = await self._renew_turn_lease(turn)
            message_id = f"assistant:{turn.id}:{budget.used_iterations}"
            try:
                if completion_kwargs.get("stream"):
                    streamed = await self._consume_stream_response(
                        agent_session=agent_session,
                        turn=turn,
                        response=response,
                        message_id=message_id,
                        allow_thinking=strategy.allow_thinking,
                        expected_execution_target=execution_target,
                    )
                else:
                    fresh_session = await self.sessions.get_fresh(
                        str(agent_session.id)
                    )
                    if fresh_session is None:
                        return LoopResult(
                            termination_reason="model_failed",
                            final_text=None,
                            iteration_count=budget.used_iterations,
                            error_code="session_not_found",
                            error_message="Agent session could not be loaded.",
                            token_usage=token_usage,
                        )
                    if (
                        execution_target_from_session(fresh_session)
                        != execution_target
                    ):
                        continue
                    agent_session = fresh_session
                    streamed = await self._consume_response(
                        agent_session=agent_session,
                        turn=turn,
                        response=response,
                        message_id=message_id,
                        allow_thinking=strategy.allow_thinking,
                    )
            except _ExecutionTargetChanged:
                continue

            token_usage = _merge_usage(token_usage, streamed.token_usage)
            turn = await self._checkpoint_loop_state(
                turn,
                budget=budget,
                token_usage=token_usage,
                progress=_progress_payload(
                    previous_tool_call_signatures,
                    previous_tool_result_signatures,
                    repeated_tool_call_count,
                ),
            )
            if turn.status == AgentTurnStatus.CANCELLED or is_interrupt_requested(turn):
                return LoopResult(
                    termination_reason=_cancellation_reason(turn),
                    final_text=None,
                    iteration_count=budget.used_iterations,
                    token_usage=token_usage,
                )
            tool_calls = [_tool_call_dict(item) for item in streamed.tool_calls]
            if tool_calls:
                tool_call_signatures = [
                    _tool_call_signature(tool_call) for tool_call in tool_calls
                ]
                await self._append_assistant_tool_calls(
                    agent_session=agent_session,
                    turn=turn,
                    provider=provider,
                    model=model,
                    tool_calls=tool_calls,
                    text=streamed.text or None,
                )
                try:
                    (
                        waiting,
                        tool_result_signatures,
                        deferred_tool_calls,
                    ) = await self._execute_tool_calls(
                        agent_session=agent_session,
                        turn=turn,
                        tool_calls=tool_calls,
                    )
                except asyncio.CancelledError:
                    return LoopResult(
                        termination_reason=_cancellation_reason(turn),
                        final_text=None,
                        iteration_count=budget.used_iterations,
                        token_usage=token_usage,
                    )
                except PermissionDeniedError as exc:
                    return LoopResult(
                        termination_reason="tool_failed",
                        final_text=None,
                        iteration_count=budget.used_iterations,
                        token_usage=token_usage,
                        error_code=_tool_permission_error_code(exc),
                        error_message=str(exc),
                    )
                if waiting:
                    turn = await self._checkpoint_loop_state(
                        turn,
                        budget=budget,
                        token_usage=token_usage,
                        progress=_pending_progress_payload(
                            previous_tool_calls=previous_tool_call_signatures,
                            previous_tool_results=previous_tool_result_signatures,
                            repeat_count=repeated_tool_call_count,
                            pending_tool_calls=tool_call_signatures,
                            pending_tool_results=tool_result_signatures,
                            deferred_tool_calls=deferred_tool_calls,
                        ),
                    )
                    return LoopResult(
                        termination_reason="waiting_approval",
                        final_text=None,
                        iteration_count=budget.used_iterations,
                        token_usage=token_usage,
                    )
                repeated_tool_call_count = next_repeat_count(
                    previous_tool_call_signatures,
                    tool_call_signatures,
                    previous_tool_results=previous_tool_result_signatures,
                    next_tool_results=tool_result_signatures,
                    repeat_count=repeated_tool_call_count,
                )
                turn = await self._checkpoint_loop_state(
                    turn,
                    budget=budget,
                    token_usage=token_usage,
                    progress=_progress_payload(
                        tool_call_signatures,
                        tool_result_signatures,
                        repeated_tool_call_count,
                    ),
                )
                if no_progress_detected(
                    previous_tool_call_signatures,
                    tool_call_signatures,
                    previous_tool_results=previous_tool_result_signatures,
                    next_tool_results=tool_result_signatures,
                    repeat_count=repeated_tool_call_count,
                ):
                    return LoopResult(
                        termination_reason="no_progress",
                        final_text=None,
                        iteration_count=budget.used_iterations,
                        token_usage=token_usage,
                        error_code="no_progress_detected",
                        error_message="Agent repeated the same tool call without making progress.",
                    )
                previous_tool_call_signatures = tool_call_signatures
                previous_tool_result_signatures = tool_result_signatures
                continue

            previous_tool_call_signatures = []
            previous_tool_result_signatures = []
            repeated_tool_call_count = 0
            turn = await self._checkpoint_loop_state(
                turn,
                budget=budget,
                token_usage=token_usage,
                progress=_progress_payload([], [], 0),
            )
            final_text = streamed.text
            if not final_text:
                if empty_response_retries_remaining > 0:
                    empty_response_retries_remaining -= 1
                    await self.ledger.append(
                        session_id=str(agent_session.id),
                        turn_id=str(turn.id),
                        type=AgentEventType.MODEL_RETRYING,
                        payload={
                            "reason": "empty_model_response",
                            "next_attempt": budget.used_iterations + 1,
                        },
                    )
                    continue
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

    async def _execute_tool_calls(
        self,
        *,
        agent_session,
        turn,
        tool_calls: list[dict],
    ) -> tuple[bool, list[str], list[dict[str, str]]]:
        result_signatures: list[str] = []
        deferred_tool_calls: list[dict[str, str]] = []
        index = 0
        while index < len(tool_calls):
            turn = await self._renew_turn_lease(turn)
            await self.db.refresh(turn)
            if turn.status == AgentTurnStatus.CANCELLED or is_interrupt_requested(turn):
                await self._append_closed_tool_calls(
                    agent_session=agent_session,
                    turn=turn,
                    tool_calls=tool_calls[index:],
                    status="cancelled",
                    error={
                        "type": "InterruptedError"
                        if is_interrupt_requested(turn)
                        else "CancelledError",
                        "message": "Tool call was cancelled before execution.",
                    },
                )
                raise asyncio.CancelledError
            tool_call = tool_calls[index]
            tool_name = decode_provider_tool_name(tool_call["name"])
            if self._is_concurrent_read_only_tool(tool_name):
                batch: list[tuple[dict[str, Any], str]] = []
                while index < len(tool_calls):
                    candidate = tool_calls[index]
                    candidate_name = decode_provider_tool_name(candidate["name"])
                    if not self._is_concurrent_read_only_tool(candidate_name):
                        break
                    batch.append((candidate, candidate_name))
                    index += 1
                results = await asyncio.gather(
                    *[
                        self._execute_tool_call_isolated(
                            agent_session=agent_session,
                            turn=turn,
                            tool_call=item,
                            tool_name=name,
                        )
                        for item, name in batch
                    ],
                    return_exceptions=True,
                )
                first_error: BaseException | None = None
                for (item, name), result in zip(batch, results, strict=False):
                    if isinstance(result, BaseException):
                        failure = _failed_tool_result(result)
                        result_signatures.append(_tool_result_signature(name, failure))
                        await self._append_tool_result(
                            agent_session=agent_session,
                            turn=turn,
                            tool_name=name,
                            tool_call_id=item.get("id"),
                            result=failure,
                        )
                        first_error = first_error or result
                        continue
                    if result.requires_resume:
                        result_signatures.append(
                            _pending_tool_result_signature(name, item.get("id"))
                        )
                        deferred_signatures, deferred_tool_calls = (
                            self._deferred_tool_results(tool_calls[index:])
                        )
                        result_signatures.extend(deferred_signatures)
                        return True, result_signatures, deferred_tool_calls
                    result_signatures.append(_tool_result_signature(name, result))
                    await self._append_tool_result(
                        agent_session=agent_session,
                        turn=turn,
                        tool_name=name,
                        tool_call_id=item.get("id"),
                        result=result,
                    )
                if first_error is not None:
                    await self._append_closed_tool_calls(
                        agent_session=agent_session,
                        turn=turn,
                        tool_calls=tool_calls[index:],
                        status="deferred",
                        error={
                            "type": "DeferredToolCall",
                            "message": "Tool call was deferred after an earlier tool failed.",
                        },
                    )
                    raise first_error
                continue

            try:
                result = await self.executor.execute(
                    tool_name=tool_name,
                    input=tool_call["arguments"],
                    context=AgentToolContext(
                        db=self.db,
                        workspace_id=str(turn.workspace_id),
                        user_id=turn.user_id,
                        session_id=str(agent_session.id),
                        turn_id=str(turn.id),
                        turn_claimed_at=turn.claimed_at,
                    ),
                    toolset_policy=agent_session.toolset_policy,
                    permission_mode=agent_session.permission_mode,
                    automation_mode=agent_session.automation_mode,
                    tool_call_id=tool_call.get("id"),
                    role=_tool_role(agent_session),
                    execution_target=execution_target_from_session(agent_session),
                    expected_execution_target=execution_target_from_session(
                        agent_session
                    ),
                )
            except BaseException as exc:
                failure = _failed_tool_result(exc)
                await self._append_tool_result(
                    agent_session=agent_session,
                    turn=turn,
                    tool_name=tool_name,
                    tool_call_id=tool_call.get("id"),
                    result=failure,
                )
                await self._append_closed_tool_calls(
                    agent_session=agent_session,
                    turn=turn,
                    tool_calls=tool_calls[index + 1 :],
                    status="deferred",
                    error={
                        "type": "DeferredToolCall",
                        "message": "Tool call was deferred after an earlier tool failed.",
                    },
                )
                raise
            if result.requires_resume:
                result_signatures.append(
                    _pending_tool_result_signature(tool_name, tool_call.get("id"))
                )
                deferred_signatures, deferred_tool_calls = self._deferred_tool_results(
                    tool_calls[index + 1 :]
                )
                result_signatures.extend(deferred_signatures)
                return True, result_signatures, deferred_tool_calls
            result_signatures.append(_tool_result_signature(tool_name, result))
            await self._append_tool_result(
                agent_session=agent_session,
                turn=turn,
                tool_name=tool_name,
                tool_call_id=tool_call.get("id"),
                result=result,
            )
            index += 1
        return False, result_signatures, deferred_tool_calls

    async def resume_turn_from_action(
        self,
        *,
        action_id: str,
        provider: str,
        model: str,
        request_args: dict[str, Any],
        capabilities: RuntimeCapabilities = RuntimeCapabilities(),
        strategy: RuntimeStrategy = RuntimeStrategy(),
        max_tokens: int | None = None,
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
        persisted_iteration_count = int(getattr(turn, "iteration_count", 0) or 0)
        persisted_token_usage = dict(getattr(turn, "token_usage", None) or {}) or None
        agent_session = await self.sessions.get(str(action.session_id))
        if agent_session is None:
            return LoopResult(
                termination_reason="model_failed",
                final_text=None,
                iteration_count=persisted_iteration_count,
                token_usage=persisted_token_usage,
                error_code="session_not_found",
                error_message="Agent session could not be loaded for resume.",
            )
        if not action_matches_pending_observation(turn, action):
            return LoopResult(
                termination_reason="action_in_progress",
                final_text=None,
                iteration_count=persisted_iteration_count,
                token_usage=persisted_token_usage,
                error_code="action_not_pending",
                error_message="Agent action is not the turn's pending observation.",
            )

        if action.status == AgentActionStatus.RUNNING:
            return LoopResult(
                termination_reason="action_in_progress",
                final_text=None,
                iteration_count=persisted_iteration_count,
                token_usage=persisted_token_usage,
            )
        if action.status in {
            AgentActionStatus.COMPLETED,
            AgentActionStatus.FAILED,
            AgentActionStatus.CANCELLED,
        }:
            result = ToolExecutionResult(
                action_id=str(action.id),
                status=action.status,
                result=action.result,
                error=action.error,
            )
        elif action.status == AgentActionStatus.REJECTED:
            result = ToolExecutionResult(
                action_id=str(action.id),
                status=action.status,
                error={
                    "type": "UserRejected",
                    "message": "The user rejected this tool call.",
                },
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
                    turn_claimed_at=turn.claimed_at,
                ),
            )
        if (result.error or {}).get("type") == "ActionAlreadyClaimed":
            return LoopResult(
                termination_reason="action_in_progress",
                final_text=None,
                iteration_count=persisted_iteration_count,
                token_usage=persisted_token_usage,
            )
        pending_observation = _pending_observation(getattr(turn, "loop_state", None))
        await self._append_tool_result(
            agent_session=agent_session,
            turn=turn,
            tool_name=action.name,
            tool_call_id=action.tool_call_id,
            result=result,
        )
        if pending_observation is not None:
            for deferred_call in pending_observation["deferred_tool_calls"]:
                deferred_name = deferred_call["tool_name"]
                await self._append_tool_result(
                    agent_session=agent_session,
                    turn=turn,
                    tool_name=deferred_name,
                    tool_call_id=deferred_call["tool_call_id"],
                    result=_deferred_tool_result(deferred_name),
                )
        previous_progress = _progress_state(getattr(turn, "loop_state", None))
        if pending_observation is not None:
            completed_tool_calls = pending_observation["tool_calls"]
            completed_tool_results = pending_observation["tool_results"]
            sentinel = _pending_tool_result_signature(action.name, action.tool_call_id)
            try:
                pending_index = completed_tool_results.index(sentinel)
            except ValueError:
                pending_index = -1
            if pending_index >= 0:
                completed_tool_results[pending_index] = _tool_result_signature(
                    action.name,
                    result,
                )
                repeat_count = next_repeat_count(
                    previous_progress["previous_tool_calls"],
                    completed_tool_calls,
                    previous_tool_results=previous_progress["previous_tool_results"],
                    next_tool_results=completed_tool_results,
                    repeat_count=previous_progress["repeat_count"],
                )
                loop_state = dict(getattr(turn, "loop_state", None) or {})
                loop_state["progress"] = _progress_payload(
                    completed_tool_calls,
                    completed_tool_results,
                    repeat_count,
                )
                turn = await self._update_claimed_turn(turn, loop_state=loop_state)
                if result.status in {
                    "completed",
                    AgentActionStatus.REJECTED,
                } and no_progress_detected(
                    previous_progress["previous_tool_calls"],
                    completed_tool_calls,
                    previous_tool_results=previous_progress["previous_tool_results"],
                    next_tool_results=completed_tool_results,
                    repeat_count=repeat_count,
                ):
                    return LoopResult(
                        termination_reason="no_progress",
                        final_text=None,
                        iteration_count=persisted_iteration_count,
                        token_usage=persisted_token_usage,
                        error_code="no_progress_detected",
                        error_message=(
                            "Agent repeated the same tool call without making progress."
                        ),
                    )
        if result.status not in {"completed", AgentActionStatus.REJECTED}:
            return LoopResult(
                termination_reason="model_failed",
                final_text=None,
                iteration_count=persisted_iteration_count,
                token_usage=persisted_token_usage,
                error_code="tool_resume_failed",
                error_message=f"Approved tool action finished with status: {result.status}",
            )
        return await self.run_turn(
            turn_id=str(turn.id),
            provider=provider,
            model=model,
            capabilities=capabilities,
            strategy=strategy,
            request_args=request_args,
            max_tokens=max_tokens,
        )

    async def _append_assistant_tool_calls(
        self,
        *,
        agent_session,
        turn,
        provider: str,
        model: str,
        tool_calls: list[dict[str, Any]],
        text: str | None = None,
    ) -> None:
        parts: list[dict[str, Any]] = []
        if text:
            parts.append(text_part(text))
        parts.append(
            tool_calls_part([_provider_tool_call(call) for call in tool_calls])
        )
        await self.transcript.append_parts(
            session_id=str(agent_session.id),
            turn_id=str(turn.id),
            role="assistant",
            parts=parts,
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
        await self.transcript.append_tool_result_once(
            session_id=str(agent_session.id),
            turn_id=str(turn.id),
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            status=result.status,
            result=result.result,
            error=result.error,
        )

    async def _append_closed_tool_calls(
        self,
        *,
        agent_session,
        turn,
        tool_calls: list[dict[str, Any]],
        status: str,
        error: dict[str, Any],
    ) -> None:
        for tool_call in tool_calls:
            tool_name = decode_provider_tool_name(tool_call["name"])
            await self._append_tool_result(
                agent_session=agent_session,
                turn=turn,
                tool_name=tool_name,
                tool_call_id=tool_call.get("id"),
                result=ToolExecutionResult(
                    action_id="",
                    status=status,
                    error=error,
                ),
            )

    def _deferred_tool_results(
        self,
        tool_calls: list[dict[str, Any]],
    ) -> tuple[list[str], list[dict[str, str]]]:
        signatures: list[str] = []
        descriptors: list[dict[str, str]] = []
        for tool_call in tool_calls:
            tool_name = decode_provider_tool_name(tool_call["name"])
            result = _deferred_tool_result(tool_name)
            signatures.append(_tool_result_signature(tool_name, result))
            descriptors.append(
                {
                    "tool_name": tool_name,
                    "tool_call_id": str(tool_call.get("id") or ""),
                }
            )
        return signatures, descriptors

    async def _execute_tool_call_isolated(
        self, *, agent_session, turn, tool_call: dict[str, Any], tool_name: str
    ):
        bind = self.db.bind
        session_factory = (
            async_sessionmaker(bind=bind, expire_on_commit=False)
            if bind is not None
            else app_database.async_session_maker
        )
        async with session_factory() as session:
            current_turn = await AgentTurnRepository(session).get(str(turn.id))
            if current_turn is None:
                return ToolExecutionResult(
                    action_id="",
                    status="cancelled",
                    error={"type": "CancelledError", "message": "Turn no longer exists."},
                )
            await session.refresh(current_turn)
            if current_turn.status == AgentTurnStatus.CANCELLED or is_interrupt_requested(
                current_turn
            ):
                return ToolExecutionResult(
                    action_id="",
                    status="cancelled",
                    error={
                        "type": "InterruptedError"
                        if is_interrupt_requested(current_turn)
                        else "CancelledError",
                        "message": "Tool call was cancelled before execution.",
                    },
                )
            executor = AgentToolExecutor(session, build_default_tool_registry())
            return await executor.execute(
                tool_name=tool_name,
                input=tool_call["arguments"],
                context=AgentToolContext(
                    db=session,
                    workspace_id=str(turn.workspace_id),
                    user_id=turn.user_id,
                    session_id=str(agent_session.id),
                    turn_id=str(turn.id),
                    turn_claimed_at=current_turn.claimed_at,
                ),
                toolset_policy=agent_session.toolset_policy,
                permission_mode=agent_session.permission_mode,
                automation_mode=agent_session.automation_mode,
                tool_call_id=tool_call.get("id"),
                role=_tool_role(agent_session),
                execution_target=execution_target_from_session(agent_session),
                expected_execution_target=execution_target_from_session(agent_session),
            )

    def _is_concurrent_read_only_tool(self, tool_name: str) -> bool:
        tool = self.registry.get(tool_name)
        spec = tool.spec
        return (
            spec.risk_level == "read"
            and not spec.write_scope
            and spec.interaction is None
            and not callable(getattr(tool, "assess_risk", None))
        )

    async def _checkpoint_loop_state(
        self,
        turn,
        *,
        budget: IterationBudget,
        token_usage: dict[str, Any] | None,
        progress: dict[str, Any],
    ):
        loop_state = dict(getattr(turn, "loop_state", None) or {})
        loop_state["progress"] = progress
        return await self._update_claimed_turn(
            turn,
            iteration_count=budget.used_iterations,
            budget_snapshot=budget.snapshot(),
            token_usage=token_usage,
            loop_state=loop_state,
        )

    async def _call_model_with_retry(
        self,
        *,
        turn,
        completion_kwargs: dict[str, Any],
        iteration_count: int,
    ) -> Any:
        async def _on_retry(
            next_attempt: int, exc: Exception, delay_seconds: float
        ) -> None:
            await self.ledger.append(
                session_id=str(turn.session_id),
                turn_id=str(turn.id),
                type=AgentEventType.MODEL_RETRYING,
                payload={
                    "next_attempt": next_attempt,
                    "delay_seconds": delay_seconds,
                    "error": str(exc),
                    "iteration_count": iteration_count,
                },
            )
            agent_metrics.increment("models.retries")

        return await run_with_retry(
            lambda: acompletion(**completion_kwargs),
            policy=_retry_policy(),
            on_retry=_on_retry,
        )

    async def _renew_turn_lease(self, turn):
        now = datetime.now(timezone.utc)
        return await self._update_claimed_turn(
            turn,
            lease_until=now + _turn_lease_duration(),
        )

    async def _update_claimed_turn(self, turn, **values):
        claim_token = getattr(turn, "claimed_at", None)
        if claim_token is None:
            raise asyncio.CancelledError
        updated = await self.turns.update_if_claimed(
            str(turn.id),
            expected_claimed_at=claim_token,
            **values,
        )
        if updated is None:
            raise asyncio.CancelledError
        return updated

    async def _consume_stream_response(
        self,
        *,
        agent_session,
        turn,
        response: Any,
        message_id: str,
        allow_thinking: bool,
        expected_execution_target=None,
    ) -> StreamCompletionResult:
        current_session = await self.sessions.get_fresh(str(agent_session.id))
        if current_session is None or (
            expected_execution_target is not None
            and execution_target_from_session(current_session)
            != expected_execution_target
        ):
            raise _ExecutionTargetChanged
        agent_session = current_session
        if not hasattr(response, "__aiter__"):
            return await self._consume_response(
                agent_session=agent_session,
                turn=turn,
                response=response,
                message_id=message_id,
                allow_thinking=allow_thinking,
            )

        text_parts: list[str] = []
        thinking_parts: list[str] = []
        text_index = 0
        thinking_index = 0
        thinking_completed = False
        seen_tool_calls: dict[int, StreamToolCall] = {}
        usage: dict[str, Any] | None = None

        async for chunk in response:
            turn = await self._renew_turn_lease(turn)
            current_session = await self.sessions.get_fresh(str(agent_session.id))
            if current_session is None or (
                expected_execution_target is not None
                and execution_target_from_session(current_session)
                != expected_execution_target
            ):
                close = getattr(response, "aclose", None)
                if close is not None:
                    await close()
                raise _ExecutionTargetChanged
            agent_session = current_session
            usage = _merge_usage(usage, _extract_token_usage(chunk))

            reasoning_delta = extract_reasoning_delta(chunk)
            if allow_thinking and reasoning_delta:
                thinking_parts.append(reasoning_delta)
                await self.ledger.append(
                    session_id=str(agent_session.id),
                    turn_id=str(turn.id),
                    type=AgentEventType.ASSISTANT_THINKING_DELTA,
                    payload={
                        "message_id": message_id,
                        "delta": reasoning_delta,
                        "content": "".join(thinking_parts),
                        "index": thinking_index,
                    },
                )
                thinking_index += 1

            text_delta = extract_text_delta(chunk)
            if text_delta:
                if allow_thinking and thinking_parts and not thinking_completed:
                    await self.ledger.append(
                        session_id=str(agent_session.id),
                        turn_id=str(turn.id),
                        type=AgentEventType.ASSISTANT_THINKING_COMPLETED,
                        payload={
                            "message_id": message_id,
                            "content": "".join(thinking_parts).strip(),
                            "index": max(thinking_index - 1, 0),
                        },
                    )
                    thinking_completed = True
                text_parts.append(text_delta)
                await self.ledger.append(
                    session_id=str(agent_session.id),
                    turn_id=str(turn.id),
                    type=AgentEventType.ASSISTANT_TEXT_DELTA,
                    payload={
                        "message_id": message_id,
                        "delta": text_delta,
                        "content": "".join(text_parts),
                        "index": text_index,
                    },
                )
                text_index += 1

            for delta in extract_tool_call_deltas(chunk):
                if allow_thinking and thinking_parts and not thinking_completed:
                    await self.ledger.append(
                        session_id=str(agent_session.id),
                        turn_id=str(turn.id),
                        type=AgentEventType.ASSISTANT_THINKING_COMPLETED,
                        payload={
                            "message_id": message_id,
                            "content": "".join(thinking_parts).strip(),
                            "index": max(thinking_index - 1, 0),
                        },
                    )
                    thinking_completed = True
                seen_before = delta.index in seen_tool_calls
                state = seen_tool_calls.setdefault(
                    delta.index,
                    StreamToolCall(
                        call_id=_canonical_tool_call_id(message_id, delta.index),
                        name=delta.name or "",
                        index=delta.index,
                    ),
                )
                started_before = (
                    bool(state.call_id and state.name) if seen_before else False
                )
                if delta.name:
                    state.name = delta.name
                if not started_before and state.call_id and state.name:
                    await self.ledger.append(
                        session_id=str(agent_session.id),
                        turn_id=str(turn.id),
                        type=AgentEventType.ASSISTANT_TOOL_CALL_STARTED,
                        payload={
                            "message_id": message_id,
                            "call_id": state.call_id,
                            "name": state.name,
                            "status": "building",
                            "index": state.index,
                        },
                    )
                if delta.arguments_delta:
                    state.arguments_text += delta.arguments_delta
                    await self.ledger.append(
                        session_id=str(agent_session.id),
                        turn_id=str(turn.id),
                        type=AgentEventType.ASSISTANT_TOOL_CALL_DELTA,
                        payload={
                            "message_id": message_id,
                            "call_id": state.call_id,
                            "name": state.name,
                            "arguments_delta": delta.arguments_delta,
                            "arguments": state.arguments(),
                            "status": "building",
                            "index": state.index,
                        },
                    )

        current_session = await self.sessions.get_fresh(str(agent_session.id))
        if current_session is None or (
            expected_execution_target is not None
            and execution_target_from_session(current_session)
            != expected_execution_target
        ):
            raise _ExecutionTargetChanged
        agent_session = current_session

        thinking_text = "".join(thinking_parts).strip()
        if allow_thinking and thinking_text and not thinking_completed:
            await self.ledger.append(
                session_id=str(agent_session.id),
                turn_id=str(turn.id),
                type=AgentEventType.ASSISTANT_THINKING_COMPLETED,
                payload={
                    "message_id": message_id,
                    "content": thinking_text,
                    "index": max(thinking_index - 1, 0),
                },
            )

        tool_calls = [seen_tool_calls[index] for index in sorted(seen_tool_calls)]
        for tool_call in tool_calls:
            await self.ledger.append(
                session_id=str(agent_session.id),
                turn_id=str(turn.id),
                type=AgentEventType.ASSISTANT_TOOL_CALL_COMPLETED,
                payload={
                    "message_id": message_id,
                    "call_id": tool_call.call_id,
                    "name": tool_call.name,
                    "arguments": tool_call.arguments(),
                    "status": "completed",
                    "index": tool_call.index,
                },
            )

        final_text = "".join(text_parts).strip()
        if final_text:
            await self.ledger.append(
                session_id=str(agent_session.id),
                turn_id=str(turn.id),
                type=AgentEventType.ASSISTANT_TEXT_COMPLETED,
                payload={
                    "message_id": message_id,
                    "text": final_text,
                    "content": final_text,
                    "index": max(text_index - 1, 0),
                },
            )

        return StreamCompletionResult(
            text=final_text,
            thinking=thinking_text,
            tool_calls=tool_calls,
            token_usage=usage,
            streamed=True,
        )

    async def _consume_response(
        self,
        *,
        agent_session,
        turn,
        response: Any,
        message_id: str,
        allow_thinking: bool,
    ) -> StreamCompletionResult:
        usage = _extract_token_usage(response)
        thinking_text = (
            extract_response_thinking(response).strip() if allow_thinking else ""
        )
        if thinking_text:
            await self.ledger.append(
                session_id=str(agent_session.id),
                turn_id=str(turn.id),
                type=AgentEventType.ASSISTANT_THINKING_COMPLETED,
                payload={
                    "message_id": message_id,
                    "content": thinking_text,
                    "index": 0,
                },
            )
        tool_calls = [
            _stream_tool_call_from_payload(item, index, message_id=message_id)
            for index, item in enumerate(_extract_tool_calls(response))
        ]
        for tool_call in tool_calls:
            await self.ledger.append(
                session_id=str(agent_session.id),
                turn_id=str(turn.id),
                type=AgentEventType.ASSISTANT_TOOL_CALL_STARTED,
                payload={
                    "message_id": message_id,
                    "call_id": tool_call.call_id,
                    "name": tool_call.name,
                    "status": "building",
                    "index": tool_call.index,
                },
            )
            await self.ledger.append(
                session_id=str(agent_session.id),
                turn_id=str(turn.id),
                type=AgentEventType.ASSISTANT_TOOL_CALL_COMPLETED,
                payload={
                    "message_id": message_id,
                    "call_id": tool_call.call_id,
                    "name": tool_call.name,
                    "arguments": tool_call.arguments(),
                    "status": "completed",
                    "index": tool_call.index,
                },
            )

        final_text = _extract_response_text(response)
        if final_text:
            await self.ledger.append(
                session_id=str(agent_session.id),
                turn_id=str(turn.id),
                type=AgentEventType.ASSISTANT_TEXT_COMPLETED,
                payload={
                    "message_id": message_id,
                    "text": final_text,
                    "content": final_text,
                    "index": 0,
                },
            )

        return StreamCompletionResult(
            text=final_text,
            thinking=thinking_text,
            tool_calls=tool_calls,
            token_usage=usage,
            streamed=False,
        )

    async def complete_turn_from_result(self, *, turn, result: LoopResult):
        claim_token = getattr(turn, "claimed_at", None)
        current_turn = await self.turns.get_fresh(str(turn.id))
        if current_turn is None:
            return None
        if (
            claim_token is None
            or current_turn.status != AgentTurnStatus.RUNNING
            or current_turn.claimed_at != claim_token
        ):
            return current_turn
        turn = current_turn

        if result.termination_reason == "assistant_final":
            status = AgentTurnStatus.COMPLETED
            event_type = AgentEventType.TURN_COMPLETED
        elif result.termination_reason == "waiting_approval":
            status = AgentTurnStatus.WAITING_APPROVAL
            event_type = None
        elif result.termination_reason == "cancelled":
            status = AgentTurnStatus.CANCELLED
            event_type = AgentEventType.TURN_CANCELLED
        elif result.termination_reason == "interrupted":
            status = AgentTurnStatus.CANCELLED
            event_type = AgentEventType.TURN_INTERRUPTED
        elif result.termination_reason == "no_progress":
            status = AgentTurnStatus.FAILED
            event_type = AgentEventType.TURN_NO_PROGRESS
        else:
            status = AgentTurnStatus.FAILED
            event_type = AgentEventType.TURN_FAILED

        loop_state = dict(getattr(turn, "loop_state", None) or {})
        loop_state["termination_reason"] = result.termination_reason
        persisted_budget = dict(getattr(turn, "budget_snapshot", None) or {})
        max_iterations = int(
            persisted_budget.get("max_iterations") or _max_iterations()
        )
        updated = await self.turns.update_if_claimed(
            str(turn.id),
            expected_claimed_at=claim_token,
            status=status,
            final_text=result.final_text,
            token_usage=result.token_usage,
            termination_reason=result.termination_reason,
            iteration_count=result.iteration_count,
            budget_snapshot={
                "used_iterations": result.iteration_count,
                "max_iterations": max_iterations,
            },
            loop_state=loop_state,
            error_code=result.error_code,
            error_message=result.error_message,
            claimed_at=None,
            lease_until=None,
            completed_at=datetime.now(timezone.utc)
            if status
            in {
                AgentTurnStatus.COMPLETED,
                AgentTurnStatus.FAILED,
                AgentTurnStatus.CANCELLED,
            }
            else None,
        )
        if updated is None:
            return await self.turns.get_fresh(str(turn.id))
        if result.termination_reason == "assistant_final":
            payload = {"final_text": result.final_text}
        elif result.termination_reason in {"interrupted", "cancelled", "no_progress"}:
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
        if status in {
            AgentTurnStatus.COMPLETED,
            AgentTurnStatus.FAILED,
            AgentTurnStatus.CANCELLED,
        }:
            await self.sessions.release_active_turn(
                str(updated.session_id), str(updated.id)
            )
        log_fields = {
            "session_id": str(updated.session_id),
            "turn_id": str(updated.id),
            "status": updated.status,
            "termination_reason": result.termination_reason,
            "iteration_count": result.iteration_count,
            "error_code": result.error_code,
        }
        if result.error_message:
            log_fields["error_message"] = truncate_log_value(result.error_message)
        logger.info("agent_core.turn.finished", **log_fields)
        agent_metrics.increment(f"turns.{result.termination_reason}")
        agent_metrics.observe("turns.iterations", float(result.iteration_count))
        return updated


def _extract_response_text(response: Any) -> str:
    choices = _value(response, "choices") or []
    if not choices:
        return ""
    message = _value(choices[0], "message")
    content = _value(message, "content") or ""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            text = (
                item.get("text")
                if isinstance(item, dict)
                else getattr(item, "text", None)
            )
            if isinstance(text, str) and text.strip():
                parts.append(text.strip())
        return "\n".join(parts).strip()
    return ""


def _extract_tool_calls(response: Any) -> list[dict[str, Any]]:
    choices = _value(response, "choices") or []
    if not choices:
        return []
    message = _value(choices[0], "message")
    raw_tool_calls = _value(message, "tool_calls") or []
    calls: list[dict[str, Any]] = []
    for raw in raw_tool_calls:
        function = _value(raw, "function")
        name = _value(function, "name")
        arguments = _value(function, "arguments")
        call_id = _value(raw, "id")
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
                "id": call_id,
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


def _tool_call_dict(tool_call: StreamToolCall) -> dict[str, Any]:
    return {
        "id": tool_call.call_id,
        "name": tool_call.name,
        "arguments": tool_call.arguments(),
    }


def _stream_tool_call_from_payload(
    tool_call: dict[str, Any],
    index: int,
    *,
    message_id: str,
) -> StreamToolCall:
    return StreamToolCall(
        call_id=_canonical_tool_call_id(message_id, index),
        name=str(tool_call.get("name") or ""),
        arguments_text=json.dumps(
            tool_call.get("arguments") or {},
            separators=(",", ":"),
            default=str,
        ),
        index=index,
    )


def _canonical_tool_call_id(message_id: str, index: int) -> str:
    occurrence = f"bioinfoflow:agent-tool-call:{message_id}:{index}"
    return f"tc_{uuid5(NAMESPACE_URL, occurrence).hex}"


def _extract_token_usage(response: Any) -> dict[str, Any] | None:
    usage = _value(response, "usage")
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


def _progress_state(loop_state: dict[str, Any] | None) -> dict[str, Any]:
    raw = (loop_state or {}).get("progress")
    if not isinstance(raw, dict):
        return _progress_payload([], [], 0)
    calls = raw.get("previous_tool_calls")
    results = raw.get("previous_tool_results")
    repeat_count = raw.get("repeat_count")
    return _progress_payload(
        [str(item) for item in calls] if isinstance(calls, list) else [],
        [str(item) for item in results] if isinstance(results, list) else [],
        max(int(repeat_count or 0), 0),
    )


def _progress_payload(
    previous_tool_calls: list[str],
    previous_tool_results: list[str],
    repeat_count: int,
) -> dict[str, Any]:
    return {
        "previous_tool_calls": list(previous_tool_calls),
        "previous_tool_results": list(previous_tool_results),
        "repeat_count": int(repeat_count),
    }


def _pending_progress_payload(
    *,
    previous_tool_calls: list[str],
    previous_tool_results: list[str],
    repeat_count: int,
    pending_tool_calls: list[str],
    pending_tool_results: list[str],
    deferred_tool_calls: list[dict[str, str]],
) -> dict[str, Any]:
    progress = _progress_payload(
        previous_tool_calls,
        previous_tool_results,
        repeat_count,
    )
    progress["pending_observation"] = {
        "tool_calls": list(pending_tool_calls),
        "tool_results": list(pending_tool_results),
        "deferred_tool_calls": [dict(item) for item in deferred_tool_calls],
    }
    return progress


def _pending_observation(loop_state: dict[str, Any] | None) -> dict[str, Any] | None:
    progress = (loop_state or {}).get("progress")
    if not isinstance(progress, dict):
        return None
    pending = progress.get("pending_observation")
    if not isinstance(pending, dict):
        return None
    tool_calls = pending.get("tool_calls")
    tool_results = pending.get("tool_results")
    deferred_tool_calls = pending.get("deferred_tool_calls") or []
    if (
        not isinstance(tool_calls, list)
        or not isinstance(tool_results, list)
        or not isinstance(deferred_tool_calls, list)
    ):
        return None
    descriptors = [
        {
            "tool_name": str(item.get("tool_name") or ""),
            "tool_call_id": str(item.get("tool_call_id") or ""),
        }
        for item in deferred_tool_calls
        if isinstance(item, dict)
    ]
    return {
        "tool_calls": [str(item) for item in tool_calls],
        "tool_results": [str(item) for item in tool_results],
        "deferred_tool_calls": descriptors,
    }


def _pending_tool_result_signature(tool_name: str, tool_call_id: str | None) -> str:
    return json.dumps(
        {
            "tool": tool_name,
            "status": "pending",
            "tool_call_id": str(tool_call_id or ""),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _deferred_tool_result(tool_name: str) -> ToolExecutionResult:
    return ToolExecutionResult(
        action_id="",
        status="deferred",
        error={
            "type": "DeferredToolCall",
            "message": (
                f"{tool_name} was not executed because an earlier tool call is waiting "
                "for user input or approval. Call it again if it is still needed after "
                "the turn resumes."
            ),
        },
    )


def _failed_tool_result(exc: BaseException) -> ToolExecutionResult:
    if isinstance(exc, asyncio.CancelledError):
        return ToolExecutionResult(
            action_id="",
            status="cancelled",
            error={"type": "CancelledError", "message": "Tool execution was cancelled."},
        )
    return ToolExecutionResult(
        action_id="",
        status="failed",
        error={"type": exc.__class__.__name__, "message": str(exc)},
    )


def _retry_policy() -> RetryPolicy:
    return RetryPolicy(
        max_attempts=max(int(settings.agent_retry_max_attempts or 1), 1),
        base_delay_seconds=max(
            float(settings.agent_retry_base_delay_seconds or 0.0), 0.0
        ),
        max_delay_seconds=max(
            float(settings.agent_retry_max_delay_seconds or 0.0), 0.0
        ),
    )


def _turn_lease_duration():
    seconds = max(int(getattr(settings, "agent_turn_lease_seconds", 300) or 300), 1)
    return timedelta(seconds=seconds)


def _tool_call_signature(tool_call: dict[str, Any]) -> str:
    return json.dumps(
        {
            "name": tool_call.get("name"),
            "arguments": tool_call.get("arguments") or {},
        },
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _tool_result_signature(tool_name: str, result: ToolExecutionResult) -> str:
    return json.dumps(
        {
            "tool": tool_name,
            "status": result.status,
            "result": result.result,
            "error": result.error,
        },
        default=str,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _cancellation_reason(turn) -> str:
    return "interrupted" if is_interrupt_requested(turn) else "cancelled"


def _tool_role(agent_session) -> str:
    return (
        "worker"
        if str(getattr(agent_session, "role_profile", "orchestrator")) == "worker"
        else "orchestrator"
    )


def _tool_permission_error_code(exc: PermissionDeniedError) -> str:
    if "not exposed" in str(exc):
        return "tool_not_exposed"
    return "tool_permission_denied"


def _max_iterations() -> int:
    return int(settings.agent_max_iterations)


def _value(source: Any, key: str) -> Any:
    if isinstance(source, dict):
        return source.get(key)
    return getattr(source, key, None)
