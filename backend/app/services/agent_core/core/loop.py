from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import app.database as app_database
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings
from app.models.agent_core import AgentActionStatus, AgentTurnStatus
from app.repositories.agent_core_repo import (
    AgentActionRepository,
    AgentSessionRepository,
    AgentTurnRepository,
)
from app.services.agent_core.approval_batches import (
    TERMINAL_ACTION_STATUSES,
    ordered_tool_call_batch,
)
from app.services.agent_core.context import AgentContextAssembler
from app.services.agent_core.core.budget import IterationBudget
from app.services.agent_core.core.guardrails import no_progress_detected
from app.services.agent_core.core.interrupt import is_interrupt_requested
from app.services.agent_core.core.retry import RetryPolicy, run_with_retry
from app.services.agent_core.core.runtime_strategy import (
    RuntimeCapabilities,
    RuntimeStrategy,
)
from app.services.agent_core.core.types import LoopResult
from app.services.agent_core.events import AgentEventType
from app.services.agent_core.execution_target import execution_target_from_session
from app.services.agent_core.ledger import AgentEventLedger
from app.services.agent_core.metrics import agent_metrics
from app.services.agent_core.observability import truncate_log_value
from app.services.agent_core.tools import AgentToolContext, build_default_tool_registry
from app.services.agent_core.tools.executor import (
    AgentToolExecutor,
    ToolExecutionResult,
)
from app.services.agent_core.tools.toolsets import (
    decode_provider_tool_name,
    model_tool_definitions,
)
from app.services.agent_core.transcript import (
    AgentTranscriptStore,
    text_part,
    tool_calls_part,
)
from app.services.agent_core.transcript.messages import (
    RESPONSES_CONTINUATION_METADATA_KEY,
    latest_responses_continuation_anchor,
    metadata_with_responses_continuation,
    model_input_parts_from_message,
)
from app.services.model_runtime.contracts import (
    CompletionMetadata,
    ModelInvocation,
    ModelTarget,
    ModelWarning,
    ReasoningDelta,
    ResponseStarted,
    ResponsesContinuation,
    TextDelta,
    ToolCallDelta,
    UsageReport,
)
from app.services.model_runtime.errors import ModelError
from app.services.model_runtime.gateway import ModelGateway
from app.utils.exceptions import PermissionDeniedError
from app.utils.logging import get_logger


logger = get_logger(__name__)


@dataclass
class _PendingToolCall:
    call_id: str
    name: str
    arguments_text: str = ""
    index: int = 0

    def arguments(self) -> dict[str, Any]:
        try:
            value = json.loads(self.arguments_text or "{}")
        except json.JSONDecodeError:
            return {}
        return value if isinstance(value, dict) else {}


@dataclass
class _ModelTurnResult:
    text: str
    commentary: str
    thinking: str
    tool_calls: list[_PendingToolCall]
    token_usage: dict[str, Any] | None
    continuation: ResponsesContinuation | None
    warnings: list[ModelWarning]


