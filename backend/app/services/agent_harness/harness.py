from __future__ import annotations

import asyncio
import inspect
import json
from collections.abc import AsyncIterator, Callable
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from app.auth.agent_tokens import AgentTokenService
from app.config import settings
from app.repositories.agent_harness_repo import (
    AgentHarnessRepository,
)
from app.services.agent_harness.contracts import (
    AgentCommand,
    AgentEvent,
    CancelCommand,
    EntryCommittedEvent,
    InteractionRequestedEvent,
    MessageCommand,
    OpenSessionRequest,
    RespondCommand,
    RunUpdatedEvent,
    SessionSnapshot,
    SteerCommand,
    ToolProgressView,
    ToolUpdatedEvent,
)
from app.services.agent_harness.events import AgentEventHub
from app.services.agent_harness.loop import (
    AgentLoop,
    HARNESS_VERSION,
    LoopLimits,
    checkpoint_interaction_id,
)
from app.services.agent_harness.projection import (
    entry_contract,
    pending_interaction_entry_view,
    run_view,
)
from app.services.agent_harness.recovery import RecoveryPlanner, create_checkpoint
from app.services.agent_harness.tool_projection import (
    project_tool_view,
    public_output_summary as _public_output_summary,
)
from app.services.agent_harness.tools import ToolCall
from app.services.agent_harness.tools.specs import ToolSpec
from app.services.model_runtime.gateway import ModelGateway


