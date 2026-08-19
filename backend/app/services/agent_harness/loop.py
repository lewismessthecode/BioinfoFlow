from __future__ import annotations

import asyncio
import inspect
import json
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from app.config import settings
from app.repositories.agent_harness_repo import AgentHarnessRepository
from app.services.agent_harness.assets import AgentHarnessAttachmentService
from app.services.agent_harness.compression import (
    DeterministicCompactor,
    is_context_overflow,
    invoke_with_context_overflow_retry,
)
from app.services.agent_harness.context import ContextBuilder
from app.services.agent_harness.contracts import (
    AssistantDeltaEvent,
    EntryCommittedEvent,
    InteractionRequestedEvent,
    RunUpdatedEvent,
    ToolExecutionMode,
    ToolProgressView,
    ToolUpdatedEvent,
)
from app.services.agent_harness.model_resolver import (
    resolved_runtime_capabilities,
    resolved_runtime_strategy,
)
from app.services.agent_harness.model_target import (
    model_target_from_resolved,
    model_target_from_snapshot,
)
from app.services.agent_harness.projection import (
    entry_contract,
    pending_interaction_entry_view,
    run_view,
)
from app.services.agent_harness.recovery import (
    create_checkpoint,
    responses_continuation_from_checkpoint,
)
from app.services.agent_harness.tool_projection import (
    project_tool_view,
    public_output_summary as _public_output_summary,
    public_tool_progress_view,
)
from app.services.agent_harness.tools import ToolCall, ToolResult
from app.services.agent_harness.tools.specs import ToolSpec
from app.services.agent_harness.turn_settings import effective_turn_session
from app.services.agent_harness.workspace_runtime import WorkspaceRuntime
from app.services.model_runtime.contracts import (
    CompletionMetadata,
    ImagePart,
    ModelInvocation,
    ReasoningDelta,
    ReasoningPart,
    ReasoningRequest,
    ResponsesContinuation,
    TextDelta,
    TextPart,
    ToolCallDelta,
    ToolCallPart,
    ToolResultPart,
    UsageReport,
)
from app.services.model_runtime.errors import ModelError
from app.services.model_runtime.exchange import (
    ModelExchangeLifecycle,
    capture_exchange_best_effort,
)
from app.services.model_runtime.streams import aclose_async_iterator


Publish = Callable[[Any], Awaitable[None]]
HARNESS_VERSION = "complete-agent-harness-v1"


class ModelAttemptTimeoutError(TimeoutError):
    pass


class ModelVisionUnsupportedError(ValueError):
    pass


@dataclass(slots=True)
class LoopLimits:
    max_iterations: int = settings.agent_max_iterations
    max_output_tokens: int = settings.agent_max_tokens
    retry_attempts: int = settings.agent_retry_max_attempts
    model_attempt_timeout_seconds: float = settings.agent_model_attempt_timeout_seconds
    run_timeout_seconds: float = settings.agent_run_timeout_seconds
    run_token_budget: int = settings.agent_run_token_budget
    compaction_threshold_chars: int = 120_000
    preserve_recent_entries: int = 12