class AgentLoopController:
    def __init__(
        self,
        session: AsyncSession,
        *,
        model_gateway: ModelGateway | None = None,
    ):
        self.db = session
        self.sessions = AgentSessionRepository(session)
        self.turns = AgentTurnRepository(session)
        self.actions = AgentActionRepository(session)
        self.ledger = AgentEventLedger(session)
        self.context = AgentContextAssembler(session)
        self.transcript = AgentTranscriptStore(session)
        self.registry = build_default_tool_registry()
        self.executor = AgentToolExecutor(session, self.registry)
        self.model_gateway = model_gateway or ModelGateway()

    async def run_turn(
        self,
        *,
        turn_id: str,
        target: ModelTarget,
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

        budget = IterationBudget(max_iterations=_max_iterations())
        tools_enabled = capabilities.supports_tools and strategy.allow_tools
        role = (
            "worker"
            if str(getattr(agent_session, "role_profile", "orchestrator")) == "worker"
            else "orchestrator"
        )
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
        token_usage: dict[str, Any] | None = None
        previous_tool_call_signatures: list[str] = []
        previous_tool_result_signatures: list[str] = []
        repeated_tool_call_count = 0
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
            if turn.status == AgentTurnStatus.CANCELLED or is_interrupt_requested(turn):
                return LoopResult(
                    termination_reason=_cancellation_reason(turn),
                    final_text=None,
                    iteration_count=budget.used_iterations,
                    token_usage=token_usage,
                )
            turn = await self._renew_turn_lease(turn)

            continuation_anchor = await self._responses_continuation_anchor(
                turn,
                target=target,
            )
            continuation = (
                continuation_anchor.continuation
                if continuation_anchor is not None
                else None
            )
            model_context = await self.context.model_context(
                agent_session=agent_session,
                turn=turn,
                exposed_tools=visible_tools,
                skip_compaction=(
                    continuation_anchor is not None
                    and continuation_anchor.turn_id == str(turn.id)
                ),
            )
            if model_context.compacted and continuation is not None:
                await self.transcript.clear_session_metadata(
                    session_id=str(agent_session.id),
                    metadata_key=RESPONSES_CONTINUATION_METADATA_KEY,
                )
                continuation = None
            invocation = ModelInvocation(
                target=target,
                instructions=model_context.instructions,
                input_items=model_context.input_items,
                tools=model_tool_definitions(visible_tools if tools_enabled else []),
                stream=capabilities.supports_streaming and strategy.use_streaming,
                max_output_tokens=max_tokens or settings.agent_max_tokens,
                allow_reasoning=strategy.allow_thinking,
                continuation=continuation,
            )

            try:
                streamed = await self._consume_model_events_with_retry(
                    agent_session=agent_session,
                    turn=turn,
                    invocation=invocation,
                    message_id=f"assistant:{turn.id}:{budget.used_iterations}",
                    allow_thinking=strategy.allow_thinking,
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
                    model_replay_safe=(
                        exc.replay_safe if isinstance(exc, ModelError) else True
                    ),
                )

            token_usage = _merge_usage(token_usage, streamed.token_usage)
            tool_calls = [_tool_call_dict(item) for item in streamed.tool_calls]
            if tool_calls:
                tool_call_signatures = [
                    _tool_call_signature(tool_call) for tool_call in tool_calls
                ]
                await self._append_assistant_tool_calls(
                    agent_session=agent_session,
                    turn=turn,
                    provider=target.provider_kind,
                    model=target.model_name,
                    tool_calls=tool_calls,
                    commentary=streamed.commentary or None,
                    final_text=streamed.text or None,
                    continuation=streamed.continuation,
                    wire_protocol=target.wire_protocol,
                )
                try:
                    waiting, tool_result_signatures = await self._execute_tool_calls(
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
                    return LoopResult(
                        termination_reason="waiting_approval",
                        final_text=None,
                        iteration_count=budget.used_iterations,
                        token_usage=token_usage,
                    )
                repeated_tool_call_count = (
                    repeated_tool_call_count + 1
                    if previous_tool_call_signatures == tool_call_signatures
                    else 1
                )
                if no_progress_detected(
                    previous_tool_call_signatures,
                    tool_call_signatures,
                    previous_tool_results=previous_tool_result_signatures,
                    next_tool_results=tool_result_signatures,
                    repeat_count=repeated_tool_call_count,
                ):
                    await self.ledger.append(
                        session_id=str(agent_session.id),
                        turn_id=str(turn.id),
                        type=AgentEventType.TURN_NO_PROGRESS,
                        payload={
                            "tool_calls": tool_call_signatures,
                            "tool_results": tool_result_signatures,
                            "iteration_count": budget.used_iterations,
                        },
                    )
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
            final_text = streamed.text
            if not final_text:
                refusal = next(
                    (
                        warning
                        for warning in streamed.warnings
                        if warning.code == "response_refusal"
                    ),
                    None,
                )
                if refusal is not None:
                    return LoopResult(
                        termination_reason="model_failed",
                        final_text=None,
                        iteration_count=budget.used_iterations,
                        token_usage=token_usage,
                        error_code="model_refusal",
                        error_message=refusal.message,
                    )
                if (
                    target.wire_protocol == "responses"
                    and streamed.commentary
                    and streamed.continuation is not None
                ):
                    await self.transcript.append_parts(
                        session_id=str(agent_session.id),
                        turn_id=str(turn.id),
                        role="assistant",
                        parts=[text_part(streamed.commentary, phase="commentary")],
                        metadata=metadata_with_responses_continuation(
                            {
                                "provider": target.provider_kind,
                                "model": target.model_name,
                                "kind": "commentary",
                            },
                            streamed.continuation.advance_canonical_input(
                                model_input_parts_from_message(
                                    "assistant",
                                    [
                                        text_part(
                                            streamed.commentary, phase="commentary"
                                        )
                                    ],
                                )
                            ),
                        ),
                        replace_session_metadata_key=(
                            RESPONSES_CONTINUATION_METADATA_KEY
                        ),
                    )
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
            parts: list[dict[str, Any]] = []
            if streamed.commentary:
                parts.append(text_part(streamed.commentary, phase="commentary"))
            parts.append(
                text_part(
                    final_text,
                    phase="final_answer"
                    if target.wire_protocol == "responses"
                    else None,
                )
            )
            final_continuation = (
                streamed.continuation.advance_canonical_input(
                    model_input_parts_from_message("assistant", parts)
                )
                if streamed.continuation is not None
                else None
            )
            await self.transcript.append_parts(
                session_id=str(agent_session.id),
                turn_id=str(turn.id),
                role="assistant",
                parts=parts,
                metadata=metadata_with_responses_continuation(
                    {"provider": target.provider_kind, "model": target.model_name},
                    final_continuation,
                ),
                replace_session_metadata_key=(
                    RESPONSES_CONTINUATION_METADATA_KEY
                    if target.wire_protocol == "responses"
                    else None
                ),
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
    ) -> tuple[bool, list[str]]:
        waiting = False
        result_signatures: list[str] = []
        index = 0
        while index < len(tool_calls):
            turn = await self._renew_turn_lease(turn)
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
                    ]
                )
                for (item, name), result in zip(batch, results, strict=False):
                    if result.requires_resume:
                        waiting = True
                        continue
                    result_signatures.append(_tool_result_signature(name, result))
                    await self._append_tool_result(
                        agent_session=agent_session,
                        turn=turn,
                        tool_name=name,
                        tool_call_id=item.get("id"),
                        result=result,
                    )
                continue

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
                role=_tool_role(agent_session),
                execution_target=execution_target_from_session(agent_session),
            )
            if result.requires_resume:
                waiting = True
                index += 1
                continue
            result_signatures.append(_tool_result_signature(tool_name, result))
            await self._append_tool_result(
                agent_session=agent_session,
                turn=turn,
                tool_name=tool_name,
                tool_call_id=tool_call.get("id"),
                result=result,
            )
            index += 1
        return waiting, result_signatures

    async def resume_turn_from_action(
        self,
        *,
        action_id: str,
        target: ModelTarget,
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
        agent_session = await self.sessions.get(str(action.session_id))
        if agent_session is None:
            return LoopResult(
                termination_reason="model_failed",
                final_text=None,
                iteration_count=0,
                error_code="session_not_found",
                error_message="Agent session could not be loaded for resume.",
            )

        batch = await ordered_tool_call_batch(
            action_repo=self.actions,
            transcript=self.transcript,
            action=action,
        )
        context = AgentToolContext(
            db=self.db,
            workspace_id=str(turn.workspace_id),
            user_id=turn.user_id,
            session_id=str(agent_session.id),
            turn_id=str(turn.id),
        )
        for sibling in batch:
            matching_tool_result = await self.transcript.find_committed_tool_result(
                session_id=str(agent_session.id),
                turn_id=str(turn.id),
                tool_call_id=sibling.tool_call_id,
            )
            if matching_tool_result is not None:
                await self._clear_terminal_action_resume_state(sibling)
                continue
            if sibling.status == AgentActionStatus.REQUESTED:
                result = await self.executor.resume_action(
                    action_id=str(sibling.id),
                    context=context,
                )
            elif sibling.status in TERMINAL_ACTION_STATUSES:
                result = _tool_result_for_terminal_action(sibling)
            else:
                continue
            if result.status not in TERMINAL_ACTION_STATUSES:
                continue
            await self._append_tool_result(
                agent_session=agent_session,
                turn=turn,
                tool_name=sibling.name,
                tool_call_id=sibling.tool_call_id,
                result=result,
            )
            refreshed = await self.actions.get(str(sibling.id))
            if refreshed is not None:
                await self._clear_terminal_action_resume_state(refreshed)

        refreshed_batch = await ordered_tool_call_batch(
            action_repo=self.actions,
            transcript=self.transcript,
            action=action,
        )
        batch_is_resolved = True
        failed_status: str | None = None
        for sibling in refreshed_batch:
            matching_tool_result = await self.transcript.find_committed_tool_result(
                session_id=str(agent_session.id),
                turn_id=str(turn.id),
                tool_call_id=sibling.tool_call_id,
            )
            if (
                sibling.status not in TERMINAL_ACTION_STATUSES
                or matching_tool_result is None
            ):
                batch_is_resolved = False
            elif sibling.status not in {
                AgentActionStatus.COMPLETED,
                AgentActionStatus.REJECTED,
            }:
                failed_status = failed_status or sibling.status
        if not batch_is_resolved:
            return LoopResult(
                termination_reason="waiting_approval",
                final_text=None,
                iteration_count=0,
            )
        if failed_status is not None:
            return LoopResult(
                termination_reason="model_failed",
                final_text=None,
                iteration_count=0,
                error_code="tool_resume_failed",
                error_message=f"Approved tool action finished with status: {failed_status}",
            )
        return await self.run_turn(
            turn_id=str(turn.id),
            target=target,
            capabilities=capabilities,
            strategy=strategy,
            max_tokens=max_tokens,
        )

    async def _clear_terminal_action_resume_state(self, action) -> None:
        if action.status not in TERMINAL_ACTION_STATUSES:
            return
        if action.requires_resume or action.completed_at is None:
            await self.actions.update_all(
                action,
                requires_resume=False,
                completed_at=action.completed_at or datetime.now(timezone.utc),
            )

    async def _append_assistant_tool_calls(
        self,
        *,
        agent_session,
        turn,
        provider: str,
        model: str,
        tool_calls: list[dict[str, Any]],
        commentary: str | None = None,
        final_text: str | None = None,
        continuation: ResponsesContinuation | None = None,
        wire_protocol: str = "chat_completions",
    ) -> None:
        parts: list[dict[str, Any]] = []
        if commentary:
            parts.append(text_part(commentary, phase="commentary"))
        if final_text:
            parts.append(
                text_part(
                    final_text,
                    phase="final_answer" if wire_protocol == "responses" else None,
                )
            )
        parts.append(
            tool_calls_part([_provider_tool_call(call) for call in tool_calls])
        )
        if continuation is not None:
            continuation = continuation.advance_canonical_input(
                model_input_parts_from_message("assistant", parts)
            )
        await self.transcript.append_parts(
            session_id=str(agent_session.id),
            turn_id=str(turn.id),
            role="assistant",
            parts=parts,
            metadata=metadata_with_responses_continuation(
                {"provider": provider, "model": model, "kind": "tool_calls"},
                continuation,
            ),
            replace_session_metadata_key=(
                RESPONSES_CONTINUATION_METADATA_KEY
                if wire_protocol == "responses"
                else None
            ),
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
            metadata={
                "tool_call_id": tool_call_id,
                "tool": tool_name,
                "is_error": bool(result.error) or result.status != "completed",
            },
        )

    async def _responses_continuation_anchor(
        self,
        turn,
        *,
        target: ModelTarget,
    ):
        messages = await self.transcript.list_messages(str(turn.session_id))
        anchor = latest_responses_continuation_anchor(messages)
        if (
            anchor is not None
            and target.wire_protocol == "responses"
            and anchor.continuation.matches_target(target)
        ):
            return anchor
        if anchor is not None or any(
            RESPONSES_CONTINUATION_METADATA_KEY
            in (getattr(message, "message_metadata", None) or {})
            for message in messages
        ):
            await self.transcript.clear_session_metadata(
                session_id=str(turn.session_id),
                metadata_key=RESPONSES_CONTINUATION_METADATA_KEY,
            )
        return None

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
                ),
                toolset_policy=agent_session.toolset_policy,
                permission_mode=agent_session.permission_mode,
                automation_mode=agent_session.automation_mode,
                tool_call_id=tool_call.get("id"),
                role=_tool_role(agent_session),
                execution_target=execution_target_from_session(agent_session),
            )

    def _is_concurrent_read_only_tool(self, tool_name: str) -> bool:
        spec = self.registry.get(tool_name).spec
        return spec.risk_level == "read" and not spec.write_scope

    async def _renew_turn_lease(self, turn):
        now = datetime.now(timezone.utc)
        return await self.turns.update_all(
            turn,
            claimed_at=turn.claimed_at or now,
            lease_until=now + _turn_lease_duration(),
        )

    async def _consume_model_events(
        self,
        *,
        agent_session,
        turn,
        invocation: ModelInvocation,
        message_id: str,
        allow_thinking: bool,
    ) -> _ModelTurnResult:
        text_parts: dict[str, list[str]] = {
            "commentary": [],
            "final_answer": [],
        }
        thinking_parts: list[str] = []
        tool_calls: dict[int, _PendingToolCall] = {}
        usage: dict[str, Any] | None = None
        text_index = 0
        thinking_index = 0
        thinking_completed = False
        response_streaming = invocation.stream
        continuation: ResponsesContinuation | None = None
        warnings: list[ModelWarning] = []

        async for event in self.model_gateway.invoke(invocation):
            if isinstance(event, ResponseStarted):
                response_streaming = event.streaming
            elif isinstance(event, ReasoningDelta):
                if not allow_thinking or not event.text:
                    continue
                thinking_parts.append(event.text)
                if response_streaming:
                    await self.ledger.append(
                        session_id=str(agent_session.id),
                        turn_id=str(turn.id),
                        type=AgentEventType.ASSISTANT_THINKING_DELTA,
                        payload={
                            "message_id": message_id,
                            "delta": event.text,
                            "content": "".join(thinking_parts),
                            "index": thinking_index,
                        },
                    )
                thinking_index += 1
            elif isinstance(event, TextDelta):
                if allow_thinking and thinking_parts and not thinking_completed:
                    await self._complete_thinking(
                        agent_session=agent_session,
                        turn=turn,
                        message_id=message_id,
                        thinking_parts=thinking_parts,
                        thinking_index=thinking_index,
                    )
                    thinking_completed = True
                if event.text:
                    phase = event.phase
                    phase_parts = text_parts[phase]
                    phase_parts.append(event.text)
                    if response_streaming:
                        await self.ledger.append(
                            session_id=str(agent_session.id),
                            turn_id=str(turn.id),
                            type=AgentEventType.ASSISTANT_TEXT_DELTA,
                            payload={
                                "message_id": message_id,
                                "delta": event.text,
                                "content": "".join(phase_parts),
                                "phase": phase,
                                "index": text_index,
                            },
                        )
                    text_index += 1
            elif isinstance(event, ToolCallDelta):
                if allow_thinking and thinking_parts and not thinking_completed:
                    await self._complete_thinking(
                        agent_session=agent_session,
                        turn=turn,
                        message_id=message_id,
                        thinking_parts=thinking_parts,
                        thinking_index=thinking_index,
                    )
                    thinking_completed = True
                seen_before = event.index in tool_calls
                state = tool_calls.setdefault(
                    event.index,
                    _PendingToolCall(
                        call_id=event.call_id or f"tool_call_{event.index + 1}",
                        name=event.name or "",
                        index=event.index,
                    ),
                )
                started_before = (
                    bool(state.call_id and state.name) if seen_before else False
                )
                if event.call_id:
                    state.call_id = event.call_id
                if event.name:
                    state.name = event.name
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
                if event.arguments_delta:
                    state.arguments_text += event.arguments_delta
                    if response_streaming:
                        await self.ledger.append(
                            session_id=str(agent_session.id),
                            turn_id=str(turn.id),
                            type=AgentEventType.ASSISTANT_TOOL_CALL_DELTA,
                            payload={
                                "message_id": message_id,
                                "call_id": state.call_id,
                                "name": state.name,
                                "arguments_delta": event.arguments_delta,
                                "arguments": state.arguments(),
                                "status": "building",
                                "index": state.index,
                            },
                        )
            elif isinstance(event, UsageReport):
                usage = _merge_usage(usage, _usage_dict(event))
            elif isinstance(event, ModelWarning):
                warnings.append(event)
                await self.ledger.append(
                    session_id=str(agent_session.id),
                    turn_id=str(turn.id),
                    type=AgentEventType.MODEL_WARNING,
                    payload={"code": event.code, "message": event.message},
                )
            elif isinstance(event, CompletionMetadata):
                if event.continuation is not None:
                    continuation = event.continuation

        thinking_text = "".join(thinking_parts).strip()
        if allow_thinking and thinking_text and not thinking_completed:
            await self._complete_thinking(
                agent_session=agent_session,
                turn=turn,
                message_id=message_id,
                thinking_parts=thinking_parts,
                thinking_index=thinking_index,
            )

        completed_calls = [tool_calls[index] for index in sorted(tool_calls)]
        for tool_call in completed_calls:
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

        commentary_text = "".join(text_parts["commentary"]).strip()
        final_text = "".join(text_parts["final_answer"]).strip()
        for phase, completed_text in (
            ("commentary", commentary_text),
            ("final_answer", final_text),
        ):
            if not completed_text:
                continue
            await self.ledger.append(
                session_id=str(agent_session.id),
                turn_id=str(turn.id),
                type=AgentEventType.ASSISTANT_TEXT_COMPLETED,
                payload={
                    "message_id": message_id,
                    "text": completed_text,
                    "content": completed_text,
                    "phase": phase,
                    "index": max(text_index - 1, 0),
                },
            )
        return _ModelTurnResult(
            text=final_text,
            commentary=commentary_text,
            thinking=thinking_text,
            tool_calls=completed_calls,
            token_usage=usage,
            continuation=continuation,
            warnings=warnings,
        )

    async def _consume_model_events_with_retry(
        self,
        *,
        agent_session,
        turn,
        invocation: ModelInvocation,
        message_id: str,
        allow_thinking: bool,
    ) -> _ModelTurnResult:
        async def on_retry(
            next_attempt: int,
            exc: Exception,
            delay_seconds: float,
        ) -> None:
            await self.ledger.append(
                session_id=str(turn.session_id),
                turn_id=str(turn.id),
                type=AgentEventType.MODEL_RETRYING,
                payload={
                    "next_attempt": next_attempt,
                    "delay_seconds": delay_seconds,
                    "error": str(exc),
                },
            )
            agent_metrics.increment("models.retries")

        return await run_with_retry(
            lambda: self._consume_model_events(
                agent_session=agent_session,
                turn=turn,
                invocation=invocation,
                message_id=message_id,
                allow_thinking=allow_thinking,
            ),
            policy=_retry_policy(),
            on_retry=on_retry,
        )

    async def _complete_thinking(
        self,
        *,
        agent_session,
        turn,
        message_id: str,
        thinking_parts: list[str],
        thinking_index: int,
    ) -> None:
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

    async def complete_turn_from_result(self, *, turn, result: LoopResult):
        current_turn = await self.turns.get(str(turn.id))
        if current_turn is None:
            return None
        if (
            current_turn.status == AgentTurnStatus.CANCELLED
            and result.termination_reason
            not in {
                "cancelled",
                "interrupted",
            }
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


def _usage_dict(usage: UsageReport) -> dict[str, int]:
    result = {
        "prompt_tokens": usage.input_tokens,
        "completion_tokens": usage.output_tokens,
        "total_tokens": usage.total_tokens,
    }
    if usage.cached_input_tokens is not None:
        result["cached_input_tokens"] = usage.cached_input_tokens
    if usage.reasoning_tokens is not None:
        result["reasoning_tokens"] = usage.reasoning_tokens
    return result


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


def _tool_call_dict(tool_call: _PendingToolCall) -> dict[str, Any]:
    return {
        "id": tool_call.call_id,
        "name": tool_call.name,
        "arguments": tool_call.arguments(),
    }


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


def _turn_lease_duration():
    seconds = max(int(getattr(settings, "agent_turn_lease_seconds", 300) or 300), 1)
    return timedelta(seconds=seconds)


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


def _tool_result_for_terminal_action(action) -> ToolExecutionResult:
    error = action.error
    if action.status == AgentActionStatus.REJECTED and not error:
        error = {
            "type": "UserRejected",
            "message": "The user rejected this tool call.",
        }
    return ToolExecutionResult(
        action_id=str(action.id),
        status=action.status,
        result=action.result,
        permission_decision=action.permission_decision,
        error=error,
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