class AgentHarness:
    """The complete BioinfoFlow agent behind one small product interface."""

    def __init__(
        self,
        repository: AgentHarnessRepository,
        *,
        model_gateway: Any,
        workspace_factory: Callable[[Any], Any],
        model_runtime_resolver: Callable[[Any], Any] | None = None,
        event_hub: AgentEventHub | None = None,
        limits: LoopLimits | None = None,
        token_service: AgentTokenService | None = None,
        tasks: dict[str, asyncio.Task[None]] | None = None,
        cancellations: dict[str, asyncio.Event] | None = None,
        run_tokens: dict[str, str] | None = None,
        execution_scheduler: Callable[[str, str, str, dict[str, Any] | None], None]
        | None = None,
        lease_owner: str | None = None,
    ) -> None:
        self.repository = repository
        self.event_hub = event_hub or AgentEventHub()
        self._tasks = tasks if tasks is not None else {}
        self._cancellations = cancellations if cancellations is not None else {}
        self.token_service = token_service
        self._run_tokens = run_tokens if run_tokens is not None else {}
        self._execution_scheduler = execution_scheduler
        self._lease_owner_id = lease_owner or f"in-process:{uuid4()}"
        original_workspace_factory = workspace_factory
        workspace_factory_parameters = len(
            inspect.signature(original_workspace_factory).parameters
        )

        def scoped_workspace_factory(session, run_id: str):
            if workspace_factory_parameters >= 3:
                workspace = original_workspace_factory(
                    session,
                    run_id,
                    self.repository.run_fence(run_id),
                )
            elif workspace_factory_parameters >= 2:
                workspace = original_workspace_factory(session, run_id)
            else:
                workspace = original_workspace_factory(session)

            async def fresh_bash_environment() -> dict[str, str]:
                await self._ensure_run_token(session, run_id, replace=True)
                token = self._run_tokens.pop(run_id)
                return {"BIOFLOW_AGENT_TOKEN": token}

            workspace.with_bash_environment_provider(fresh_bash_environment)
            return workspace

        self.loop = AgentLoop(
            repository,
            model_gateway=model_gateway,
            workspace_factory=scoped_workspace_factory,
            model_runtime_resolver=model_runtime_resolver,
            publish=self._publish_for_current_session,
            limits=limits,
        )
        self._publishing_session_id: str | None = None

    @classmethod
    def for_database(
        cls,
        db,
        *,
        model_gateway: Any | None = None,
        workspace_factory: Callable[[Any], Any],
        model_runtime_resolver: Callable[[Any], Any] | None = None,
        event_hub: AgentEventHub | None = None,
        limits: LoopLimits | None = None,
        tasks: dict[str, asyncio.Task[None]] | None = None,
        cancellations: dict[str, asyncio.Event] | None = None,
        run_tokens: dict[str, str] | None = None,
        execution_scheduler: Callable[[str, str, str, dict[str, Any] | None], None]
        | None = None,
        lease_owner: str | None = None,
    ) -> AgentHarness:
        return cls(
            AgentHarnessRepository(db),
            model_gateway=model_gateway or ModelGateway(),
            workspace_factory=workspace_factory,
            model_runtime_resolver=model_runtime_resolver,
            event_hub=event_hub,
            limits=limits,
            token_service=AgentTokenService(db),
            tasks=tasks,
            cancellations=cancellations,
            run_tokens=run_tokens,
            execution_scheduler=execution_scheduler,
            lease_owner=lease_owner,
        )

    def bind_run_fence(self, run_id: str, *, owner: str, generation: int) -> None:
        self.repository.bind_run_fence(run_id, owner=owner, generation=generation)

    async def open_session(self, request: OpenSessionRequest) -> SessionSnapshot:
        session = await self.repository.open_session(request)
        return await self.repository.snapshot(str(session.id))

    async def dispatch(self, session_id: str, command: AgentCommand) -> None:
        session = await self.repository.get_session(session_id)
        if session is None or session.status == "deleted":
            raise LookupError(f"agent session not found: {session_id}")
        if session.status != "active":
            raise ValueError("agent session is closing")
        current = await self.repository.get_current_run(session_id)
        if isinstance(command, MessageCommand):
            run, entry, inserted = await self.repository.submit_user_command(
                session_id,
                command,
                model_snapshot=session.model_snapshot,
            )
            if not inserted:
                return
            if run is not None:
                assert entry is not None
                await self.event_hub.publish(
                    session_id,
                    EntryCommittedEvent(entry=entry_contract(entry)),
                )
                await self._start_run(session_id, str(run.id), wait=True)
            return
        if isinstance(command, SteerCommand):
            if current is None:
                raise ValueError("there is no active run to steer")
            target_run, inserted = await self.repository.enqueue_command(
                session_id, command
            )
            return
        if isinstance(command, RespondCommand):
            if current is None or current.status != "waiting_user":
                raise ValueError("there is no pending user interaction")
            _, inserted = await self.repository.enqueue_command(session_id, command)
            if not inserted:
                return
            if self._execution_scheduler is not None:
                self._execution_scheduler(session_id, str(current.id), "commands", None)
            else:
                await self.process_durable_commands(session_id, str(current.id))
            return
        if isinstance(command, CancelCommand):
            if current is None:
                return
            _, inserted = await self.repository.enqueue_command(session_id, command)
            if not inserted:
                return
            task = self._tasks.get(str(current.id))
            if (
                current.status != "waiting_user"
                and task is not None
                and not task.done()
            ):
                cancellation = self._cancellations.setdefault(
                    str(current.id), asyncio.Event()
                )
                cancellation.set()
                task.cancel()
            if self._execution_scheduler is not None:
                self._execution_scheduler(session_id, str(current.id), "commands", None)
            else:
                await self.process_durable_commands(session_id, str(current.id))
            return
        raise TypeError(f"unsupported agent command: {type(command).__name__}")

    async def _current_tool_calls(
        self, *, session_id: str, run_id: str, run
    ) -> list[dict]:
        entries = await self.repository.list_entries(session_id)
        for entry in reversed(entries):
            if (
                str(entry.run_id) == run_id
                and entry.type == "message"
                and entry.payload.get("role") == "assistant"
                and _typed_tool_calls(entry.payload)
            ):
                return _typed_tool_calls(entry.payload)
        return [
            dict(item)
            for item in (run.checkpoint or {}).get("in_flight_tools") or []
            if isinstance(item, dict)
        ]

    async def snapshot(self, session_id: str) -> SessionSnapshot:
        return await self.repository.snapshot(session_id)

    async def delete_session(self, session_id: str) -> None:
        session = await self.repository.get_session(session_id)
        if session is None:
            raise LookupError(f"agent session not found: {session_id}")
        if session.status != "closing":
            raise ValueError("agent session must be quiesced before deletion")
        current = await self.repository.get_current_run(session_id)
        if current is not None:
            raise ValueError("agent session still has active work")
        if self.token_service is not None:
            await self.token_service.revoke_session(session_id)
        if not await self.repository.delete_session(session_id):
            raise LookupError(f"agent session not found: {session_id}")

    def events(self, session_id: str) -> AsyncIterator[AgentEvent]:
        return self.event_hub.stream(
            session_id,
            lambda: self.repository.snapshot(session_id),
        )

    async def recover(self) -> int:
        """Resume queued/running work from permanent history after process restart."""

        runs = await self.repository.list_recoverable_runs()
        recovered = 0
        if self._execution_scheduler is not None:
            for run in runs:
                self._execution_scheduler(
                    str(run.session_id), str(run.id), "recover", None
                )
            recovered = len(runs)
        else:
            recovered = sum([await self.recover_run(str(run.id)) for run in runs])
        sessions = await self.repository.list_sessions_with_queued_command(
            kind="message"
        )
        for session in sessions:
            if await self._start_next_message(str(session.id), wait=True):
                recovered += 1
        return recovered

    async def process_durable_commands(
        self,
        session_id: str,
        run_id: str,
        *,
        claimed: bool = False,
    ) -> bool:
        """Let the lease owner consume respond/cancel commands from durable state."""

        if not claimed and not await self._claim_and_bind(run_id):
            return False
        return await self._consume_durable_commands(
            session_id=session_id,
            run_id=run_id,
        )

    async def recover_run(self, run_id: str, *, claimed: bool = False) -> int:
        run = await self.repository.get_run(run_id)
        if run is None:
            return 0
        session = await self.repository.get_session(str(run.session_id))
        if session is None or session.status == "deleted":
            return 0
        if self.token_service is not None:
            await self.token_service.revoke_run(str(run.id))
        self._run_tokens.pop(str(run.id), None)
        if not claimed and not await self._claim_and_bind(str(run.id)):
            return 0
        if session.status == "closing":
            await self.repository.update_run(
                str(run.id),
                status="cancelled",
                phase=None,
                termination_reason=str(run.cancel_reason or "session_deleted"),
            )
            return 1
        if await self.process_durable_commands(
            str(session.id),
            str(run.id),
            claimed=True,
        ):
            return 1
        plan = RecoveryPlanner(harness_version=HARNESS_VERSION).plan(
            checkpoint=run.checkpoint,
            history_revision=int(session.history_revision),
        )
        recovery_revision = int(session.history_revision)
        reset_model_checkpoint = plan.source == "history"
        if plan.source == "history" and plan.notice:
            notice = await self._append_recovery_notice(
                session_id=str(session.id),
                run_id=str(run.id),
                code="recovery_state_ignored",
                message=plan.notice,
            )
            recovery_revision = notice.sequence
        if plan.source == "history" and run.status == "waiting_user":
            if await self._restore_waiting_interaction_from_history(
                session_id=str(session.id),
                run_id=str(run.id),
                history_revision=recovery_revision,
            ):
                return 1
        if plan.source == "history":
            if await self._complete_committed_final_answer(
                session_id=str(session.id), run_id=str(run.id)
            ):
                return 1
            session = await self.repository.get_session(str(run.session_id))
            assert session is not None
            recovery_revision = int(session.history_revision)
        if plan.source == "history" and await self._recover_committed_tool_calls(
            session=session,
            run_id=str(run.id),
            history_revision=recovery_revision,
        ):
            return 1
        if plan.resume_phase == "model" and run.draft:
            notice = await self._append_recovery_notice(
                session_id=str(session.id),
                run_id=str(run.id),
                code="model_stream_interrupted",
                message=(
                    "The previous model stream ended before its assistant message "
                    "was committed. Continuing from permanent history."
                ),
            )
            recovery_revision = notice.sequence
            reset_model_checkpoint = True
        if reset_model_checkpoint:
            await self.repository.update_run(
                str(run.id),
                draft=None,
                checkpoint=create_checkpoint(
                    harness_version=HARNESS_VERSION,
                    phase="model",
                    history_revision=recovery_revision,
                ),
            )
        if run.status == "waiting_user" and plan.resume_phase == "interaction":
            return 1
        if plan.source == "checkpoint" and plan.resume_phase == "tools":
            if await self._recover_tools(session, run, plan):
                return 1
        await self._drive_run(str(session.id), str(run.id), claimed=True)
        return 1

    async def _consume_durable_commands(
        self,
        *,
        session_id: str,
        run_id: str,
    ) -> bool:
        commands = await self.repository.dequeue_commands(
            run_id,
            kinds={"cancel"},
        )
        cancellation = next(
            (
                CancelCommand.model_validate(command)
                for command in commands
                if command.get("type") == "cancel"
            ),
            None,
        )
        persisted_reason = await self.repository.get_run_cancellation(run_id)
        if cancellation is not None or persisted_reason is not None:
            run = await self.repository.get_run(run_id)
            if run is None:
                return False
            reason = (
                cancellation.reason if cancellation is not None else persisted_reason
            ) or "cancelled"
            if self.token_service is not None:
                await self.token_service.revoke_run(run_id)
            self._run_tokens.pop(run_id, None)
            committed, cancelled = await self.repository.cancel_run_with_history(
                session_id,
                run_id=run_id,
                reason=reason,
                tool_calls=await self._current_tool_calls(
                    session_id=session_id,
                    run_id=run_id,
                    run=run,
                ),
            )
            for entry in committed:
                await self.event_hub.publish(
                    session_id,
                    EntryCommittedEvent(entry=entry_contract(entry)),
                )
            await self.event_hub.publish(
                session_id,
                RunUpdatedEvent(run=run_view(cancelled)),
            )
            await self._after_run(session_id, run_id, wait=True)
            return True
        responses = [
            RespondCommand.model_validate(command)
            for command in await self.repository.peek_commands(
                run_id, kinds={"respond"}
            )
            if command.get("type") == "respond"
        ]
        if not responses:
            return False
        run = await self.repository.get_run(run_id)
        if run is None:
            return False
        expected_interaction_id = checkpoint_interaction_id(run.checkpoint or {})
        command = next(
            (
                response
                for response in responses
                if response.interaction_id == expected_interaction_id
            ),
            None,
        )
        if command is None:
            raise ValueError(
                "response interaction does not match the pending interaction"
            )
        await self.drive_response(
            session_id,
            run_id,
            {
                **command.response.model_dump(mode="json", exclude={"type"}),
                "request_id": command.interaction_id,
            },
            claimed=True,
            command_id=command.command_id,
        )
        return True

    async def _complete_committed_final_answer(
        self, *, session_id: str, run_id: str
    ) -> bool:
        entries = await self.repository.list_entries(session_id)
        latest_message = next(
            (
                entry
                for entry in reversed(entries)
                if str(entry.run_id) == run_id and entry.type == "message"
            ),
            None,
        )
        if (
            latest_message is None
            or latest_message.payload.get("role") != "assistant"
            or _typed_tool_calls(latest_message.payload)
        ):
            return False
        steer_entries, completed = await self.repository.commit_steers_or_complete_run(
            session_id, run_id=run_id
        )
        for entry in steer_entries:
            await self.event_hub.publish(
                session_id,
                EntryCommittedEvent(entry=entry_contract(entry)),
            )
        if steer_entries:
            return False
        return completed.status == "completed"

    async def _recover_committed_tool_calls(
        self,
        *,
        session,
        run_id: str,
        history_revision: int,
    ) -> bool:
        entries = await self.repository.list_entries(str(session.id))
        unresolved: list[dict[str, Any]] | None = None
        for entry in reversed(entries):
            if (
                str(entry.run_id) != run_id
                or entry.type != "message"
                or entry.payload.get("role") != "assistant"
            ):
                continue
            calls = _typed_tool_calls(entry.payload)
            if not calls:
                continue
            resolved = {
                str(_typed_tool_result_call_id(candidate.payload))
                for candidate in entries
                if candidate.sequence > entry.sequence
                and str(candidate.run_id) == run_id
                and candidate.type == "message"
                and candidate.payload.get("role") == "tool"
                and _typed_tool_result_call_id(candidate.payload)
            }
            unresolved = [
                {
                    **item,
                    "group_id": str(item.get("group_id") or entry.id),
                }
                for item in calls
                if str(item.get("call_id")) not in resolved
            ]
            if unresolved:
                break
        if not unresolved:
            return False
        workspace = self.loop.workspace_factory(session, run_id)
        replay_policies = {spec.name: spec.replay_policy for spec in workspace.tools}
        checkpoint = {
            **create_checkpoint(
                harness_version=HARNESS_VERSION,
                phase="tools",
                history_revision=history_revision,
                in_flight_tools=tuple(
                    {
                        **call,
                        "replay_policy": replay_policies.get(call.get("name"), "never"),
                    }
                    for call in unresolved
                ),
            ),
            "pending_calls": unresolved,
        }
        await self.repository.update_run(
            run_id,
            status="running",
            phase="tools",
            checkpoint=checkpoint,
            tool_progress=[
                _tool_progress_item(
                    call_id=str(call.get("call_id") or ""),
                    name=str(call.get("name") or "unknown"),
                    arguments=dict(call.get("arguments") or {}),
                    spec=workspace.tool_spec(str(call.get("name") or "unknown")),
                    status="pending",
                    group_id=str(
                        call.get("group_id") or _missing_group_id(call)
                    ),
                    execution_mode=str(call.get("execution_mode") or "serial"),
                )
                for call in unresolved
            ],
        )
        run = await self.repository.get_run(run_id)
        assert run is not None
        plan = RecoveryPlanner(harness_version=HARNESS_VERSION).plan(
            checkpoint=run.checkpoint,
            history_revision=history_revision,
        )
        if await self._recover_tools(session, run, plan):
            return True
        await self._drive_run(str(session.id), run_id, claimed=True)
        return True

    async def _restore_waiting_interaction_from_history(
        self,
        *,
        session_id: str,
        run_id: str,
        history_revision: int,
    ) -> bool:
        entries = await self.repository.list_entries(session_id)
        pending: dict[str, Any] = {}
        resolved_call_ids: set[str] = set()
        for entry in entries:
            if str(entry.run_id) != run_id:
                continue
            interaction_id = str(entry.payload.get("interaction_id") or "")
            if entry.type == "interaction_request" and interaction_id:
                pending[interaction_id] = entry
            elif entry.type == "interaction_response" and interaction_id:
                pending.pop(interaction_id, None)
            elif entry.type == "message" and entry.payload.get("role") == "tool":
                call_id = _typed_tool_result_call_id(entry.payload)
                if isinstance(call_id, str) and call_id:
                    resolved_call_ids.add(call_id)
        if not pending:
            return False
        request_entry = max(pending.values(), key=lambda item: item.sequence)
        request = dict(request_entry.payload.get("request") or {})
        interaction_id = str(request_entry.payload["interaction_id"])
        call_id = request.get("call_id")
        if not isinstance(call_id, str) or not call_id:
            prefix, separator, suffix = interaction_id.partition(":")
            call_id = suffix if separator and prefix == "tool" else None
        if not call_id:
            return False
        calls: list[dict[str, Any]] | None = None
        owning_entry_id: str | None = None
        for entry in reversed(entries):
            if (
                str(entry.run_id) != run_id
                or entry.type != "message"
                or entry.payload.get("role") != "assistant"
            ):
                continue
            candidate = _typed_tool_calls(entry.payload)
            if any(item.get("call_id") == call_id for item in candidate):
                calls = candidate
                owning_entry_id = str(entry.id)
                break
        if calls is None or owning_entry_id is None:
            return False
        calls = [
            {**item, "group_id": str(item.get("group_id") or owning_entry_id)}
            for item in calls
        ]
        waiting_index = next(
            index for index, item in enumerate(calls) if item.get("call_id") == call_id
        )
        waiting_call = calls[waiting_index]
        pending_calls = [
            item
            for item in calls[waiting_index + 1 :]
            if item.get("call_id") not in resolved_call_ids
        ]
        session = await self.repository.get_session(session_id)
        if session is None:
            return False
        workspace = self.loop.workspace_factory(session, run_id)
        replay_policies = {spec.name: spec.replay_policy for spec in workspace.tools}
        private_interaction = request
        refreshed = await workspace.execute(_runtime_tool_call(waiting_call))
        if refreshed.status == "interaction_required":
            private_interaction = _tool_interaction_dict(refreshed)
        checkpoint = {
            **create_checkpoint(
                harness_version=HARNESS_VERSION,
                phase="interaction",
                history_revision=history_revision,
                in_flight_tools=tuple(
                    {
                        **item,
                        "replay_policy": replay_policies.get(
                            str(item.get("name") or ""), "never"
                        ),
                    }
                    for item in [waiting_call, *pending_calls]
                ),
                interaction=private_interaction,
            ),
            "waiting_call": waiting_call,
            "pending_calls": pending_calls,
            "interaction": private_interaction,
        }
        await self.repository.update_run(
            run_id,
            status="waiting_user",
            phase="interaction",
            checkpoint=checkpoint,
            draft=None,
            tool_progress=[
                _tool_progress_item(
                    call_id=str(item.get("call_id") or ""),
                    name=str(item.get("name") or "unknown"),
                    arguments=dict(item.get("arguments") or {}),
                    spec=workspace.tool_spec(str(item.get("name") or "unknown")),
                    status=(
                        "interaction_required"
                        if item.get("call_id") == call_id
                        else "pending"
                    ),
                    group_id=str(
                        item.get("group_id") or _missing_group_id(item)
                    ),
                    execution_mode=str(item.get("execution_mode") or "serial"),
                )
                for item in [waiting_call, *pending_calls]
            ],
        )
        return True

    async def _append_recovery_notice(
        self,
        *,
        session_id: str,
        run_id: str,
        code: str,
        message: str,
    ):
        entry = await self.repository.append_entry(
            session_id,
            run_id=run_id,
            entry_type="notice",
            payload={"code": code, "message": message},
        )
        await self.event_hub.publish(
            session_id,
            EntryCommittedEvent(entry=entry_contract(entry)),
        )
        return entry

    async def _recover_tools(self, session, run, plan) -> bool:
        workspace = self.loop.workspace_factory(session, str(run.id))
        committed_call_ids: set[str] = set()
        await self.repository.update_run(
            str(run.id),
            tool_progress=[
                _tool_progress_item(
                    call_id=item.call_id,
                    name=item.name,
                    arguments={},
                    spec=workspace.tool_spec(item.name),
                    status="pending",
                    **_checkpoint_tool_presentation(
                        run.checkpoint, call_id=item.call_id
                    ),
                )
                for item in plan.tools
            ],
        )
        for item in plan.tools:
            interaction_id = f"tool:{item.call_id}"
            persisted_response = await self.repository.get_interaction_response(
                str(session.id),
                run_id=str(run.id),
                interaction_id=interaction_id,
            )
            reusable_response = (
                persisted_response
                if persisted_response is not None
                and not (
                    item.action == "ask_user"
                    and persisted_response.get("approved") is True
                )
                else None
            )
            if item.action == "ask_user" and reusable_response is None:
                current = await self.repository.get_run(str(run.id))
                checkpoint = dict(current.checkpoint or {}) if current else {}
                checkpoint["history_revision"] = int(session.history_revision)
                checkpoint["in_flight_tools"] = [
                    raw
                    for raw in checkpoint.get("in_flight_tools") or []
                    if raw.get("call_id") not in committed_call_ids
                ]
                await self.repository.update_run(str(run.id), checkpoint=checkpoint)
                current = await self.repository.get_run(str(run.id))
                assert current is not None
                current_plan = RecoveryPlanner(harness_version=HARNESS_VERSION).plan(
                    checkpoint=current.checkpoint,
                    history_revision=int(session.history_revision),
                )
                await self._request_recovery_interaction(session, current, current_plan)
                return True
            call_data = next(
                (
                    raw
                    for raw in (run.checkpoint or {}).get("in_flight_tools") or []
                    if isinstance(raw, dict) and raw.get("call_id") == item.call_id
                ),
                None,
            )
            if call_data is None:
                continue
            await self._mark_tool_progress(
                str(run.id),
                call_id=item.call_id,
                name=item.name,
                status="running",
            )
            call = ToolCall(
                call_id=item.call_id,
                name=item.name,
                arguments=dict(call_data.get("arguments") or {}),
            )
            if item.action == "verify":
                result = await workspace.verify_recovery(call)
            elif reusable_response is not None:
                result = await workspace.execute(
                    call,
                    interaction_response={
                        **reusable_response,
                        "request_id": interaction_id,
                    },
                )
            else:
                result = await workspace.execute(call)
            if result.status == "interaction_required":
                interaction = result.interaction
                assert interaction is not None
                checkpoint = dict(run.checkpoint or {})
                recovery_request = _verification_recovery_request(result)
                checkpoint.update(
                    {
                        "phase": "interaction",
                        "waiting_call": {
                            "call_id": item.call_id,
                            "name": item.name,
                            "arguments": dict(call_data.get("arguments") or {}),
                        },
                        "interaction": recovery_request,
                        "recovery_interaction": recovery_request,
                    }
                )
                _, entry, _ = await self.repository.commit_waiting_interaction(
                    str(session.id),
                    run_id=str(run.id),
                    request_payload={
                        "interaction_id": interaction.request_id,
                        "request": recovery_request,
                    },
                    checkpoint=checkpoint,
                    tool_progress=[
                        _tool_progress_item(
                            call_id=item.call_id,
                            name=item.name,
                            arguments=dict(call_data.get("arguments") or {}),
                            spec=workspace.tool_spec(item.name),
                            status="interaction_required",
                            group_id=str(
                                call_data.get("group_id")
                                or _missing_group_id(call_data)
                            ),
                            execution_mode=str(
                                call_data.get("execution_mode") or "serial"
                            ),
                        )
                    ],
                )
                await self.event_hub.publish(
                    str(session.id),
                    EntryCommittedEvent(entry=entry_contract(entry)),
                )
                await self.event_hub.publish(
                    str(session.id),
                    InteractionRequestedEvent(
                        run_id=run.id,
                        interaction=(
                            pending_interaction_entry_view(entry)
                        ),
                    ),
                )
                return True
            await self._mark_tool_progress(
                str(run.id),
                call_id=item.call_id,
                name=item.name,
                status=result.status,
                output_summary=_public_output_summary(result.output),
                error=result.error,
            )
            entry = await self.repository.append_entry(
                str(session.id),
                run_id=str(run.id),
                entry_type="message",
                payload={
                    "role": "tool",
                    "parts": [
                        {
                            "id": f"tool-result:{item.call_id}",
                            "type": "tool_result",
                            "call_id": item.call_id,
                            "status": result.status,
                            "output": {
                                "type": "text",
                                "text": _recovered_tool_output(result),
                            },
                            "error": result.error,
                        }
                    ],
                },
            )
            committed_call_ids.add(item.call_id)
            await self.event_hub.publish(
                str(session.id),
                EntryCommittedEvent(entry=entry_contract(entry)),
            )
        checkpoint = dict(run.checkpoint or {})
        checkpoint["history_revision"] = int(session.history_revision)
        checkpoint["in_flight_tools"] = [
            item
            for item in checkpoint.get("in_flight_tools") or []
            if item.get("call_id") not in committed_call_ids
        ]
        checkpoint["phase"] = "model"
        await self.repository.update_run(
            str(run.id),
            status="running",
            phase="model",
            checkpoint=checkpoint,
            tool_progress=None,
        )
        return False

    async def _request_recovery_interaction(self, session, run, plan) -> None:
        interaction = plan.interaction
        assert interaction is not None
        notice_payload = {
            "code": "unknown_tool_effect",
            "message": plan.notice or "Tool outcome is unknown after restart.",
            "details": {"interaction_id": interaction.interaction_id},
        }
        request_payload = {
            "interaction_id": interaction.interaction_id,
            "request": interaction.request,
        }
        checkpoint = dict(run.checkpoint or {})
        checkpoint.update(
            {
                "phase": "interaction",
                "recovery_interaction": interaction.request,
                "waiting_call": _recovering_call(checkpoint, interaction.request),
            }
        )
        waiting_call = checkpoint["waiting_call"]
        workspace = self.loop.workspace_factory(session, str(run.id))
        notice, request, waiting_run = await self.repository.commit_waiting_interaction(
            str(session.id),
            run_id=str(run.id),
            notice_payload=notice_payload,
            request_payload=request_payload,
            checkpoint=checkpoint,
            tool_progress=[
                _tool_progress_item(
                    call_id=str(waiting_call.get("call_id") or ""),
                    name=str(waiting_call.get("name") or "unknown"),
                    arguments=dict(waiting_call.get("arguments") or {}),
                    spec=workspace.tool_spec(
                        str(waiting_call.get("name") or "unknown")
                    ),
                    status="interaction_required",
                    group_id=str(
                        waiting_call.get("group_id")
                        or _missing_group_id(waiting_call)
                    ),
                    execution_mode=str(
                        waiting_call.get("execution_mode") or "serial"
                    ),
                )
            ],
        )
        assert notice is not None
        await self.event_hub.publish(
            str(session.id),
            RunUpdatedEvent(run=run_view(waiting_run)),
        )
        await self.event_hub.publish(
            str(session.id),
            EntryCommittedEvent(entry=entry_contract(notice)),
        )
        await self.event_hub.publish(
            str(session.id),
            EntryCommittedEvent(entry=entry_contract(request)),
        )
        await self.event_hub.publish(
            str(session.id),
            ToolUpdatedEvent(
                run_id=run.id,
                tool=_tool_progress_view(
                    waiting_run, str(waiting_call.get("call_id") or "")
                ),
            ),
        )
        await self.event_hub.publish(
            str(session.id),
            InteractionRequestedEvent(
                run_id=run.id,
                interaction=pending_interaction_entry_view(request),
            ),
        )

    async def drive_run(
        self, session_id: str, run_id: str, *, claimed: bool = False
    ) -> None:
        await self._drive_run(session_id, run_id, claimed=claimed)

    async def drive_response(
        self,
        session_id: str,
        run_id: str,
        response: dict[str, Any],
        *,
        claimed: bool = False,
        command_id: str | None = None,
    ) -> None:
        cancellation = self._cancellations.setdefault(run_id, asyncio.Event())
        session = await self.repository.get_session(session_id)
        if session is None:
            raise LookupError(f"agent session not found: {session_id}")
        if not claimed and not await self._claim_and_bind(run_id):
            return
        self._publishing_session_id = session_id
        try:
            await self.loop.resume_interaction(
                run_id,
                response,
                cancellation,
                command_id=command_id,
            )
        except asyncio.CancelledError:
            await asyncio.shield(self.repository.db.rollback())
            raise
        finally:
            self._publishing_session_id = None
            await self._revoke_run_token(run_id)
        await self._after_run(session_id, run_id, wait=True)

    async def _start_run(self, session_id: str, run_id: str, *, wait: bool) -> None:
        if self._execution_scheduler is not None:
            self._execution_scheduler(session_id, run_id, "run", None)
            return
        if wait:
            await self._drive_run(session_id, run_id)
            return
        task = asyncio.create_task(
            self._drive_run(session_id, run_id), name=f"agent-run:{run_id}"
        )
        self._tasks[run_id] = task

    async def _drive_run(
        self, session_id: str, run_id: str, *, claimed: bool = False
    ) -> None:
        cancellation = self._cancellations.setdefault(run_id, asyncio.Event())
        session = await self.repository.get_session(session_id)
        if session is None:
            raise LookupError(f"agent session not found: {session_id}")
        if not claimed and not await self._claim_and_bind(run_id):
            return
        self._publishing_session_id = session_id
        try:
            await self.loop.run(run_id, cancellation)
        except asyncio.CancelledError:
            await asyncio.shield(self.repository.db.rollback())
            raise
        finally:
            self._publishing_session_id = None
            finished = await self.repository.get_run(run_id)
            if finished is None or finished.status in {
                "waiting_user",
                "completed",
                "failed",
                "cancelled",
            }:
                await self._revoke_run_token(run_id)
        await self._after_run(session_id, run_id, wait=False)

    async def _after_run(self, session_id: str, run_id: str, *, wait: bool) -> None:
        run = await self.repository.get_run(run_id)
        if run is not None and run.status in {"completed", "failed", "cancelled"}:
            self._cancellations.pop(run_id, None)
            await self._start_next_message(session_id, wait=wait)

    async def _start_next_message(self, session_id: str, *, wait: bool) -> bool:
        session = await self.repository.get_session(session_id)
        if session is None or session.status != "active":
            return False
        next_run = await self.repository.create_run_from_next_session_command(
            session_id,
            kind="message",
            model_snapshot=session.model_snapshot,
        )
        if next_run is None:
            return False
        run, entry = next_run
        await self.event_hub.publish(
            session_id,
            EntryCommittedEvent(entry=entry_contract(entry)),
        )
        await self._start_run(session_id, str(run.id), wait=wait)
        return True

    async def _publish_for_current_session(self, event: AgentEvent) -> None:
        session_id = self._publishing_session_id
        if session_id is not None:
            await self.event_hub.publish(session_id, event)

    async def _ensure_run_token(
        self, session, run_id: str, *, replace: bool = False
    ) -> None:
        if self.token_service is None or (run_id in self._run_tokens and not replace):
            return
        fence = self.repository.run_fence(run_id)
        if fence is None:
            raise ValueError("Agent token issuance requires a claimed Run fence")
        grant = await self.token_service.issue(
            user_id=session.user_id,
            workspace_id=str(session.workspace_id),
            session_id=str(session.id),
            run_id=run_id,
            fence=fence,
        )
        self._run_tokens[run_id] = grant.token

    async def _revoke_run_token(self, run_id: str) -> None:
        try:
            if self.token_service is not None:
                await self.token_service.revoke_run(
                    run_id,
                    fence=self.repository.run_fence(run_id),
                )
        finally:
            self._run_tokens.pop(run_id, None)

    async def _mark_tool_progress(
        self,
        run_id: str,
        *,
        call_id: str,
        name: str,
        status: str,
        output_summary: str | None = None,
        error: str | None = None,
    ):
        run = await self.repository.get_run(run_id)
        if run is None:
            raise LookupError(f"agent run not found: {run_id}")
        view = await self.repository.update_tool_progress(
            run_id,
            call_id=call_id,
            name=name,
            status=status,
            output_summary=output_summary,
            error=error,
        )
        await self.event_hub.publish(
            str(run.session_id),
            ToolUpdatedEvent(run_id=run.id, tool=view),
        )
        return view

    def _lease_owner(self) -> str:
        return self._lease_owner_id

    async def _claim_and_bind(self, run_id: str) -> bool:
        generation = await self.repository.claim_run(
            run_id,
            owner=self._lease_owner(),
            lease_expires_at=datetime.now(timezone.utc)
            + timedelta(seconds=max(int(settings.agent_run_lease_seconds), 1)),
        )
        if generation is None:
            return False
        self.bind_run_fence(run_id, owner=self._lease_owner(), generation=generation)
        return True