class AgentLoop:
    """The single model-tool-model loop used by every BioinfoFlow agent run."""

    def __init__(
        self,
        repository: AgentHarnessRepository,
        *,
        model_gateway: Any,
        workspace_factory: Callable[[Any, str], WorkspaceRuntime],
        publish: Publish,
        model_runtime_resolver: Callable[[Any], Awaitable[dict[str, Any]]]
        | None = None,
        limits: LoopLimits | None = None,
        model_exchange_recorder: ModelExchangeLifecycle | None = None,
    ) -> None:
        self.repository = repository
        self.model_gateway = model_gateway
        self.workspace_factory = workspace_factory
        self.model_runtime_resolver = model_runtime_resolver
        self.publish = publish
        self.limits = limits or LoopLimits()
        self.model_exchange_recorder = model_exchange_recorder
        self.context = ContextBuilder()
        self.compactor = DeterministicCompactor(
            preserve_recent_entries=self.limits.preserve_recent_entries
        )

    async def run(self, run_id: str, cancellation: asyncio.Event) -> None:
        run = await self.repository.get_run(run_id)
        if run is None:
            raise LookupError(f"agent run not found: {run_id}")
        session = await self.repository.get_session(str(run.session_id))
        if session is None:
            raise LookupError(f"agent session not found: {run.session_id}")
        session = effective_turn_session(session, run)
        workspace = self.workspace_factory(session, run_id)
        await self._update(run_id, status="running", phase="model")
        try:
            for iteration in range(1, self.limits.max_iterations + 1):
                if cancellation.is_set() or await self._stop_if_cancel_requested(
                    run_id
                ):
                    await self._cancel(run_id)
                    return
                if await self._stop_if_budget_exceeded(run_id):
                    return
                await self.apply_steers(run_id, str(session.id))
                entries = await self.repository.list_entries(str(session.id))
                context = await self._build_context(session, entries)

                async def invoke():
                    current = await self.repository.get_run(run_id)
                    previous = dict(current.checkpoint or {}) if current else {}
                    await self.repository.update_run(
                        run_id,
                        checkpoint={
                            **create_checkpoint(
                                harness_version=HARNESS_VERSION,
                                phase="model",
                                history_revision=context.history_revision,
                                continuation=(
                                    previous.get("continuation")
                                    if isinstance(previous.get("continuation"), dict)
                                    else None
                                ),
                                budget=(
                                    previous.get("budget")
                                    if isinstance(previous.get("budget"), dict)
                                    else None
                                ),
                            ),
                            **{
                                key: previous[key]
                                for key in (
                                    "iteration",
                                    "last_tool_signature",
                                    "repeat_count",
                                    "control_input",
                                )
                                if key in previous
                            },
                        },
                    )
                    return await self._invoke(
                        run_id=run_id,
                        iteration=iteration,
                        session=session,
                        context=context,
                        workspace=workspace,
                        cancellation=cancellation,
                    )

                async def compact():
                    nonlocal context, entries
                    plan = self.compactor.plan(
                        (_history_mapping(entry) for entry in entries),
                        threshold_chars=self.limits.compaction_threshold_chars,
                    )
                    if plan is None:
                        return False
                    compaction = await self.repository.append_entry(
                        str(session.id),
                        run_id=run_id,
                        entry_type="compaction",
                        payload=plan.payload,
                    )
                    await self.repository.update_run(
                        run_id,
                        checkpoint=create_checkpoint(
                            harness_version=HARNESS_VERSION,
                            phase="compression",
                            history_revision=compaction.sequence,
                            compaction_through=plan.through_sequence,
                        ),
                    )
                    entries = await self.repository.list_entries(str(session.id))
                    context = await self._build_context(session, entries)
                    return True

                response = await invoke_with_context_overflow_retry(
                    invoke=invoke,
                    compact=compact,
                )
                if response.cancelled or await self._stop_if_cancel_requested(run_id):
                    await self._cancel(run_id)
                    return

                execution_mode = workspace.batch_execution_mode(response.tool_calls)
                assistant_entry_id = str(uuid4())
                group_id = assistant_entry_id
                assistant = None
                if response.text or response.reasoning_traces or response.tool_calls:
                    assistant = await self._append_message(
                        str(session.id),
                        run_id,
                        role="assistant",
                        content=response.text,
                        reasoning_traces=response.reasoning_traces,
                        entry_id=assistant_entry_id,
                        tool_calls=[
                            _public_tool_call_dict(
                                call,
                                spec=workspace.tool_spec(call.name),
                                group_id=group_id,
                                execution_mode=execution_mode,
                            )
                            for call in response.tool_calls
                        ],
                    )
                response.continuation = _advance_response_continuation(response)
                await self.repository.update_run(run_id, draft=None)
                if assistant is not None:
                    await self.publish(EntryCommittedEvent(entry=assistant))

                if await self._stop_if_budget_exceeded(run_id):
                    return

                if not response.tool_calls:
                    (
                        steer_entries,
                        completed,
                    ) = await self.repository.commit_steers_or_complete_run(
                        str(session.id), run_id=run_id
                    )
                    for entry in steer_entries:
                        await self.publish(
                            EntryCommittedEvent(entry=entry_contract(entry))
                        )
                    if steer_entries:
                        continue
                    await self.publish(RunUpdatedEvent(run=run_view(completed)))
                    return

                signature = _call_signature(response.tool_calls)
                current = await self.repository.get_run(run_id)
                checkpoint = dict(current.checkpoint or {}) if current else {}
                if checkpoint.get("last_tool_signature") == signature:
                    repeats = int(checkpoint.get("repeat_count") or 0) + 1
                else:
                    repeats = 0
                if repeats >= 2:
                    await self._fail(
                        run_id,
                        "no_progress",
                        "Agent repeated the same tool calls without making progress.",
                    )
                    return
                await self.repository.update_run(
                    run_id,
                    tool_progress=[
                        _tool_progress_dict(
                            call,
                            spec=workspace.tool_spec(call.name),
                            status="pending",
                            group_id=group_id,
                            execution_mode=execution_mode,
                        )
                        for call in response.tool_calls
                    ],
                    checkpoint={
                        **create_checkpoint(
                            harness_version=HARNESS_VERSION,
                            phase="tools",
                            history_revision=assistant.sequence,
                            continuation=response.continuation,
                            in_flight_tools=tuple(
                                {
                                    "call_id": call.call_id,
                                    "group_id": group_id,
                                    "execution_mode": execution_mode,
                                    "name": call.name,
                                    "arguments": call.arguments,
                                    "replay_policy": _replay_policy(
                                        workspace, call.name
                                    ),
                                }
                                for call in response.tool_calls
                            ),
                        ),
                        "iteration": iteration,
                        "last_tool_signature": signature,
                        "repeat_count": repeats,
                        "pending_calls": [
                            _tool_call_dict(call) for call in response.tool_calls
                        ],
                    },
                )
                await self._update(run_id, status="running", phase="tools")

                mark_started, mark_finished = self._tool_progress_callbacks(
                    run_id,
                    group_id=group_id,
                    execution_mode=execution_mode,
                )

                batch = await workspace.execute_batch(
                    response.tool_calls,
                    cancellation=cancellation,
                    on_start=mark_started,
                    on_result=mark_finished,
                )
                for result in batch.results:
                    if result.status == "interaction_required":
                        pending = [
                            _tool_call_dict(call) for call in batch.pending_calls
                        ]
                        interaction = result.interaction
                        assert interaction is not None
                        current = await self.repository.get_run(run_id)
                        progress = (
                            [dict(item) for item in (current.tool_progress or [])]
                            if current is not None
                            else []
                        )
                        progress = _replace_tool_progress(
                            progress,
                            call_id=result.call_id,
                            name=result.tool_name,
                            status="interaction_required",
                        )
                        for pending_call in batch.pending_calls:
                            progress = _replace_tool_progress(
                                progress,
                                call_id=pending_call.call_id,
                                name=pending_call.name,
                                status="pending",
                            )
                        (
                            _,
                            entry,
                            waiting_run,
                        ) = await self.repository.commit_waiting_interaction(
                            str(session.id),
                            run_id=run_id,
                            request_payload={
                                "interaction_id": interaction.request_id,
                                "request": _interaction_dict(result),
                            },
                            tool_progress=progress,
                            checkpoint={
                                **create_checkpoint(
                                    harness_version=HARNESS_VERSION,
                                    phase="interaction",
                                    history_revision=0,
                                    continuation=response.continuation,
                                    in_flight_tools=tuple(
                                        {
                                            "call_id": call.call_id,
                                            "group_id": group_id,
                                            "execution_mode": execution_mode,
                                            "name": call.name,
                                            "arguments": call.arguments,
                                            "replay_policy": _replay_policy(
                                                workspace, call.name
                                            ),
                                        }
                                        for call in response.tool_calls
                                    ),
                                    interaction=_interaction_dict(result),
                                ),
                                "waiting_call": _tool_call_dict(
                                    _find_call(response.tool_calls, result.call_id)
                                ),
                                "pending_calls": pending,
                                "interaction": _interaction_dict(result),
                            },
                        )
                        await self.publish(RunUpdatedEvent(run=run_view(waiting_run)))
                        await self.publish(
                            ToolUpdatedEvent(
                                run_id=run_id,
                                tool=_tool_progress_view(waiting_run, result.call_id),
                            )
                        )
                        await self.publish(
                            EntryCommittedEvent(entry=entry_contract(entry))
                        )
                        await self.publish(
                            InteractionRequestedEvent(
                                run_id=run_id,
                                interaction=pending_interaction_entry_view(entry),
                            )
                        )
                        return
                    if result.tool_name == "update_plan" and result.status == "completed":
                        plan = await self.repository.commit_plan(
                            str(session.id),
                            run_id=run_id,
                            title=result.output.get("title"),
                            items=list(result.output.get("items") or []),
                        )
                        await self.publish(
                            EntryCommittedEvent(entry=entry_contract(plan))
                        )
                        payload = plan.payload if isinstance(plan.payload, Mapping) else {}
                        result = replace(
                            result,
                            output={
                                "plan_id": payload.get("plan_id"),
                                "revision": payload.get("revision"),
                                "status": "completed",
                            },
                        )
                    tool_entry = await self._append_message(
                        str(session.id),
                        run_id,
                        role="tool",
                        content=json.dumps(
                            _tool_result_history_output(result),
                            ensure_ascii=False,
                            separators=(",", ":"),
                            default=str,
                        ),
                        call_id=result.call_id,
                        tool_name=result.tool_name,
                        is_error=result.status != "completed",
                        tool_status=result.status,
                    )
                    await self.publish(EntryCommittedEvent(entry=tool_entry))
                    current = await self.repository.get_run(run_id)
                    if current is not None and current.checkpoint is not None:
                        checkpoint_after_result = dict(current.checkpoint)
                        checkpoint_after_result["history_revision"] = (
                            tool_entry.sequence
                        )
                        checkpoint_after_result["in_flight_tools"] = [
                            item
                            for item in checkpoint_after_result.get("in_flight_tools")
                            or []
                            if item.get("call_id") != result.call_id
                        ]
                        checkpoint_after_result["pending_calls"] = [
                            item
                            for item in checkpoint_after_result.get("pending_calls")
                            or []
                            if item.get("call_id") != result.call_id
                        ]
                        await self.repository.update_run(
                            run_id,
                            checkpoint=checkpoint_after_result,
                        )
                if await self._stop_if_budget_exceeded(run_id):
                    return
                await self._update(
                    run_id,
                    status="running",
                    phase="model",
                    tool_progress=None,
                )
            await self._fail(
                run_id, "iteration_limit", "Agent iteration limit reached."
            )
        except asyncio.CancelledError:
            cancellation.set()
            raise
        except ModelAttemptTimeoutError as exc:
            await self._fail(run_id, "model_attempt_timeout", str(exc), exc=exc)
        except ModelVisionUnsupportedError as exc:
            notice = await self.repository.append_entry(
                str(session.id),
                run_id=run_id,
                entry_type="notice",
                payload={
                    "code": "model_vision_unsupported",
                    "message": str(exc),
                },
            )
            await self.publish(EntryCommittedEvent(entry=entry_contract(notice)))
            await self._fail(run_id, "model_vision_unsupported", str(exc))
        except Exception as exc:  # noqa: BLE001 - terminal run must be durable
            await self._fail(run_id, "agent_failed", str(exc), exc=exc)

    async def resume_interaction(
        self,
        run_id: str,
        response: dict[str, Any],
        cancellation: asyncio.Event,
        *,
        command_id: str | None = None,
    ) -> None:
        run = await self.repository.get_run(run_id)
        if run is None or run.status != "waiting_user":
            raise ValueError("run is not waiting for user interaction")
        session = await self.repository.get_session(str(run.session_id))
        if session is None:
            raise LookupError(f"agent session not found: {run.session_id}")
        session = effective_turn_session(session, run)
        checkpoint = run.checkpoint or {}
        expected_interaction_id = checkpoint_interaction_id(checkpoint)
        if response.get("request_id") != expected_interaction_id:
            raise ValueError(
                "response interaction does not match the pending interaction"
            )
        persisted_interaction = checkpoint.get("interaction")
        if (
            isinstance(response.get("approved"), bool)
            and isinstance(persisted_interaction, dict)
            and (
                persisted_interaction.get("kind") == "confirmation"
                or persisted_interaction.get("type") == "approval"
            )
        ):
            selected_response = "approve" if response["approved"] else "reject"
            allowed_responses = persisted_interaction.get("allowed_responses")
            if allowed_responses is None:
                allowed_responses = ["approve", "reject"]
            if (
                not isinstance(allowed_responses, list)
                or selected_response not in allowed_responses
            ):
                raise ValueError(
                    "approval response is not allowed by pending interaction"
                )
        if checkpoint.get("recovery_interaction"):
            await self._resume_recovery_interaction(
                run=run,
                session=session,
                checkpoint=checkpoint,
                response=response,
                cancellation=cancellation,
                command_id=command_id,
            )
            return
        call_data = checkpoint.get("waiting_call")
        if not isinstance(call_data, dict):
            raise ValueError("waiting interaction has no tool call")
        call = _runtime_tool_call(call_data)
        workspace = self.workspace_factory(session, run_id)
        replay_policy = _checkpoint_replay_policy(checkpoint, call.call_id)
        response_entry = None
        execution_response = response
        if response.get("approved") is True and replay_policy == "never":
            assessment_matches = workspace.approval_assessment_matches(
                call,
                persisted_interaction
                if isinstance(persisted_interaction, dict)
                else None,
            )
            if not await _await_if_needed(assessment_matches):
                raise ValueError("Bash approval assessment changed before execution")
            approved_risk = persisted_interaction.get("risk")
            assert isinstance(approved_risk, dict)
            approved_fingerprint = approved_risk.get("assessment_fingerprint")
            assert isinstance(approved_fingerprint, str)
            (
                response_entry,
                durable_run,
            ) = await self.repository.begin_approved_tool_execution(
                str(session.id),
                run_id=run_id,
                interaction_id=str(
                    response.get("request_id") or f"tool:{call.call_id}"
                ),
                response=response,
                call=_tool_call_dict(call),
                replay_policy=replay_policy,
                command_id=command_id,
            )
            checkpoint = dict(durable_run.checkpoint or {})
            await self.publish(
                EntryCommittedEvent(entry=entry_contract(response_entry))
            )
            await self.publish(RunUpdatedEvent(run=run_view(durable_run)))
            await self.publish(
                ToolUpdatedEvent(
                    run_id=run_id,
                    tool=_tool_progress_view(durable_run, call.call_id),
                )
            )
            execution_response = {
                **response,
                "assessment_fingerprint": approved_fingerprint,
            }
        else:
            await self._mark_tool_progress(
                run_id,
                call_id=call.call_id,
                name=call.name,
                status="running",
            )
        result = await workspace.execute(
            call,
            cancellation=cancellation,
            interaction_response=execution_response,
        )
        if result.status == "interaction_required":
            raise ValueError("interaction response did not resolve the request")
        await self._mark_tool_progress(
            run_id,
            call_id=result.call_id,
            name=result.tool_name,
            status=result.status,
            output_summary=_public_output_summary(
                result.output, tool_name=result.tool_name
            ),
            error=result.error,
        )
        if response_entry is None:
            response_entry = await self.repository.commit_interaction_response(
                str(session.id),
                run_id=run_id,
                command_id=command_id,
                interaction_id=str(
                    response.get("request_id") or f"tool:{call.call_id}"
                ),
                response=response,
            )
            await self.publish(
                EntryCommittedEvent(entry=entry_contract(response_entry))
            )
        tool_entry = await self._append_message(
            str(session.id),
            run_id,
            role="tool",
            content=json.dumps(
                _tool_result_history_output(result),
                ensure_ascii=False,
                default=str,
            ),
            call_id=call.call_id,
            tool_name=result.tool_name,
            tool_status=result.status,
        )
        await self.publish(EntryCommittedEvent(entry=tool_entry))
        history_revision = tool_entry.sequence
        pending = checkpoint.get("pending_calls") or []
        if pending:
            in_flight_tools = [
                dict(item)
                for item in checkpoint.get("in_flight_tools") or []
                if isinstance(item, dict) and item.get("call_id") != call.call_id
            ]
            mark_started, mark_finished = self._tool_progress_callbacks(run_id)

            remaining = await workspace.execute_batch(
                tuple(_runtime_tool_call(item) for item in pending),
                cancellation=cancellation,
                on_start=mark_started,
                on_result=mark_finished,
            )
            for pending_result in remaining.results:
                if pending_result.status == "interaction_required":
                    interaction = pending_result.interaction
                    assert interaction is not None
                    current = await self.repository.get_run(run_id)
                    progress = (
                        [dict(item) for item in (current.tool_progress or [])]
                        if current is not None
                        else []
                    )
                    progress = _replace_tool_progress(
                        progress,
                        call_id=pending_result.call_id,
                        name=pending_result.tool_name,
                        status="interaction_required",
                    )
                    for pending_call in remaining.pending_calls:
                        progress = _replace_tool_progress(
                            progress,
                            call_id=pending_call.call_id,
                            name=pending_call.name,
                            status="pending",
                        )
                    waiting_call = _find_call(
                        tuple(_runtime_tool_call(item) for item in pending),
                        pending_result.call_id,
                    )
                    (
                        _,
                        request_entry,
                        waiting_run,
                    ) = await self.repository.commit_waiting_interaction(
                        str(session.id),
                        run_id=run_id,
                        request_payload={
                            "interaction_id": interaction.request_id,
                            "request": _interaction_dict(pending_result),
                        },
                        tool_progress=progress,
                        checkpoint={
                            **checkpoint,
                            "phase": "interaction",
                            "history_revision": history_revision,
                            "in_flight_tools": in_flight_tools,
                            "waiting_call": _tool_call_dict(waiting_call),
                            "pending_calls": [
                                _tool_call_dict(pending_call)
                                for pending_call in remaining.pending_calls
                            ],
                            "interaction": _interaction_dict(pending_result),
                        },
                    )
                    await self.publish(RunUpdatedEvent(run=run_view(waiting_run)))
                    await self.publish(
                        ToolUpdatedEvent(
                            run_id=run_id,
                            tool=_tool_progress_view(
                                waiting_run, pending_result.call_id
                            ),
                        )
                    )
                    await self.publish(
                        EntryCommittedEvent(entry=entry_contract(request_entry))
                    )
                    await self.publish(
                        InteractionRequestedEvent(
                            run_id=run_id,
                            interaction=pending_interaction_entry_view(request_entry),
                        )
                    )
                    return
                pending_entry = await self._append_message(
                    str(session.id),
                    run_id,
                    role="tool",
                    content=json.dumps(
                        pending_result.output, ensure_ascii=False, default=str
                    ),
                    call_id=pending_result.call_id,
                    tool_name=pending_result.tool_name,
                    tool_status=pending_result.status,
                )
                await self.publish(EntryCommittedEvent(entry=pending_entry))
                history_revision = pending_entry.sequence
                in_flight_tools = [
                    item
                    for item in in_flight_tools
                    if item.get("call_id") != pending_result.call_id
                ]
        await self.repository.update_run(
            run_id,
            checkpoint=create_checkpoint(
                harness_version=HARNESS_VERSION,
                phase="model",
                history_revision=history_revision,
                continuation=(
                    checkpoint.get("continuation")
                    if isinstance(checkpoint.get("continuation"), dict)
                    else None
                ),
            ),
            tool_progress=None,
        )
        await self.run(run_id, cancellation)

    async def _resume_recovery_interaction(
        self,
        *,
        run,
        session,
        checkpoint: dict[str, Any],
        response: dict[str, Any],
        cancellation: asyncio.Event,
        command_id: str | None,
    ) -> None:
        choice = response.get("choice")
        if choice not in {"inspect", "retry", "cancel"}:
            raise ValueError("invalid recovery choice")
        interaction_id = str(response.get("request_id") or "recovery")
        call_data = checkpoint.get("waiting_call")
        if not isinstance(call_data, dict):
            raise ValueError("recovery interaction has no tool call")
        call = _runtime_tool_call(call_data)
        if choice == "retry":
            workspace = self.workspace_factory(session, str(run.id))
            replay_policy = _replay_policy(workspace, call.name)
            retry_fingerprint = None
            if call.name == "bash":
                retry_fingerprint = await _await_if_needed(
                    workspace.approval_assessment_fingerprint(call)
                )
            (
                response_entry,
                durable_run,
            ) = await self.repository.begin_approved_tool_execution(
                str(session.id),
                run_id=str(run.id),
                interaction_id=interaction_id,
                response=response,
                call=_tool_call_dict(call),
                replay_policy=replay_policy,
                command_id=command_id,
            )
            checkpoint = dict(durable_run.checkpoint or {})
            await self.publish(RunUpdatedEvent(run=run_view(durable_run)))
            await self.publish(
                ToolUpdatedEvent(
                    run_id=str(run.id),
                    tool=_tool_progress_view(durable_run, call.call_id),
                )
            )
        else:
            response_entry = await self.repository.commit_interaction_response(
                str(session.id),
                run_id=str(run.id),
                command_id=command_id,
                interaction_id=interaction_id,
                response=response,
            )
        await self.publish(EntryCommittedEvent(entry=entry_contract(response_entry)))
        if choice == "cancel":
            await self._cancel(str(run.id))
            return
        if choice == "retry":
            result = await workspace.execute(
                call,
                cancellation=cancellation,
                interaction_response=(
                    {
                        "request_id": f"tool:{run.id}:{call.call_id}",
                        "approved": True,
                        "assessment_fingerprint": retry_fingerprint,
                    }
                    if retry_fingerprint is not None
                    else None
                ),
            )
            if result.status == "interaction_required":
                raise ValueError("recovery retry did not resolve tool approval")
            output = _tool_result_history_output(result)
        else:
            output = {
                "recovery": f"unknown {call.name} effect was not replayed",
                "next_step": "inspect the current workspace state before continuing",
            }
        tool_entry = await self._append_message(
            str(session.id),
            str(run.id),
            role="tool",
            content=json.dumps(output, ensure_ascii=False, default=str),
            call_id=call.call_id,
            tool_name=call.name,
            is_error=choice == "retry" and result.status != "completed",
            tool_status=(result.status if choice == "retry" else "completed"),
        )
        await self.publish(EntryCommittedEvent(entry=tool_entry))
        waiting, history_revision = await self._resume_remaining_recovery_tools(
            session=session,
            run_id=str(run.id),
            checkpoint=checkpoint,
            completed_call_id=call.call_id,
            history_revision=tool_entry.sequence,
            cancellation=cancellation,
        )
        if waiting:
            return
        await self.repository.update_run(
            str(run.id),
            status="running",
            phase="model",
            checkpoint=create_checkpoint(
                harness_version=HARNESS_VERSION,
                phase="model",
                history_revision=history_revision,
            ),
        )
        await self.run(str(run.id), cancellation)

    async def _resume_remaining_recovery_tools(
        self,
        *,
        session,
        run_id: str,
        checkpoint: dict[str, Any],
        completed_call_id: str,
        history_revision: int,
        cancellation: asyncio.Event,
    ) -> tuple[bool, int]:
        remaining = [
            dict(item)
            for item in checkpoint.get("in_flight_tools") or []
            if isinstance(item, dict) and item.get("call_id") != completed_call_id
        ]
        if not remaining:
            return False, history_revision
        workspace = self.workspace_factory(session, run_id)
        for index, item in enumerate(remaining):
            call = ToolCall(
                call_id=str(item["call_id"]),
                name=str(item["name"]),
                arguments=dict(item.get("arguments") or {}),
            )
            policy = str(item.get("replay_policy") or "never")
            if policy == "never":
                await self._wait_for_recovery_choice(
                    session=session,
                    run_id=run_id,
                    checkpoint=checkpoint,
                    remaining=remaining[index:],
                    workspace=workspace,
                    call=call,
                    history_revision=history_revision,
                    message=(
                        "The previous process stopped after this tool may have started "
                        "but before its result was saved. It will not be run again "
                        "automatically."
                    ),
                )
                return True, history_revision
            await self._mark_tool_progress(
                run_id,
                call_id=call.call_id,
                name=call.name,
                status="running",
            )
            result = (
                await workspace.verify_recovery(call)
                if policy == "verify"
                else await workspace.execute(call, cancellation=cancellation)
            )
            if result.status == "interaction_required":
                await self._wait_for_recovery_choice(
                    session=session,
                    run_id=run_id,
                    checkpoint=checkpoint,
                    remaining=remaining[index:],
                    workspace=workspace,
                    call=call,
                    history_revision=history_revision,
                    message=(
                        f"BioinfoFlow could not prove whether the interrupted "
                        f"{call.name} operation changed the target."
                    ),
                )
                return True, history_revision
            tool_entry = await self._append_message(
                str(session.id),
                run_id,
                role="tool",
                content=json.dumps(
                    _tool_result_history_output(result),
                    ensure_ascii=False,
                    default=str,
                ),
                call_id=call.call_id,
                tool_name=result.tool_name,
                is_error=result.status != "completed",
                tool_status=result.status,
            )
            history_revision = tool_entry.sequence
            await self.publish(EntryCommittedEvent(entry=tool_entry))
            await self._mark_tool_progress(
                run_id,
                call_id=result.call_id,
                name=result.tool_name,
                status=result.status,
                output_summary=_public_output_summary(
                    result.output, tool_name=result.tool_name
                ),
                error=result.error,
            )
        return False, history_revision

    async def _wait_for_recovery_choice(
        self,
        *,
        session,
        run_id: str,
        checkpoint: dict[str, Any],
        remaining: list[dict[str, Any]],
        workspace: WorkspaceRuntime,
        call: ToolCall,
        history_revision: int,
        message: str,
    ) -> None:
        interaction_id = f"recovery:{call.call_id}"
        request = _recovery_request(call, message=message)
        waiting_checkpoint = {
            **checkpoint,
            "phase": "interaction",
            "history_revision": history_revision,
            "in_flight_tools": remaining,
            "waiting_call": _tool_call_dict(call),
            "recovery_interaction": request,
        }
        notice, request_entry, _ = await self.repository.commit_waiting_interaction(
            str(session.id),
            run_id=run_id,
            notice_payload={
                "code": "unknown_tool_effect",
                "message": message,
                "details": {"interaction_id": interaction_id},
            },
            request_payload={
                "interaction_id": interaction_id,
                "request": request,
            },
            checkpoint=waiting_checkpoint,
            tool_progress=[
                _recovery_tool_progress(
                    call_id=str(item.get("call_id") or ""),
                    name=str(item.get("name") or "unknown"),
                    arguments=dict(item.get("arguments") or {}),
                    spec=workspace.tool_spec(str(item.get("name") or "unknown")),
                    group_id=str(item.get("group_id") or _missing_group_id(item)),
                    execution_mode=str(item.get("execution_mode") or "serial"),
                    status=(
                        "interaction_required"
                        if item.get("call_id") == call.call_id
                        else "pending"
                    ),
                )
                for item in remaining
            ],
        )
        assert notice is not None
        await self.publish(EntryCommittedEvent(entry=entry_contract(notice)))
        await self.publish(EntryCommittedEvent(entry=entry_contract(request_entry)))
        await self.publish(
            InteractionRequestedEvent(
                run_id=run_id,
                interaction=pending_interaction_entry_view(request_entry),
            )
        )

    async def _invoke(
        self, *, run_id, iteration, session, context, workspace, cancellation
    ):
        if self.model_runtime_resolver is None:
            target = model_target_from_snapshot(session.model_snapshot)
            resolved = dict(session.model_snapshot or {})
        else:
            resolved = await self.model_runtime_resolver(session)
            target = model_target_from_resolved(resolved)
        capabilities = resolved_runtime_capabilities(resolved)
        strategy = resolved_runtime_strategy(resolved)
        current = await self.repository.get_run(run_id)
        checkpoint = current.checkpoint if current is not None else None
        input_items = (
            *context.input_items,
            *_private_control_input_parts(checkpoint),
        )
        if not capabilities.supports_vision and any(
            isinstance(item, ImagePart) for item in input_items
        ):
            raise ModelVisionUnsupportedError(
                "The selected model does not support image input."
            )
        reasoning_enabled = capabilities.supports_reasoning and strategy.allow_thinking
        continuation = responses_continuation_from_checkpoint(
            checkpoint,
            target=target,
            input_items=input_items,
        )
        invocation = ModelInvocation(
            target=target,
            instructions=context.instructions,
            input_items=input_items,
            tools=(
                workspace.model_tools
                if capabilities.supports_tools and strategy.allow_tools
                else ()
            ),
            stream=capabilities.supports_streaming and strategy.use_streaming,
            max_output_tokens=strategy.max_tokens or self.limits.max_output_tokens,
            reasoning=ReasoningRequest(
                enabled=reasoning_enabled,
                effort=(strategy.reasoning_effort or "medium")
                if reasoning_enabled
                else None,
            ),
            continuation=continuation,
        )
        attempts = 0
        while True:
            response = _ModelResponse()
            semantic = False
            exchange_id = None
            recorder = self.model_exchange_recorder
            if recorder is not None:
                exchange_id = await capture_exchange_best_effort(
                    recorder,
                    "start",
                    lambda: recorder.start(
                        session_id=str(session.id),
                        run_id=run_id,
                        iteration=iteration,
                        attempt=attempts + 1,
                        context_through_sequence=context.history_revision,
                        provider=target.provider_kind,
                        model=target.model_name,
                        wire_protocol=target.wire_protocol,
                        context_snapshot=_trace_context_snapshot(
                            context,
                            input_items=input_items,
                            tools=invocation.tools,
                            max_context_tokens=_optional_positive_int(
                                resolved.get("context_window_tokens")
                            ),
                        ),
                    ),
                )
            attempt_invocation = replace(invocation, exchange_id=exchange_id)
            try:
                async for event in _model_events_with_timeout(
                    self.model_gateway.invoke(attempt_invocation),
                    timeout_seconds=self.limits.model_attempt_timeout_seconds,
                ):
                    if cancellation.is_set():
                        if exchange_id is not None:
                            assert recorder is not None
                            await capture_exchange_best_effort(
                                recorder,
                                "fail",
                                lambda: recorder.fail(
                                    exchange_id,
                                    code="cancelled",
                                    message="Model exchange was cancelled.",
                                ),
                            )
                        return _ModelResponse(cancelled=True)
                    if isinstance(event, TextDelta):
                        semantic = True
                        start_offset = len(response.text)
                        response.text += event.text
                        end_offset = len(response.text)
                        await self.repository.update_run(
                            run_id,
                            draft=_assistant_draft_payload(
                                run_id,
                                text=response.text,
                                reasoning_traces=response.reasoning_traces,
                            ),
                        )
                        await self.publish(
                            AssistantDeltaEvent(
                                run_id=run_id,
                                draft_id=f"draft:{run_id}",
                                part_id=f"draft:{run_id}:text",
                                part_type="text",
                                delta=event.text,
                                start_offset=start_offset,
                                end_offset=end_offset,
                            )
                        )
                    elif isinstance(event, ReasoningDelta):
                        semantic = True
                        segment_index, start_offset, end_offset = (
                            response.add_reasoning(event)
                        )
                        segment = response.reasoning_traces[segment_index]
                        await self.repository.update_run(
                            run_id,
                            draft=_assistant_draft_payload(
                                run_id,
                                text=response.text,
                                reasoning_traces=response.reasoning_traces,
                            ),
                        )
                        await self.publish(
                            AssistantDeltaEvent(
                                run_id=run_id,
                                draft_id=f"draft:{run_id}",
                                part_id=f"draft:{run_id}:reasoning:{segment_index}",
                                part_type="reasoning_trace",
                                delta=event.text,
                                start_offset=start_offset,
                                end_offset=end_offset,
                                provider=segment.provider,
                                model=segment.model,
                                source=segment.source,
                                truncated=segment.truncated,
                                started_at=segment.started_at,
                            )
                        )
                    elif isinstance(event, ToolCallDelta):
                        semantic = True
                        response.tool_deltas.append(event)
                    elif isinstance(event, UsageReport):
                        response.usage = {
                            "input_tokens": event.input_tokens,
                            "output_tokens": event.output_tokens,
                            "total_tokens": event.total_tokens,
                            "cached_input_tokens": event.cached_input_tokens,
                            "reasoning_tokens": event.reasoning_tokens,
                        }
                    elif isinstance(event, CompletionMetadata):
                        response.provider_response_id = event.response_id
                        response.finish_reason = event.finish_reason
                        response.continuation = (
                            event.continuation.to_private_dict()
                            if event.continuation is not None
                            else None
                        )
                response.tool_calls = _assemble_tool_calls(response.tool_deltas)
                current = await self.repository.get_run(run_id)
                usage = dict(current.token_usage or {}) if current else {}
                if response.usage:
                    for key, value in response.usage.items():
                        if value is not None:
                            usage[key] = int(usage.get(key) or 0) + value
                await self.repository.update_run(
                    run_id,
                    token_usage=usage or None,
                    draft=_assistant_draft_payload(
                        run_id,
                        text=response.text,
                        reasoning_traces=response.reasoning_traces,
                    ),
                )
                if exchange_id is not None:
                    assert recorder is not None
                    await capture_exchange_best_effort(
                        recorder,
                        "complete",
                        lambda: recorder.complete(
                            exchange_id,
                            usage=response.usage,
                            provider_response_id=response.provider_response_id,
                            finish_reason=response.finish_reason,
                        ),
                    )
                return response
            except TimeoutError as exc:
                if exchange_id is not None:
                    assert recorder is not None
                    await capture_exchange_best_effort(
                        recorder,
                        "fail",
                        lambda: recorder.fail(
                            exchange_id,
                            code="timeout",
                            message="Model exchange timed out.",
                        ),
                    )
                attempts += 1
                if semantic or attempts >= self.limits.retry_attempts:
                    raise ModelAttemptTimeoutError(
                        "Model stream exceeded the per-attempt timeout."
                    ) from exc
                delay = min(
                    settings.agent_retry_base_delay_seconds * (2 ** (attempts - 1)),
                    settings.agent_retry_max_delay_seconds,
                )
                await asyncio.sleep(delay)
            except ModelError as exc:
                if exchange_id is not None:
                    assert recorder is not None
                    error_code = exc.category
                    error_message = exc.message
                    error_details = {
                        "http_status": exc.http_status,
                        "provider_code": exc.provider_code,
                        "retryable": exc.retryable,
                        "retry_after_seconds": exc.retry_after_seconds,
                        "request_id": exc.request_id,
                    }
                    await capture_exchange_best_effort(
                        recorder,
                        "fail",
                        lambda: recorder.fail(
                            exchange_id,
                            code=error_code,
                            message=error_message,
                            details=error_details,
                        ),
                    )
                attempts += 1
                if (
                    is_context_overflow(exc)
                    or semantic
                    or not exc.retryable
                    or not exc.replay_safe
                    or attempts >= self.limits.retry_attempts
                ):
                    raise
                delay = exc.retry_after_seconds or min(
                    settings.agent_retry_base_delay_seconds * (2 ** (attempts - 1)),
                    settings.agent_retry_max_delay_seconds,
                )
                await asyncio.sleep(delay)
            except Exception as exc:
                if exchange_id is not None:
                    assert recorder is not None
                    exception_type = type(exc).__name__
                    await capture_exchange_best_effort(
                        recorder,
                        "fail",
                        lambda: recorder.fail(
                            exchange_id,
                            code="internal_error",
                            message="Model exchange failed unexpectedly.",
                            details={"exception_type": exception_type},
                        ),
                    )
                raise

    async def _build_context(self, session, entries) -> Any:
        mappings = tuple(_history_mapping(entry) for entry in entries)
        attachment_ids = _attachment_ids(mappings)
        attachment_parts_by_id = await AgentHarnessAttachmentService(
            self.repository.db
        ).model_parts_for_ids(
            attachment_ids,
            session_id=str(session.id),
            workspace_id=str(session.workspace_id),
            user_id=session.user_id,
        )
        return self.context.build(
            prompt_snapshot=session.prompt_snapshot,
            entries=mappings,
            attachment_parts_by_id=attachment_parts_by_id,
            settings_revision=session.settings_revision,
        )

    async def _append_message(
        self,
        session_id: str,
        run_id: str,
        *,
        role: str,
        content: str,
        call_id: str | None = None,
        tool_name: str | None = None,
        is_error: bool = False,
        tool_status: str | None = None,
        reasoning_traces: list[_ReasoningTraceSegment] | None = None,
        entry_id: str | None = None,
        tool_calls: list[dict[str, Any]] | None = None,
    ):
        message_id = entry_id or str(uuid4())
        parts: list[dict[str, Any]] = []
        if role == "tool":
            if call_id is None:
                raise ValueError("tool message requires call_id")
            run = await self.repository.get_run(run_id)
            progress = (
                next(
                    (
                        item
                        for item in (run.tool_progress or [])
                        if isinstance(item, dict) and item.get("call_id") == call_id
                    ),
                    {},
                )
                if run is not None
                else {}
            )
            try:
                private_output = json.loads(content)
            except (TypeError, ValueError):
                private_output = content
            parts.append(
                {
                    "id": f"tool-result:{call_id}",
                    "type": "tool_result",
                    "call_id": call_id,
                    "status": tool_status or ("failed" if is_error else "completed"),
                    "summary": _public_output_summary(
                        private_output, tool_name=tool_name
                    ),
                    "output": {"type": "text", "text": content},
                    "started_at": progress.get("started_at"),
                    "completed_at": progress.get("completed_at"),
                    "error": content if is_error else None,
                }
            )
        else:
            completed_at = datetime.now(timezone.utc)
            parts.extend(
                trace.public_part(
                    part_id=f"message:{message_id}:reasoning:{index}",
                    completed_at=completed_at,
                )
                for index, trace in enumerate(reasoning_traces or [])
                if trace.text
            )
            if content:
                parts.append(
                    {
                        "id": f"message:{message_id}:text",
                        "type": "text",
                        "text": content,
                    }
                )
            parts.extend(
                {"id": f"tool-call:{call['call_id']}", "type": "tool_call", **call}
                for call in tool_calls or []
            )
        entry = await self.repository.append_entry(
            session_id,
            run_id=run_id,
            entry_type="message",
            entry_id=message_id,
            payload={
                "role": role,
                "parts": parts,
            },
        )
        return entry_contract(entry)

    async def apply_steers(self, run_id: str, session_id: str) -> int:
        entries = await self.repository.commit_steers_to_history(
            session_id, run_id=run_id
        )
        for entry in entries:
            await self.publish(EntryCommittedEvent(entry=entry_contract(entry)))
        return len(entries)

    async def _update(self, run_id: str, **changes: Any) -> None:
        run = await self.repository.update_run(run_id, **changes)
        await self.publish(RunUpdatedEvent(run=run_view(run)))

    async def _mark_tool_progress(
        self,
        run_id: str,
        *,
        call_id: str,
        name: str,
        status: str,
        group_id: str | None = None,
        execution_mode: ToolExecutionMode | None = None,
        arguments: dict[str, Any] | None = None,
        output_summary: str | None = None,
        error: str | None = None,
    ) -> ToolProgressView:
        view = await self.repository.update_tool_progress(
            run_id,
            call_id=call_id,
            name=name,
            status=status,
            group_id=group_id,
            execution_mode=execution_mode,
            arguments=arguments,
            output_summary=output_summary,
            error=error,
        )
        await self.publish(ToolUpdatedEvent(run_id=run_id, tool=view))
        return view

    def _tool_progress_callbacks(
        self,
        run_id: str,
        *,
        group_id: str | None = None,
        execution_mode: ToolExecutionMode | None = None,
    ):
        async def mark_started(call: ToolCall) -> None:
            await self._mark_tool_progress(
                run_id,
                call_id=call.call_id,
                name=call.name,
                status="running",
                group_id=group_id,
                execution_mode=execution_mode,
                arguments=call.arguments,
            )

        async def mark_finished(result: ToolResult) -> None:
            await self._mark_tool_progress(
                run_id,
                call_id=result.call_id,
                name=result.tool_name,
                status=result.status,
                output_summary=_public_output_summary(
                    result.output, tool_name=result.tool_name
                ),
                error=result.error,
            )

        return mark_started, mark_finished

    async def _cancel(self, run_id: str) -> None:
        run = await self.repository.get_run(run_id)
        reason = (
            str(run.cancel_reason or "cancelled") if run is not None else "cancelled"
        )
        try:
            await self._update(
                run_id,
                status="cancelled",
                phase=None,
                termination_reason=reason,
            )
        except ValueError:
            run = await self.repository.get_run(run_id)
            if run is None or run.status not in {"completed", "failed", "cancelled"}:
                raise

    async def _stop_if_budget_exceeded(self, run_id: str) -> bool:
        run = await self.repository.get_run(run_id)
        if run is None:
            raise LookupError(f"agent run not found: {run_id}")
        code: str | None = None
        message: str | None = None
        if run.started_at is not None:
            started_at = run.started_at
            if started_at.tzinfo is None:
                started_at = started_at.replace(tzinfo=timezone.utc)
            elapsed = (datetime.now(timezone.utc) - started_at).total_seconds()
            if elapsed >= self.limits.run_timeout_seconds:
                code = "run_timeout_exceeded"
                message = (
                    f"Agent Run exceeded its {self.limits.run_timeout_seconds:g}-second "
                    "wall-clock budget."
                )
        usage = dict(run.token_usage or {})
        total_tokens = int(usage.get("total_tokens") or 0)
        if code is None and total_tokens >= self.limits.run_token_budget:
            code = "token_budget_exceeded"
            message = (
                f"Agent Run used {total_tokens} tokens, reaching its "
                f"{self.limits.run_token_budget}-token budget."
            )
        if code is None or message is None:
            return False
        session_id = str(run.session_id)
        notice = await self.repository.append_entry(
            session_id,
            run_id=run_id,
            entry_type="notice",
            payload={
                "code": code,
                "message": message,
                "details": (
                    {"limit_seconds": self.limits.run_timeout_seconds}
                    if code == "run_timeout_exceeded"
                    else {
                        "total_tokens": total_tokens,
                        "token_budget": self.limits.run_token_budget,
                    }
                ),
            },
        )
        await self.publish(EntryCommittedEvent(entry=entry_contract(notice)))
        await self._fail(run_id, code, message)
        return True

    async def _stop_if_cancel_requested(self, run_id: str) -> bool:
        return await self.repository.get_run_cancellation(run_id) is not None

    async def _fail(
        self, run_id: str, code: str, message: str, *, exc: Exception | None = None
    ) -> None:
        try:
            await self._update(
                run_id,
                status="failed",
                phase=None,
                termination_reason=code,
                error={
                    "code": code,
                    "message": message,
                    "type": type(exc).__name__ if exc else None,
                },
            )
        except ValueError:
            run = await self.repository.get_run(run_id)
            if run is None or run.status not in {"completed", "failed", "cancelled"}:
                raise


