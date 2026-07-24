from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import app.database as app_database
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings
from app.models.agent_core import (
    AgentActionStatus,
    AgentToolCallBatchStatus,
    AgentTurn,
    AgentTurnStatus,
)
from app.repositories.agent_core_repo import (
    AgentActionRepository,
    AgentSessionRepository,
    AgentTurnRepository,
)
from app.services.agent_core.approval_batches import (
    TERMINAL_ACTION_STATUSES,
)
from app.services.agent_core.context import AgentContextAssembler
from app.services.agent_core.core.budget import IterationBudget
from app.services.agent_core.core.guardrails import (
    next_repeat_count,
    no_progress_detected,
)
from app.services.agent_core.core.interrupt import is_interrupt_requested
from app.services.agent_core.core.lease import (
    LEASE_LOSS_CANCELLATION,
    is_lease_loss_cancellation,
)
from app.services.agent_core.core.retry import RetryPolicy, run_with_retry
from app.services.agent_core.core.runtime_strategy import (
    RuntimeCapabilities,
    RuntimeStrategy,
)
from app.services.agent_core.core.types import LoopResult
from app.services.agent_core.events import AgentEventType
from app.services.agent_core.execution_target import (
    ExecutionTargetChangedError,
    execution_target_from_session,
    session_execution_scope_from_metadata,
)
from app.services.agent_core.ledger import AgentEventLedger
from app.services.agent_core.metrics import agent_metrics
from app.services.agent_core.ownership import (
    TurnOwnership,
    TurnOwnershipLostError,
    new_turn_owner_token,
)
from app.services.agent_core.observability import truncate_log_value
from app.services.agent_core.permissions.context import PermissionContextResolver
from app.services.agent_core.tools import AgentToolContext, build_default_tool_registry
from app.services.agent_core.tools.batches import ToolCallBatchCoordinator
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
    ReasoningRequest,
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
from app.services.model_runtime.streams import aclose_async_iterator
from app.utils.exceptions import PermissionDeniedError
from app.utils.logging import get_logger


logger = get_logger(__name__)