def _recovering_call(
    checkpoint: dict[str, Any], request: dict[str, Any]
) -> dict[str, Any]:
    call_id = request.get("call_id")
    for item in checkpoint.get("in_flight_tools") or []:
        if isinstance(item, dict) and item.get("call_id") == call_id:
            return {
                "call_id": item.get("call_id"),
                "group_id": item.get("group_id"),
                "execution_mode": item.get("execution_mode"),
                "name": item.get("name"),
                "arguments": item.get("arguments") or {},
            }
    return {"call_id": call_id, "name": request.get("tool_name"), "arguments": {}}


def _typed_tool_calls(payload: dict[str, Any]) -> list[dict[str, Any]]:
    calls = [
        part
        for part in payload.get("parts") or []
        if isinstance(part, dict) and part.get("type") == "tool_call"
    ]
    return [
        {
            "call_id": str(item.get("call_id") or ""),
            "group_id": str(item.get("group_id") or ""),
            "execution_mode": str(item.get("execution_mode") or "serial"),
            "name": str(item.get("name") or "unknown"),
            "arguments": dict(item.get("arguments") or {}),
        }
        for item in calls
        if isinstance(item, dict) and item.get("call_id")
    ]


def _runtime_tool_call(item: dict[str, Any]) -> ToolCall:
    return ToolCall(
        call_id=str(item.get("call_id") or ""),
        name=str(item.get("name") or "unknown"),
        arguments=dict(item.get("arguments") or {}),
    )