async def _model_events_with_timeout(
    events: AsyncIterator[Any],
    *,
    timeout_seconds: float,
) -> AsyncIterator[Any]:
    """Limit provider wait time without cancelling durable event persistence."""

    iterator = events.__aiter__()
    remaining = timeout_seconds
    try:
        while True:
            if remaining <= 0:
                raise TimeoutError
            started_wait = asyncio.get_running_loop().time()
            try:
                async with asyncio.timeout(remaining):
                    event = await anext(iterator)
            except StopAsyncIteration:
                return
            finally:
                remaining -= asyncio.get_running_loop().time() - started_wait
            yield event
    finally:
        await aclose_async_iterator(iterator)


@dataclass
class _ReasoningTraceSegment:
    provider: str
    model: str
    source: str
    truncated: bool = False
    text: str = ""
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def identity(self) -> tuple[str, str, str, bool]:
        return (self.provider, self.model, self.source, self.truncated)

    def public_part(
        self,
        *,
        part_id: str,
        completed_at: datetime | None,
    ) -> dict[str, Any]:
        return {
            "id": part_id,
            "type": "reasoning_trace",
            "text": self.text,
            "provider": self.provider,
            "model": self.model,
            "source": self.source,
            "truncated": self.truncated,
            "started_at": self.started_at.isoformat(),
            "completed_at": completed_at.isoformat() if completed_at else None,
        }