@dataclass
class _PendingToolCall:
    call_id: str
    name: str
    provider_call_id: str | None = None
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
        ownership: TurnOwnership | None = None,
    ):
        self.db = session
        self.sessions = AgentSessionRepository(session)
        self.turns = AgentTurnRepository(session)
        self.actions = AgentActionRepository(session)
        owner_token = ownership.owner_token if ownership is not None else None
        owned_turn_id = ownership.turn_id if ownership is not None else None
        self.ledger = AgentEventLedger(
            session,
            owned_turn_id=owned_turn_id,
            expected_owner_token=owner_token,
        )
        self.context = AgentContextAssembler(
            session,
            owned_turn_id=owned_turn_id,
            expected_owner_token=owner_token,
        )
        self.transcript = AgentTranscriptStore(
            session,
            owned_turn_id=owned_turn_id,
            expected_owner_token=owner_token,
        )
        self.registry = build_default_tool_registry()
        self.executor = AgentToolExecutor(session, self.registry)
        self.tool_batches = ToolCallBatchCoordinator(session)
        self._current_prepared_batch_id: str | None = None
        self.model_gateway = model_gateway or ModelGateway()
        self.ownership = ownership
        self._execution_owner_token = owner_token

    async def run_turn(
        self,
        *,
        turn_id: str,
        target: ModelTarget,
        capabilities: RuntimeCapabilities = RuntimeCapabilities(),
        strategy: RuntimeStrategy = RuntimeStrategy(),
        max_tokens: int | None = None,
        continuation_batch_id: str | None = None,
        continuation_failure_mode: str = "failed",
        execution_owner_token: str | None = None,
    ) -> LoopResult:
        if execution_owner_token is not None:
            self._execution_owner_token = execution_owner_token
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
        active_continuation_batch_id = continuation_batch_id
        if active_continuation_batch_id is not None:
            batch = await self.tool_batches.batches.get_fresh(
                active_continuation_batch_id
            )
            if batch is not None and batch.status == "ready":
                if not await self.tool_batches.claim_continuation(
                    active_continuation_batch_id
                ):
                    active_continuation_batch_id = None

        while budget.consume():
            await self._ensure_owned()
            turn = await self.turns.get(turn_id)
            if turn is None:
                if active_continuation_batch_id is not None:
                    await self.tool_batches.fail_continuation(
                        active_continuation_batch_id
                    )
                return LoopResult(
                    termination_reason="model_failed",
                    final_text=None,
                    iteration_count=budget.used_iterations,
                    error_code="turn_not_found",
                    error_message="Agent turn could not be loaded.",
                )
            if turn.status == AgentTurnStatus.CANCELLED or is_interrupt_requested(turn):
                if active_continuation_batch_id is not None:
                    await self.tool_batches.cancel_continuation(
                        active_continuation_batch_id
                    )
                return LoopResult(
                    termination_reason=_cancellation_reason(turn),
                    final_text=None,
                    iteration_count=budget.used_iterations,
                    token_usage=token_usage,
                )
            turn = await self._renew_turn_lease(turn)
            if turn is None:
                return LoopResult(
                    termination_reason="model_failed",
                    final_text=None,
                    iteration_count=budget.used_iterations,
                    error_code="execution_claim_lost",
                    error_message="Agent turn execution lease ownership was lost.",
                    token_usage=token_usage,
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
            permission_context, agent_session = await PermissionContextResolver(
                self.db
            ).resolve_with_session(
                session_id=str(turn.session_id),
                workspace_id=str(turn.workspace_id),
                user_id=turn.user_id,
            )
            permission_snapshot = permission_context.snapshot()
            expected_execution_target = permission_snapshot["execution_target"]
            expected_execution_scope = permission_snapshot.get("execution_scope")
            visible_tools = (
                self.executor.exposure.exposed_specs(
                    policy=permission_snapshot["toolset_policy"],
                    role=permission_context.role,
                    execution_target=expected_execution_target,
                    execution_scope=expected_execution_scope,
                )
                if tools_enabled
                else []
            )
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
                reasoning=ReasoningRequest(
                    enabled=strategy.allow_thinking,
                    effort="medium" if strategy.allow_thinking else None,
                ),
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
                await self._ensure_owned()
            except asyncio.CancelledError:
                if active_continuation_batch_id is not None:
                    await self.tool_batches.cancel_continuation(
                        active_continuation_batch_id
                    )
                return LoopResult(
                    termination_reason=_cancellation_reason(turn),
                    final_text=None,
                    iteration_count=budget.used_iterations,
                    token_usage=token_usage,
                )
            except Exception as exc:
                released_batch_id = active_continuation_batch_id
                if active_continuation_batch_id is not None:
                    if continuation_failure_mode == "ready":
                        await self.tool_batches.release_continuation(
                            active_continuation_batch_id
                        )
                    else:
                        await self.tool_batches.fail_continuation(
                            active_continuation_batch_id
                        )
                model_error = (
                    exc.to_public_dict() if isinstance(exc, ModelError) else None
                )
                return LoopResult(
                    termination_reason="model_failed",
                    final_text=None,
                    iteration_count=budget.used_iterations,
                    error_code="model_request_failed",
                    error_message=str(exc),
                    token_usage=token_usage,
                    continuation_batch_id=released_batch_id,
                    model_replay_safe=(
                        exc.replay_safe if isinstance(exc, ModelError) else True
                    ),
                    model_error=model_error,
                )

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
            tool_calls = _normalize_tool_calls(
                streamed.tool_calls,
                turn_id=str(turn.id),
                iteration_count=budget.used_iterations,
            )
            if tool_calls:
                tool_call_signatures = [
                    _tool_call_signature(tool_call) for tool_call in tool_calls
                ]
                try:
                    (
                        waiting,
                        tool_result_signatures,
                        claimed_batch_id,
                    ) = await self._execute_tool_calls(
                        agent_session=agent_session,
                        turn=turn,
                        tool_calls=tool_calls,
                        provider=target.provider_kind,
                        model=target.model_name,
                        commentary=streamed.commentary or None,
                        final_text=streamed.text or None,
                        continuation=streamed.continuation,
                        wire_protocol=target.wire_protocol,
                        prior_continuation_batch_id=active_continuation_batch_id,
                        expected_execution_target=expected_execution_target,
                        expected_execution_scope=expected_execution_scope,
                    )
                    if active_continuation_batch_id is not None:
                        active_continuation_batch_id = None
                except ExecutionTargetChangedError:
                    continue
                except asyncio.CancelledError:
                    if self._current_prepared_batch_id is not None:
                        await self._cancel_committed_batch(
                            self._current_prepared_batch_id,
                            agent_session=agent_session,
                            turn_id=turn_id,
                        )
                        self._current_prepared_batch_id = None
                    if active_continuation_batch_id is not None:
                        await self.tool_batches.cancel_continuation(
                            active_continuation_batch_id
                        )
                    cancelled_turn = await self.turns.get_fresh(turn_id)
                    return LoopResult(
                        termination_reason=_cancellation_reason(cancelled_turn or turn),
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
                active_continuation_batch_id = claimed_batch_id
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
                delivered_steers = await self._deliver_pending_steers(
                    session_id=str(agent_session.id),
                    turn_id=str(turn.id),
                )
                if not delivered_steers and no_progress_detected(
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
                    if active_continuation_batch_id is not None:
                        await self.tool_batches.fail_continuation(
                            active_continuation_batch_id
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
            turn = await self._checkpoint_loop_state(
                turn,
                budget=budget,
                token_usage=token_usage,
                progress=_progress_payload([], [], 0),
            )
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
                    await self._ensure_owned()
                    try:
                        fresh_session = await self._session_for_expected_target(
                            str(agent_session.id),
                            expected_execution_target=expected_execution_target,
                            expected_execution_scope=expected_execution_scope,
                        )
                    except ExecutionTargetChangedError:
                        continue
                    if fresh_session is None:
                        return LoopResult(
                            termination_reason="model_failed",
                            final_text=None,
                            iteration_count=budget.used_iterations,
                            token_usage=token_usage,
                            error_code="session_not_found",
                            error_message="Agent session could not be loaded.",
                        )
                    agent_session = fresh_session
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
                released_batch_id = active_continuation_batch_id
                if active_continuation_batch_id is not None:
                    if continuation_failure_mode == "ready":
                        await self.tool_batches.release_continuation(
                            active_continuation_batch_id
                        )
                    else:
                        await self.tool_batches.fail_continuation(
                            active_continuation_batch_id
                        )
                return LoopResult(
                    termination_reason="model_failed",
                    final_text=None,
                    iteration_count=budget.used_iterations,
                    token_usage=token_usage,
                    error_code="empty_model_response",
                    error_message="The selected model completed without returning visible text.",
                    continuation_batch_id=released_batch_id,
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
            await self._ensure_owned()
            try:
                fresh_session = await self._session_for_expected_target(
                    str(agent_session.id),
                    expected_execution_target=expected_execution_target,
                    expected_execution_scope=expected_execution_scope,
                )
            except ExecutionTargetChangedError:
                continue
            if fresh_session is None:
                return LoopResult(
                    termination_reason="model_failed",
                    final_text=None,
                    iteration_count=budget.used_iterations,
                    token_usage=token_usage,
                    error_code="session_not_found",
                    error_message="Agent session could not be loaded.",
                )
            agent_session = fresh_session
            active_session_id = str(agent_session.id)
            await self.transcript.append_parts(
                session_id=active_session_id,
                turn_id=turn_id,
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
            if await self._deliver_pending_steers(
                session_id=active_session_id,
                turn_id=turn_id,
            ):
                if active_continuation_batch_id is not None:
                    await self.tool_batches.mark_terminal(
                        active_continuation_batch_id
                    )
                    active_continuation_batch_id = None
                continue
            if self._execution_owner_token is not None:
                sealed = await self._seal_steering_if_idle(
                    turn_id=turn_id,
                )
                if not sealed:
                    if await self._deliver_pending_steers(
                        session_id=active_session_id,
                        turn_id=turn_id,
                    ):
                        if active_continuation_batch_id is not None:
                            await self.tool_batches.mark_terminal(
                                active_continuation_batch_id
                            )
                            active_continuation_batch_id = None
                        continue
                    await self._ensure_owned()
            if active_continuation_batch_id is not None:
                await self.tool_batches.mark_terminal(active_continuation_batch_id)
                active_continuation_batch_id = None
            return LoopResult(
                termination_reason="assistant_final",
                final_text=final_text,
                iteration_count=budget.used_iterations,
                token_usage=token_usage,
            )

        if active_continuation_batch_id is not None:
            await self.tool_batches.fail_continuation(active_continuation_batch_id)
        return LoopResult(
            termination_reason="budget_exhausted",
            final_text=None,
            iteration_count=budget.used_iterations,
            token_usage=token_usage,
            error_code="iteration_budget_exhausted",
            error_message="Agent turn exhausted its iteration budget.",
        )

    async def _deliver_pending_steers(
        self,
        *,
        session_id: str,
        turn_id: str,
    ) -> list:
        if self._execution_owner_token is None:
            return []
        session_factory = async_sessionmaker(
            bind=self.db.bind,
            expire_on_commit=False,
            class_=AsyncSession,
        )
        async with session_factory() as boundary_session:
            return await AgentTranscriptStore(
                boundary_session
            ).deliver_pending_steers(
                session_id=session_id,
                turn_id=turn_id,
                expected_owner_token=self._execution_owner_token,
            )

    async def _seal_steering_if_idle(self, *, turn_id: str) -> bool:
        if self._execution_owner_token is None:
            return True
        session_factory = async_sessionmaker(
            bind=self.db.bind,
            expire_on_commit=False,
            class_=AsyncSession,
        )
        async with session_factory() as boundary_session:
            return await AgentTurnRepository(
                boundary_session
            ).seal_steering_if_idle(
                turn_id=turn_id,
                expected_owner_token=self._execution_owner_token,
            )

    async def _cancel_pending_steers(
        self,
        *,
        session_id: str,
        turn_id: str,
        reason: str,
    ) -> None:
        session_factory = async_sessionmaker(
            bind=self.db.bind,
            expire_on_commit=False,
            class_=AsyncSession,
        )
        async with session_factory() as boundary_session:
            await AgentTranscriptStore(boundary_session).cancel_pending_steers(
                session_id=session_id,
                turn_id=turn_id,
                reason=reason,
            )

    async def _session_for_expected_target(
        self,
        session_id: str,
        *,
        expected_execution_target: dict[str, str] | None,
        expected_execution_scope: dict[str, Any] | None,
    ):
        agent_session = await self.sessions.get_fresh(session_id)
        if agent_session is None:
            return None
        if (
            expected_execution_target is not None
            and execution_target_from_session(agent_session)
            != expected_execution_target
        ):
            raise ExecutionTargetChangedError
        if (
            session_execution_scope_from_metadata(agent_session.session_metadata)
            != expected_execution_scope
        ):
            raise ExecutionTargetChangedError
        return agent_session

    async def _execute_tool_calls(
        self,
        *,
        agent_session,
        turn,
        tool_calls: list[dict],
        provider: str,
        model: str,
        text: str | None = None,
        commentary: str | None = None,
        final_text: str | None = None,
        continuation: ResponsesContinuation | None = None,
        wire_protocol: str = "chat_completions",
        prior_continuation_batch_id: str | None = None,
        expected_execution_target: dict[str, str] | None = None,
        expected_execution_scope: dict[str, Any] | None = None,
    ) -> tuple[bool, list[str], str | None]:
        session_id = str(agent_session.id)
        turn_id = str(turn.id)
        final_text = final_text if final_text is not None else text
        batch_id = str(uuid4())
        context = AgentToolContext(
            db=self.db,
            workspace_id=str(turn.workspace_id),
            user_id=turn.user_id,
            session_id=str(agent_session.id),
            turn_id=str(turn.id),
            ownership_guard=self._ensure_owned,
            expected_owner_token=self._execution_owner_token,
        )
        prepared: list[tuple[dict[str, Any], str, ToolExecutionResult]] = []
        try:
            locked_session = await self.sessions.lock_policy(session_id)
            if locked_session is None:
                raise PermissionDeniedError("Agent session is not accessible")
            if (
                expected_execution_target is not None
                and execution_target_from_session(locked_session)
                != expected_execution_target
            ):
                await self.db.rollback()
                raise ExecutionTargetChangedError
            if (
                session_execution_scope_from_metadata(locked_session.session_metadata)
                != expected_execution_scope
            ):
                await self.db.rollback()
                raise ExecutionTargetChangedError
            if (
                self._execution_owner_token is not None
                and not await self.turns.lock_execution_owner(
                    turn_id,
                    owner_token=self._execution_owner_token,
                )
            ):
                await self.db.rollback()
                raise TurnOwnershipLostError("Agent turn ownership was replaced")
            agent_session = locked_session
            locked_policy_version = int(agent_session.permission_policy_version)
            await self.tool_batches.create(
                session_id=session_id,
                turn_id=turn_id,
                tool_call_count=len(tool_calls),
                batch_id=batch_id,
                commit=False,
            )
            await self._append_assistant_tool_calls(
                agent_session=agent_session,
                turn=turn,
                provider=provider,
                model=model,
                tool_calls=tool_calls,
                commentary=commentary,
                final_text=final_text,
                continuation=continuation,
                wire_protocol=wire_protocol,
                batch_id=batch_id,
                commit=False,
                owner_fence_held=self._execution_owner_token is not None,
            )
            for ordinal, tool_call in enumerate(tool_calls):
                tool_name = decode_provider_tool_name(tool_call["name"])
                result = await self.executor.execute(
                    tool_name=tool_name,
                    input=tool_call["arguments"],
                    context=context,
                    toolset_policy=agent_session.toolset_policy,
                    permission_mode=agent_session.permission_mode,
                    automation_mode=agent_session.automation_mode,
                    tool_call_id=tool_call["id"],
                    tool_batch_id=batch_id,
                    tool_call_ordinal=ordinal,
                    defer_execution=True,
                    commit_action=False,
                    role=_tool_role(agent_session),
                    execution_target=execution_target_from_session(agent_session),
                )
                prepared.append((tool_call, tool_name, result))
            if not await self.sessions.policy_version_matches(
                session_id, locked_policy_version
            ):
                raise RuntimeError(
                    "Permission policy changed during atomic tool-batch preparation"
                )
            prepared_actions = await self.actions.list_for_batch(batch_id)
            if any(
                action.evaluated_policy_version != locked_policy_version
                for action in prepared_actions
            ):
                raise RuntimeError(
                    "Tool action was evaluated outside the locked permission policy"
                )
            if prior_continuation_batch_id is not None:
                await self.tool_batches.batches.terminalize_continuing_pending(
                    prior_continuation_batch_id
                )
            await self.db.commit()
            self._current_prepared_batch_id = batch_id
        except TurnOwnershipLostError:
            await self.db.rollback()
            raise
        except ExecutionTargetChangedError:
            await self.db.rollback()
            raise
        except asyncio.CancelledError as exc:
            if is_lease_loss_cancellation(exc):
                await self.db.rollback()
                raise
            await self._persist_failed_preparation_batch(
                batch_id=batch_id,
                session_id=session_id,
                turn_id=turn_id,
                tool_calls=tool_calls,
                provider=provider,
                model=model,
                commentary=commentary,
                final_text=final_text,
                continuation=continuation,
                wire_protocol=wire_protocol,
                action_status=AgentActionStatus.CANCELLED,
                batch_status=AgentToolCallBatchStatus.CANCELLED,
                error_type="BatchPreparationCancelled",
                error_message="Tool batch preparation was cancelled.",
                prior_continuation_batch_id=prior_continuation_batch_id,
            )
            raise exc
        except Exception as exc:  # noqa: BLE001 - replace with a complete terminal batch
            await self._persist_failed_preparation_batch(
                batch_id=batch_id,
                session_id=session_id,
                turn_id=turn_id,
                tool_calls=tool_calls,
                provider=provider,
                model=model,
                commentary=commentary,
                final_text=final_text,
                continuation=continuation,
                wire_protocol=wire_protocol,
                action_status=AgentActionStatus.FAILED,
                batch_status=AgentToolCallBatchStatus.FAILED,
                error_type="BatchPreparationError",
                error_message=str(exc),
                prior_continuation_batch_id=prior_continuation_batch_id,
            )
            if isinstance(exc, PermissionDeniedError):
                raise
            self._current_prepared_batch_id = None
            return False, [], None

        fresh_turn = await self._ensure_turn_allows_tool_execution(turn_id)
        if fresh_turn is None:
            await self._cancel_committed_batch(
                batch_id,
                agent_session=agent_session,
                turn_id=turn_id,
            )
            self._current_prepared_batch_id = None
            raise asyncio.CancelledError
        turn = fresh_turn
        interaction_ordinals = [
            ordinal
            for ordinal, call in enumerate(tool_calls)
            if self.registry.get(
                decode_provider_tool_name(call["name"])
            ).spec.interaction
        ]
        if interaction_ordinals:
            waiting, signatures = await self._execute_interaction_batch(
                agent_session=agent_session,
                turn=turn,
                prepared=prepared,
                batch_id=batch_id,
                interaction_ordinal=interaction_ordinals[0],
            )
            self._current_prepared_batch_id = None
            return waiting, signatures, None
        waiting = False
        result_signatures: list[str] = []
        approval_barrier_hit = False
        for segment in self._ordered_tool_execution_segments(prepared):
            parallel_results: dict[str, ToolExecutionResult] = {}
            if self._is_parallel_segment(segment):
                results = await asyncio.gather(
                    *[
                        self._execute_tool_call_isolated(
                            agent_session=agent_session,
                            turn=turn,
                            action_id=prepared_result.action_id,
                        )
                        for _tool_call, _tool_name, prepared_result in segment
                    ]
                )
                parallel_results = {
                    prepared_result.action_id: result
                    for (_call, _name, prepared_result), result in zip(
                        segment, results, strict=True
                    )
                }

            for tool_call, tool_name, prepared_result in segment:
                turn = await self._renew_turn_lease(turn)
                if turn is None:
                    current_turn = await self.turns.get_fresh(turn_id)
                    if current_turn is not None and (
                        current_turn.status == AgentTurnStatus.CANCELLED
                        or is_interrupt_requested(current_turn)
                    ):
                        raise asyncio.CancelledError
                    raise asyncio.CancelledError(LEASE_LOSS_CANCELLATION)
                result = parallel_results.get(prepared_result.action_id)
                if result is None:
                    if prepared_result.requires_resume:
                        waiting = True
                        approval_barrier_hit = True
                        break
                    result = prepared_result
                    if prepared_result.status == AgentActionStatus.REQUESTED:
                        result = await self.executor.resume_action(
                            action_id=prepared_result.action_id,
                            context=context,
                            require_resume_marker=False,
                        )
                if (
                    result.requires_resume
                    or result.status == AgentActionStatus.WAITING_DECISION
                ):
                    waiting = True
                    approval_barrier_hit = True
                    break
                result_signatures.append(_tool_result_signature(tool_name, result))
                if result.status in TERMINAL_ACTION_STATUSES:
                    await self._append_tool_result(
                        agent_session=agent_session,
                        turn=turn,
                        tool_name=tool_name,
                        tool_call_id=tool_call.get("id"),
                        action_id=prepared_result.action_id,
                        batch_id=batch_id,
                        result=result,
                    )
            if approval_barrier_hit:
                break
        state = await self.tool_batches.settle(batch_id)
        claimed_batch_id: str | None = None
        if state == "ready":
            await self._append_missing_batch_results(
                agent_session=agent_session,
                turn=turn,
                batch_id=batch_id,
            )
            if await self.tool_batches.claim_continuation(batch_id):
                claimed_batch_id = batch_id
        self._current_prepared_batch_id = None
        return waiting, result_signatures, claimed_batch_id

    async def _fresh_running_turn(self, turn_id: str):
        turn = await self.turns.get_fresh(turn_id)
        if (
            turn is None
            or turn.status == AgentTurnStatus.CANCELLED
            or is_interrupt_requested(turn)
        ):
            return None
        if self._execution_owner_token is not None and (
            turn.status != AgentTurnStatus.RUNNING
            or turn.owner_token != self._execution_owner_token
        ):
            raise TurnOwnershipLostError("Agent turn ownership was replaced")
        return turn

    async def _ensure_turn_allows_tool_execution(self, turn_id: str):
        return await self._fresh_running_turn(turn_id)

    async def _persist_failed_preparation_batch(
        self,
        *,
        batch_id: str,
        session_id: str,
        turn_id: str,
        tool_calls: list[dict],
        provider: str,
        model: str,
        commentary: str | None,
        final_text: str | None,
        continuation: ResponsesContinuation | None,
        wire_protocol: str,
        action_status: str,
        batch_status: str,
        error_type: str,
        error_message: str,
        prior_continuation_batch_id: str | None = None,
    ) -> None:
        await self.db.rollback()
        if (
            self._execution_owner_token is not None
            and not await self.turns.lock_execution_owner(
                turn_id,
                owner_token=self._execution_owner_token,
            )
        ):
            raise TurnOwnershipLostError("Agent turn ownership was replaced")
        agent_session = await self.sessions.get(session_id)
        turn = await self.turns.get(turn_id)
        if agent_session is None or turn is None:
            raise RuntimeError("Cannot rebuild tool batch without its session and turn")
        batch = await self.tool_batches.create(
            session_id=session_id,
            turn_id=turn_id,
            tool_call_count=len(tool_calls),
            batch_id=batch_id,
            commit=False,
        )
        await self._append_assistant_tool_calls(
            agent_session=agent_session,
            turn=turn,
            provider=provider,
            model=model,
            tool_calls=tool_calls,
            commentary=commentary,
            final_text=final_text,
            continuation=continuation,
            wire_protocol=wire_protocol,
            batch_id=batch_id,
            commit=False,
            owner_fence_held=self._execution_owner_token is not None,
        )
        await self.tool_batches.repair_preparation_failure(
            batch_id=batch_id,
            session_id=session_id,
            turn_id=turn_id,
            tool_calls=tool_calls,
            error_message=error_message,
            action_status=action_status,
            error_type=error_type,
            commit=False,
        )
        await self.tool_batches.batches.update_all_pending(
            batch,
            status=batch_status,
            completed_at=datetime.now(timezone.utc),
        )
        if prior_continuation_batch_id is not None:
            await self.tool_batches.batches.terminalize_continuing_pending(
                prior_continuation_batch_id
            )
        await self._append_missing_batch_results(
            agent_session=agent_session,
            turn=turn,
            batch_id=batch_id,
            commit=False,
        )
        await self.db.commit()

    async def _cancel_committed_batch(
        self, batch_id: str, *, agent_session, turn_id: str
    ) -> None:
        if (
            self._execution_owner_token is not None
            and not await self.turns.lock_execution_owner(
                turn_id,
                owner_token=self._execution_owner_token,
            )
        ):
            await self.db.rollback()
            return
        turn = await self.turns.get_fresh(turn_id)
        if turn is None:
            await self.db.rollback()
            return
        now = datetime.now(timezone.utc)
        for action in await self.actions.list_for_batch(batch_id):
            if action.status in {
                AgentActionStatus.WAITING_DECISION,
                AgentActionStatus.REQUESTED,
                AgentActionStatus.RUNNING,
            }:
                await self.actions.cancel_open(
                    str(action.id),
                    error={
                        "type": "CancelledError",
                        "message": "Tool batch execution was cancelled.",
                    },
                    completed_at=now,
                    expected_turn_owner_token=self._execution_owner_token,
                )
        await self.tool_batches.batches.cancel_nonterminal(batch_id)
        await self._append_missing_batch_results(
            agent_session=agent_session,
            turn=turn,
            batch_id=batch_id,
        )

    async def _execute_interaction_batch(
        self,
        *,
        agent_session,
        turn,
        prepared: list[tuple[dict[str, Any], str, ToolExecutionResult]],
        batch_id: str,
        interaction_ordinal: int,
    ) -> tuple[bool, list[str]]:
        result_signatures: list[str] = []
        for ordinal, (tool_call, tool_name, prepared_result) in enumerate(prepared):
            if ordinal == interaction_ordinal:
                continue
            result = prepared_result
            if prepared_result.status in {
                AgentActionStatus.REQUESTED,
                AgentActionStatus.WAITING_DECISION,
            }:
                result = await self.executor.cancel_action(
                    action_id=prepared_result.action_id,
                    reason="A user interaction in this tool-call batch is exclusive.",
                    expected_turn_owner_token=self._execution_owner_token,
                )
            result_signatures.append(_tool_result_signature(tool_name, result))
        await self.tool_batches.settle(batch_id)
        return True, result_signatures

    async def resume_turn_from_action(
        self,
        *,
        action_id: str,
        target: ModelTarget,
        capabilities: RuntimeCapabilities = RuntimeCapabilities(),
        strategy: RuntimeStrategy = RuntimeStrategy(),
        max_tokens: int | None = None,
        continuation_failure_mode: str = "failed",
    ) -> LoopResult:
        await self._ensure_owned()
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

        context = AgentToolContext(
            db=self.db,
            workspace_id=str(turn.workspace_id),
            user_id=turn.user_id,
            session_id=str(agent_session.id),
            turn_id=str(turn.id),
            ownership_guard=self._ensure_owned,
            expected_owner_token=self._execution_owner_token,
        )
        if action.tool_batch_id:
            failed_resume_status: str | None = None
            for batch_action in await self.actions.list_for_batch(
                str(action.tool_batch_id)
            ):
                if batch_action.status in TERMINAL_ACTION_STATUSES:
                    await self._clear_terminal_action_resume_state(batch_action)
                    continue
                if batch_action.status != AgentActionStatus.REQUESTED:
                    continue
                result = await self.executor.resume_action(
                    action_id=str(batch_action.id),
                    context=context,
                    require_resume_marker=False,
                )
                if (
                    result.status in TERMINAL_ACTION_STATUSES
                    and not await self._has_tool_result(
                        str(agent_session.id),
                        tool_call_id=batch_action.tool_call_id,
                        action_id=str(batch_action.id),
                        batch_id=str(action.tool_batch_id),
                    )
                ):
                    await self._append_tool_result(
                        agent_session=agent_session,
                        turn=turn,
                        tool_name=batch_action.name,
                        tool_call_id=batch_action.tool_call_id,
                        action_id=str(batch_action.id),
                        batch_id=str(action.tool_batch_id),
                        result=result,
                    )
                if result.status == AgentActionStatus.WAITING_DECISION:
                    return LoopResult(
                        termination_reason="waiting_approval",
                        final_text=None,
                        iteration_count=persisted_iteration_count,
                        token_usage=persisted_token_usage,
                    )
                if result.status not in {
                    AgentActionStatus.COMPLETED,
                    AgentActionStatus.REJECTED,
                }:
                    failed_resume_status = result.status
            if failed_resume_status is not None:
                await self._append_missing_batch_results(
                    agent_session=agent_session,
                    turn=turn,
                    batch_id=str(action.tool_batch_id),
                )
                return LoopResult(
                    termination_reason="model_failed",
                    final_text=None,
                    iteration_count=persisted_iteration_count,
                    token_usage=persisted_token_usage,
                    error_code="tool_resume_failed",
                    error_message=(
                        "Approved tool action finished with status: "
                        f"{failed_resume_status}"
                    ),
                )
            state = await self.tool_batches.settle(str(action.tool_batch_id))
            if state != "ready":
                return LoopResult(
                    termination_reason="waiting_approval",
                    final_text=None,
                    iteration_count=persisted_iteration_count,
                    token_usage=persisted_token_usage,
                )
            if not await self.tool_batches.claim_continuation(
                str(action.tool_batch_id)
            ):
                return LoopResult(
                    termination_reason="waiting_approval",
                    final_text=None,
                    iteration_count=persisted_iteration_count,
                    token_usage=persisted_token_usage,
                )
            await self._append_missing_batch_results(
                agent_session=agent_session,
                turn=turn,
                batch_id=str(action.tool_batch_id),
            )
        else:
            if action.status == AgentActionStatus.REJECTED:
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
                    context=context,
                    require_resume_marker=False,
                )
            if result.status == AgentActionStatus.WAITING_DECISION:
                return LoopResult(
                    termination_reason="waiting_approval",
                    final_text=None,
                    iteration_count=persisted_iteration_count,
                    token_usage=persisted_token_usage,
                )
            if not await self._has_tool_result(
                str(agent_session.id),
                tool_call_id=action.tool_call_id,
                action_id=str(action.id),
                batch_id=None,
            ):
                await self._append_tool_result(
                    agent_session=agent_session,
                    turn=turn,
                    tool_name=action.name,
                    tool_call_id=action.tool_call_id,
                    action_id=str(action.id),
                    batch_id=None,
                    result=result,
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
            target=target,
            capabilities=capabilities,
            strategy=strategy,
            max_tokens=max_tokens,
            continuation_batch_id=(
                str(action.tool_batch_id) if action.tool_batch_id else None
            ),
            continuation_failure_mode=continuation_failure_mode,
        )

    async def _clear_terminal_action_resume_state(self, action) -> None:
        if action.status not in TERMINAL_ACTION_STATUSES:
            return
        if action.requires_resume or action.completed_at is None:
            values = {
                "requires_resume": False,
                "completed_at": action.completed_at or datetime.now(timezone.utc),
            }
            if self.ownership is None:
                await self.actions.update_all(action, **values)
            else:
                updated, owned = await self.actions.update_all_owned(
                    action,
                    expected_owner_token=self.ownership.owner_token,
                    **values,
                )
                if not owned or updated is None:
                    raise TurnOwnershipLostError("Agent turn ownership was replaced")

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
        batch_id: str | None = None,
        commit: bool = True,
        owner_fence_held: bool = False,
    ) -> None:
        await self._ensure_owned()
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
            if any(
                call.get("provider_tool_call_id") != call.get("id")
                for call in tool_calls
            ):
                continuation = None
            else:
                continuation = continuation.advance_canonical_input(
                    model_input_parts_from_message("assistant", parts)
                )
        metadata = metadata_with_responses_continuation(
            {
                "provider": provider,
                "model": model,
                "kind": "tool_calls",
                "tool_batch_id": batch_id,
                "turn_id": str(turn.id),
                "provider_tool_call_ids": [
                    {
                        "ordinal": ordinal,
                        "provider_id": call.get("provider_tool_call_id"),
                        "internal_id": call["id"],
                    }
                    for ordinal, call in enumerate(tool_calls)
                ],
            },
            continuation,
        )
        await self.transcript.append_parts(
            session_id=str(agent_session.id),
            turn_id=str(turn.id),
            role="assistant",
            parts=parts,
            metadata=metadata,
            commit=commit,
            replace_session_metadata_key=(
                RESPONSES_CONTINUATION_METADATA_KEY
                if wire_protocol == "responses" and commit
                else None
            ),
            owner_fence_held=owner_fence_held,
        )

    async def _append_tool_result(
        self,
        *,
        agent_session,
        turn,
        tool_name: str,
        tool_call_id: str | None,
        action_id: str | None,
        batch_id: str | None,
        result,
        commit: bool = True,
    ) -> None:
        await self._ensure_owned()
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
                "action_id": action_id,
                "tool_batch_id": batch_id,
                "is_error": bool(result.error) or result.status != "completed",
            },
            commit=commit,
            owner_fence_held=not commit and self._execution_owner_token is not None,
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
        self,
        *,
        agent_session,
        turn,
        action_id: str,
    ):
        bind = self.db.bind
        session_factory = (
            async_sessionmaker(bind=bind, expire_on_commit=False)
            if bind is not None
            else app_database.async_session_maker
        )
        async with session_factory() as session:
            executor = AgentToolExecutor(session, build_default_tool_registry())
            return await executor.resume_action(
                action_id=action_id,
                context=AgentToolContext(
                    db=session,
                    workspace_id=str(turn.workspace_id),
                    user_id=turn.user_id,
                    session_id=str(agent_session.id),
                    turn_id=str(turn.id),
                    ownership_guard=self._ensure_owned,
                    expected_owner_token=self._execution_owner_token,
                ),
                require_resume_marker=False,
            )

    async def _has_tool_result(
        self,
        session_id: str,
        *,
        tool_call_id: str | None,
        action_id: str | None,
        batch_id: str | None,
    ) -> bool:
        if not tool_call_id:
            return False
        messages = await self.transcript.list_messages(session_id)
        for message in messages:
            if message.role != "tool":
                continue
            metadata = message.message_metadata or {}
            if action_id and metadata.get("action_id") == action_id:
                return True
            if batch_id and metadata.get("tool_batch_id") == batch_id:
                if metadata.get("tool_call_id") == tool_call_id:
                    return True
            if not batch_id and not metadata.get("tool_batch_id"):
                if metadata.get("tool_call_id") == tool_call_id:
                    return True
        return False

    async def _append_missing_batch_results(
        self,
        *,
        agent_session,
        turn,
        batch_id: str,
        commit: bool = True,
    ) -> None:
        for batch_action in await self.actions.list_for_batch(batch_id):
            if await self._has_tool_result(
                str(agent_session.id),
                tool_call_id=batch_action.tool_call_id,
                action_id=str(batch_action.id),
                batch_id=batch_id,
            ):
                continue
            if batch_action.status == AgentActionStatus.REJECTED:
                result = ToolExecutionResult(
                    action_id=str(batch_action.id),
                    status=batch_action.status,
                    error={
                        "type": "UserRejected",
                        "message": "The user rejected this tool call.",
                    },
                )
            else:
                result = ToolExecutionResult(
                    action_id=str(batch_action.id),
                    status=batch_action.status,
                    result=batch_action.result,
                    error=batch_action.error,
                )
            await self._append_tool_result(
                agent_session=agent_session,
                turn=turn,
                tool_name=batch_action.name,
                tool_call_id=batch_action.tool_call_id,
                action_id=str(batch_action.id),
                batch_id=batch_id,
                result=result,
                commit=commit,
            )

    def _ordered_tool_execution_segments(
        self,
        prepared: list[tuple[dict[str, Any], str, ToolExecutionResult]],
    ) -> list[list[tuple[dict[str, Any], str, ToolExecutionResult]]]:
        segments: list[list[tuple[dict[str, Any], str, ToolExecutionResult]]] = []
        parallel_segment: list[tuple[dict[str, Any], str, ToolExecutionResult]] = []
        for item in prepared:
            if self._is_parallel_candidate(item):
                parallel_segment.append(item)
                continue
            if parallel_segment:
                segments.append(parallel_segment)
                parallel_segment = []
            segments.append([item])
        if parallel_segment:
            segments.append(parallel_segment)
        return segments

    def _is_parallel_candidate(
        self,
        item: tuple[dict[str, Any], str, ToolExecutionResult],
    ) -> bool:
        _tool_call, tool_name, prepared_result = item
        return (
            prepared_result.status == AgentActionStatus.REQUESTED
            and not prepared_result.requires_resume
            and self.registry.get(tool_name).spec.parallel_safe
        )

    def _is_parallel_segment(
        self,
        segment: list[tuple[dict[str, Any], str, ToolExecutionResult]],
    ) -> bool:
        return bool(segment) and all(
            self._is_parallel_candidate(item) for item in segment
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
        values = {
            "iteration_count": budget.used_iterations,
            "budget_snapshot": budget.snapshot(),
            "token_usage": token_usage,
            "loop_state": loop_state,
        }
        if self.ownership is not None:
            updated, owned = await self.turns.update_owned(
                str(turn.id),
                expected_owner_token=self.ownership.owner_token,
                **values,
            )
            if not owned or updated is None:
                raise TurnOwnershipLostError("Agent turn ownership was replaced")
            return updated
        if self._execution_owner_token is not None:
            updated = await self.turns.update_claimed_execution(
                str(turn.id),
                owner_token=self._execution_owner_token,
                **values,
            )
            if updated is None:
                raise TurnOwnershipLostError("Agent turn ownership was replaced")
            return updated
        return await self.turns.update_all(turn, **values)

    async def _renew_turn_lease(self, turn):
        if self.ownership is not None:
            await self.ownership.renew()
            refreshed = await self.turns.get(str(turn.id))
            if refreshed is None:
                raise TurnOwnershipLostError("Agent turn ownership was replaced")
            return refreshed
        now = datetime.now(timezone.utc)
        if self._execution_owner_token is not None:
            return await self.turns.renew_execution_lease(
                str(turn.id),
                owner_token=self._execution_owner_token,
                lease_until=now + _turn_lease_duration(),
            )
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
        semantic_output_emitted = False

        event_stream = self.model_gateway.invoke(invocation)
        try:
            async with asyncio.timeout(_model_attempt_timeout_seconds()):
                async for event in event_stream:
                    await self._ensure_owned()
                    if isinstance(
                        event,
                        (ReasoningDelta, TextDelta, ToolCallDelta),
                    ):
                        semantic_output_emitted = True
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
                                provider_call_id=event.call_id,
                                index=event.index,
                            ),
                        )
                        started_before = (
                            bool(state.call_id and state.name) if seen_before else False
                        )
                        if event.call_id:
                            state.call_id = event.call_id
                            state.provider_call_id = event.call_id
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
        except TimeoutError:
            raise ModelError(
                category="timeout",
                message="The model provider request timed out.",
                provider_code="model_attempt_timeout",
                retryable=True,
                replay_safe=not semantic_output_emitted,
            ) from None
        finally:
            await aclose_async_iterator(event_stream)

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
            payload: dict[str, Any] = {
                "next_attempt": next_attempt,
                "delay_seconds": delay_seconds,
                "error": str(exc),
            }
            if isinstance(exc, ModelError):
                payload["model_error"] = exc.to_public_dict()
            await self.ledger.append(
                session_id=str(turn.session_id),
                turn_id=str(turn.id),
                type=AgentEventType.MODEL_RETRYING,
                payload=payload,
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
        await self._ensure_owned()
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

    async def complete_turn_from_result(
        self,
        *,
        turn,
        result: LoopResult,
    ):
        current_turn = await self.turns.get_fresh(str(turn.id))
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

        loop_state = dict(getattr(turn, "loop_state", None) or {})
        loop_state["termination_reason"] = result.termination_reason
        if result.termination_reason == "waiting_approval":
            loop_state[
                "pending_tool_call_ids"
            ] = await self.transcript.latest_unresolved_tool_call_batch_ids(
                session_id=str(turn.session_id),
                turn_id=str(turn.id),
            )
        resume_batch_token = (
            new_turn_owner_token()
            if result.termination_reason == "waiting_approval"
            else None
        )
        persisted_budget = dict(getattr(turn, "budget_snapshot", None) or {})
        max_iterations = int(
            persisted_budget.get("max_iterations") or _max_iterations()
        )
        values = dict(
            status=status,
            accepts_steer=status
            not in {
                AgentTurnStatus.COMPLETED,
                AgentTurnStatus.FAILED,
                AgentTurnStatus.CANCELLED,
            },
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
            owner_token=None,
            resume_batch_token=func.coalesce(
                AgentTurn.resume_batch_token,
                resume_batch_token,
            ),
            completed_at=datetime.now(timezone.utc)
            if status
            in {
                AgentTurnStatus.COMPLETED,
                AgentTurnStatus.FAILED,
                AgentTurnStatus.CANCELLED,
            }
            else None,
        )
        publish_terminal_event = event_type is not None
        if self.ownership is None:
            if publish_terminal_event:
                updated = await self.turns.update_all_pending(turn, **values)
            else:
                updated = await self.turns.update_all(turn, **values)
        else:
            updated, owned = await self.turns.update_owned(
                str(turn.id),
                expected_owner_token=self.ownership.owner_token,
                commit=not publish_terminal_event,
                **values,
            )
            if not owned or updated is None:
                raise TurnOwnershipLostError("Agent turn ownership was replaced")
        if result.termination_reason == "assistant_final":
            payload = {"final_text": result.final_text}
        elif result.termination_reason in {"interrupted", "cancelled", "no_progress"}:
            payload = {"termination_reason": result.termination_reason}
        elif result.error_code or result.error_message:
            payload = {
                "error_message": result.error_message,
                "error_code": result.error_code,
            }
            if result.model_error is not None:
                payload["model_error"] = result.model_error
        else:
            payload = {"termination_reason": result.termination_reason}
        if event_type is not None:
            await self.ledger.append(
                session_id=str(updated.session_id),
                turn_id=str(updated.id),
                type=event_type,
                payload=payload,
                after_owner_fenced_transition=self.ownership is not None,
            )
        if status in {
            AgentTurnStatus.COMPLETED,
            AgentTurnStatus.FAILED,
            AgentTurnStatus.CANCELLED,
        }:
            await self._cancel_pending_steers(
                session_id=str(updated.session_id),
                turn_id=str(updated.id),
                reason=result.termination_reason,
            )
            await self.sessions.release_active_turn(
                str(updated.session_id),
                str(updated.id),
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
        if result.model_error is not None:
            log_fields["model_error"] = result.model_error
        logger.info("agent_core.turn.finished", **log_fields)
        agent_metrics.increment(f"turns.{result.termination_reason}")
        agent_metrics.observe("turns.iterations", float(result.iteration_count))
        return updated

    async def _ensure_owned(self) -> None:
        if self.ownership is not None:
            await self.ownership.ensure_current()


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
        "provider_tool_call_id": tool_call.provider_call_id or None,
        "name": tool_call.name,
        "arguments": tool_call.arguments(),
    }


def _normalize_tool_calls(
    tool_calls: list[_PendingToolCall],
    *,
    turn_id: str,
    iteration_count: int,
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, item in enumerate(tool_calls):
        call = _tool_call_dict(item)
        provider_id = call.get("provider_tool_call_id")
        internal_id = str(provider_id).strip() if provider_id else ""
        if not internal_id or internal_id in seen_ids:
            internal_id = f"bioinfoflow-{turn_id}-{iteration_count}-{index}"
            suffix = 1
            while internal_id in seen_ids:
                internal_id = (
                    f"bioinfoflow-{turn_id}-{iteration_count}-{index}-{suffix}"
                )
                suffix += 1
        seen_ids.add(internal_id)
        call["id"] = internal_id
        normalized.append(call)
    return normalized


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


def _model_attempt_timeout_seconds() -> float:
    return max(float(settings.agent_model_attempt_timeout_seconds or 0.0), 0.001)


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