def _typed_tool_result_call_id(payload: dict[str, Any]) -> str | None:
    for part in payload.get("parts") or []:
        if isinstance(part, dict) and part.get("type") == "tool_result":
            call_id = part.get("call_id")
            return str(call_id) if call_id else None
    return None


def _recovered_tool_output(result) -> str:
    return json.dumps(
        result.output if result.status == "completed" else {"error": result.error},
        ensure_ascii=False,
        default=str,
    )


def _tool_progress_view(run: Any, call_id: str) -> ToolProgressView:
    for item in run.tool_progress or []:
        if isinstance(item, dict) and item.get("call_id") == call_id:
            return ToolProgressView.model_validate(item)
    raise LookupError(f"tool progress not found: {call_id}")


def _tool_progress_item(
    *,
    call_id: str,
    name: str,
    arguments: dict[str, Any],
    spec: ToolSpec | None,
    status: str,
    group_id: str,
    execution_mode: str | None = None,
) -> dict[str, Any]:
    return project_tool_view(
        spec=spec,
        call_id=call_id,
        name=name,
        arguments=arguments,
        status=status,
        group_id=group_id,
        execution_mode=execution_mode or "serial",
    ).model_dump(mode="json")


def _checkpoint_tool_presentation(
    checkpoint: dict[str, Any] | None, *, call_id: str
) -> dict[str, str]:
    for item in (checkpoint or {}).get("in_flight_tools") or []:
        if isinstance(item, dict) and item.get("call_id") == call_id:
            return {
                "group_id": str(item.get("group_id") or _missing_group_id(item)),
                "execution_mode": str(item.get("execution_mode") or "serial"),
            }
    raise ValueError(f"checkpoint has no tool call {call_id}")


def _missing_group_id(item: dict[str, Any]) -> str:
    raise ValueError(
        f"tool call {item.get('call_id') or 'unknown'} has no owning assistant entry"
    )


def _tool_interaction_dict(result) -> dict[str, Any]:
    interaction = result.interaction
    if interaction is None:
        return {}
    return {
        "request_id": interaction.request_id,
        "call_id": interaction.call_id,
        "kind": interaction.kind,
        "questions": list(interaction.questions),
        "risk": interaction.risk,
    }


def _verification_recovery_request(result) -> dict[str, Any]:
    return {
        "kind": "recovery",
        "call_id": result.call_id,
        "tool_name": result.tool_name,
        "message": (
            f"Bioinfoflow could not prove whether the interrupted {result.tool_name} "
            "operation changed the target. Choose how to continue."
        ),
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


__all__ = ["AgentHarness"]