@dataclass
class _ModelResponse:
    text: str = ""
    reasoning_traces: list[_ReasoningTraceSegment] = None  # type: ignore[assignment]
    tool_deltas: list[ToolCallDelta] = None  # type: ignore[assignment]
    tool_calls: tuple[ToolCall, ...] = ()
    usage: dict[str, int | None] | None = None
    continuation: dict[str, Any] | None = None
    provider_response_id: str | None = None
    finish_reason: str | None = None
    cancelled: bool = False

    def __post_init__(self) -> None:
        if self.reasoning_traces is None:
            self.reasoning_traces = []
        if self.tool_deltas is None:
            self.tool_deltas = []

    def add_reasoning(self, event: ReasoningDelta) -> tuple[int, int, int]:
        identity = (
            event.provider,
            event.model,
            event.source,
            event.truncated,
        )
        if self.reasoning_traces and self.reasoning_traces[-1].identity == identity:
            segment = self.reasoning_traces[-1]
        else:
            segment = _ReasoningTraceSegment(
                provider=event.provider,
                model=event.model,
                source=event.source,
                truncated=event.truncated,
            )
            self.reasoning_traces.append(segment)
        start_offset = len(segment.text)
        segment.text += event.text
        return len(self.reasoning_traces) - 1, start_offset, len(segment.text)


def _trace_context_snapshot(
    context: Any,
    *,
    input_items: tuple[Any, ...],
    tools: tuple[Any, ...],
    max_context_tokens: int | None,
) -> dict[str, Any]:
    characters = {
        "system": len(context.instructions),
        "user": 0,
        "context": 0,
        "assistant": 0,
        "tool": 0,
    }
    for item in input_items:
        if isinstance(item, TextPart):
            category = "assistant" if item.phase is not None else "user"
            characters[category] += len(item.text)
        elif isinstance(item, ReasoningPart):
            characters["assistant"] += len(item.text)
        elif isinstance(item, ImagePart):
            characters["user"] += len(item.data)
        elif isinstance(item, ToolCallPart):
            characters["tool"] += len(
                json.dumps(
                    {
                        "call_id": item.call_id,
                        "name": item.name,
                        "arguments": item.arguments,
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                    default=str,
                )
            )
        elif isinstance(item, ToolResultPart):
            characters["tool"] += len(item.output)
    if tools:
        characters["tool"] += len(
            json.dumps(
                [
                    {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.parameters,
                    }
                    for tool in tools
                ],
                ensure_ascii=False,
                separators=(",", ":"),
                default=str,
            )
        )
    return {
        "compacted": bool(context.compacted),
        "max_context_tokens": max_context_tokens,
        "composition": [
            {"category": category, "characters": count, "tokens": None}
            for category, count in characters.items()
            if count > 0
        ],
    }


def _optional_positive_int(value: Any) -> int | None:
    return (
        value
        if isinstance(value, int) and not isinstance(value, bool) and value > 0
        else None
    )


def _advance_response_continuation(
    response: _ModelResponse,
) -> dict[str, Any] | None:
    continuation = ResponsesContinuation.from_private_dict(response.continuation)
    if continuation is None:
        return response.continuation
    committed_parts = (
        *(
            ReasoningPart(text=trace.text, source=trace.source)
            for trace in response.reasoning_traces
            if trace.text
        ),
        *((TextPart(response.text, phase="final_answer"),) if response.text else ()),
        *(
            ToolCallPart(
                call_id=call.call_id,
                name=call.name,
                arguments=call.arguments,
            )
            for call in response.tool_calls
        ),
    )
    return continuation.advance_canonical_input(committed_parts).to_private_dict()


def _private_control_input_parts(
    checkpoint: Mapping[str, Any] | None,
) -> tuple[ToolCallPart | ToolResultPart, ...]:
    if not isinstance(checkpoint, Mapping):
        return ()
    raw = checkpoint.get("control_input")
    if not isinstance(raw, list):
        return ()
    parts: list[ToolCallPart | ToolResultPart] = []
    for index in range(0, len(raw), 2):
        pair = raw[index : index + 2]
        if len(pair) != 2:
            return ()
        call, result = pair
        if not isinstance(call, Mapping) or not isinstance(result, Mapping):
            return ()
        call_id = call.get("call_id")
        name = call.get("name")
        arguments = call.get("arguments")
        output = result.get("output")
        if not (
            call.get("type") == "tool_call"
            and result.get("type") == "tool_result"
            and isinstance(call_id, str)
            and call_id
            and result.get("call_id") == call_id
            and isinstance(name, str)
            and name
            and isinstance(arguments, Mapping)
            and isinstance(output, str)
        ):
            return ()
        parts.extend(
            (
                ToolCallPart(
                    call_id=call_id,
                    name=name,
                    arguments=dict(arguments),
                ),
                ToolResultPart(
                    call_id=call_id,
                    output=output,
                    is_error=bool(result.get("is_error", False)),
                ),
            )
        )
    return tuple(parts)


def _assemble_tool_calls(events: list[ToolCallDelta]) -> tuple[ToolCall, ...]:
    by_index: dict[int, dict[str, Any]] = {}
    for event in events:
        current = by_index.setdefault(
            event.index, {"call_id": None, "name": None, "arguments": ""}
        )
        current["call_id"] = event.call_id or current["call_id"]
        current["name"] = event.name or current["name"]
        current["arguments"] += event.arguments_delta
    calls: list[ToolCall] = []
    for index, data in sorted(by_index.items()):
        name = data["name"]
        if not isinstance(name, str) or not name:
            name = "unknown"
        raw = data["arguments"] or "{}"
        try:
            arguments = json.loads(raw)
            if not isinstance(arguments, dict):
                raise ValueError("tool arguments must be an object")
        except (json.JSONDecodeError, ValueError):
            arguments = {"_malformed_arguments": raw}
        calls.append(
            ToolCall(
                call_id=str(data["call_id"] or f"tool-{index}"),
                name=name,
                arguments=arguments,
            )
        )
    return tuple(calls)


def _call_signature(calls: tuple[ToolCall, ...]) -> str:
    return json.dumps(
        [(call.name, call.arguments) for call in calls],
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )


def _history_mapping(entry) -> dict[str, Any]:
    return {
        "sequence": entry.sequence,
        "entry_type": entry.type,
        "payload": entry.payload,
    }


def _attachment_ids(entries: tuple[dict[str, Any], ...]) -> list[str]:
    ordered_entries = sorted(entries, key=lambda entry: int(entry.get("sequence") or 0))
    covered_through = _latest_compaction_through(ordered_entries)
    ordered: list[str] = []
    seen: set[str] = set()
    for entry in ordered_entries:
        if int(entry.get("sequence") or 0) <= covered_through:
            continue
        payload = entry.get("payload")
        if not isinstance(payload, dict):
            continue
        raw_ids = [
            part.get("attachment_id")
            for part in payload.get("parts") or []
            if isinstance(part, dict)
            and part.get("type") in {"attachment_ref", "file_ref", "directory_ref"}
            and part.get("attachment_id") is not None
        ]
        for raw_id in raw_ids:
            attachment_id = str(raw_id)
            if attachment_id and attachment_id not in seen:
                seen.add(attachment_id)
                ordered.append(attachment_id)
    return ordered


def _latest_compaction_through(entries: list[dict[str, Any]]) -> int:
    for entry in reversed(entries):
        if entry.get("entry_type", entry.get("type")) != "compaction":
            continue
        payload = entry.get("payload")
        if not isinstance(payload, dict):
            continue
        summary = payload.get("summary")
        through_sequence = payload.get("through_sequence")
        sequence = int(entry.get("sequence") or 0)
        if (
            isinstance(summary, str)
            and summary.strip()
            and isinstance(through_sequence, int)
            and not isinstance(through_sequence, bool)
            and 0 <= through_sequence < sequence
        ):
            return through_sequence
    return 0


def _tool_result_dict(result: ToolResult) -> dict[str, Any]:
    return {
        "tool_name": result.tool_name,
        "output": result.output,
        "error": result.error,
        "replay_policy": result.replay_policy,
    }


def _interaction_dict(result: ToolResult) -> dict[str, Any]:
    interaction = result.interaction
    if interaction is None:
        return {}
    payload = {
        "request_id": interaction.request_id,
        "call_id": interaction.call_id,
        "kind": interaction.kind,
        "tool_name": result.tool_name,
        "summary": interaction.summary,
        "input_preview": interaction.input_preview,
        "questions": list(interaction.questions),
        "risk": interaction.risk,
        "target": interaction.target,
    }
    if interaction.kind == "confirmation":
        payload["allowed_responses"] = list(
            interaction.allowed_responses or ("approve", "reject")
        )
    return payload


def checkpoint_interaction_id(checkpoint: dict[str, Any]) -> str:
    interaction = checkpoint.get("interaction")
    if isinstance(interaction, dict):
        request_id = interaction.get("request_id")
        if isinstance(request_id, str) and request_id:
            return request_id
    waiting_call = checkpoint.get("waiting_call")
    if isinstance(waiting_call, dict):
        call_id = waiting_call.get("call_id")
        if isinstance(call_id, str) and call_id:
            prefix = "recovery" if checkpoint.get("recovery_interaction") else "tool"
            return f"{prefix}:{call_id}"
    raise ValueError("waiting interaction has no interaction id")


def _recovery_request(call: ToolCall, *, message: str) -> dict[str, Any]:
    return {
        "kind": "recovery",
        "call_id": call.call_id,
        "tool_name": call.name,
        "message": message,
        "message_code": "unknown_tool_effect",
        "message_params": {"tool_name": call.name},
        "options": [
            {
                "id": "inspect",
                "label": "Inspect state",
                "description": "Continue without replaying the operation.",
            },
            {
                "id": "retry",
                "label": "Retry operation",
                "description": "Explicitly allow the operation to run again.",
            },
            {
                "id": "cancel",
                "label": "Cancel run",
                "description": "Stop without replaying the operation.",
            },
        ],
    }


def _find_call(calls: tuple[ToolCall, ...], call_id: str) -> ToolCall:
    for call in calls:
        if call.call_id == call_id:
            return call
    raise LookupError(f"tool call not found: {call_id}")


def _tool_result_history_output(result: ToolResult) -> dict[str, Any]:
    output = dict(result.output)
    if result.status != "completed":
        output.setdefault("error", result.error)
    return output


def _tool_call_dict(call: ToolCall) -> dict[str, Any]:
    return {
        "call_id": call.call_id,
        "name": call.name,
        "arguments": call.arguments,
    }


def _runtime_tool_call(item: dict[str, Any]) -> ToolCall:
    return ToolCall(
        call_id=str(item.get("call_id") or ""),
        name=str(item.get("name") or "unknown"),
        arguments=dict(item.get("arguments") or {}),
    )


async def _await_if_needed(value: Any) -> Any:
    return await value if inspect.isawaitable(value) else value


def _assistant_draft_payload(
    run_id: str,
    *,
    text: str,
    reasoning_traces: list[_ReasoningTraceSegment] | None = None,
) -> dict[str, Any]:
    draft_id = f"draft:{run_id}"
    return {
        "id": draft_id,
        "run_id": run_id,
        "parts": [
            *(
                trace.public_part(
                    part_id=f"{draft_id}:reasoning:{index}",
                    completed_at=None,
                )
                | {"end_offset": len(trace.text)}
                for index, trace in enumerate(reasoning_traces or [])
                if trace.text
            ),
            {
                "id": f"{draft_id}:text",
                "type": "text",
                "text": text,
                "end_offset": len(text),
            },
        ],
    }


def _public_tool_call_dict(
    call: ToolCall,
    *,
    spec: ToolSpec | None,
    group_id: str,
    execution_mode: ToolExecutionMode,
) -> dict[str, Any]:
    projected = project_tool_view(
        spec=spec,
        call_id=call.call_id,
        name=call.name,
        arguments=call.arguments,
        status="pending",
        group_id=group_id,
        execution_mode=execution_mode,
    ).model_dump(
        mode="json",
        include={
            "call_id",
            "group_id",
            "execution_mode",
            "name",
            "display_name",
            "category",
            "summary",
            "arguments",
        },
    )
    projected["arguments"] = dict(call.arguments)
    return projected


def _tool_progress_dict(
    call: ToolCall,
    *,
    spec: ToolSpec | None,
    status: str,
    group_id: str,
    execution_mode: ToolExecutionMode,
) -> dict[str, Any]:
    return project_tool_view(
        spec=spec,
        call_id=call.call_id,
        name=call.name,
        arguments=call.arguments,
        status=status,
        group_id=group_id,
        execution_mode=execution_mode,
    ).model_dump(mode="json")


def _replace_tool_progress(
    progress: list[dict[str, Any]],
    *,
    call_id: str,
    name: str,
    status: str,
) -> list[dict[str, Any]]:
    replacement: dict[str, Any] | None = None
    for index, item in enumerate(progress):
        if item.get("call_id") == call_id:
            replacement = {
                **item,
                "name": name,
                "status": status,
                "revision": int(item.get("revision") or 0) + 1,
            }
            progress[index] = replacement
            break
    else:
        raise LookupError(f"tool progress not found: {call_id}")
    return progress


def _recovery_tool_progress(
    *,
    call_id: str,
    name: str,
    arguments: dict[str, Any],
    spec: ToolSpec | None,
    group_id: str,
    execution_mode: ToolExecutionMode,
    status: str,
) -> dict[str, Any]:
    return project_tool_view(
        spec=spec,
        call_id=call_id,
        name=name,
        arguments=arguments,
        status=status,
        group_id=group_id,
        execution_mode=execution_mode,
    ).model_dump(mode="json")


def _tool_progress_view(run: Any, call_id: str) -> ToolProgressView:
    for item in run.tool_progress or []:
        if isinstance(item, dict) and item.get("call_id") == call_id:
            return public_tool_progress_view(item)
    raise LookupError(f"tool progress not found: {call_id}")


def _checkpoint_replay_policy(checkpoint: dict[str, Any], call_id: str) -> str:
    for item in checkpoint.get("in_flight_tools") or []:
        if isinstance(item, dict) and item.get("call_id") == call_id:
            return str(item.get("replay_policy") or "never")
    return "never"


def _missing_group_id(item: dict[str, Any]) -> str:
    raise ValueError(
        f"tool call {item.get('call_id') or 'unknown'} has no owning assistant entry"
    )


def _replay_policy(workspace: WorkspaceRuntime, tool_name: str) -> str:
    for spec in workspace.tools:
        if spec.name == tool_name:
            return spec.replay_policy
    return "never"


__all__ = ["AgentLoop", "HARNESS_VERSION", "LoopLimits"]
