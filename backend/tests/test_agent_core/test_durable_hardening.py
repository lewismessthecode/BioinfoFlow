from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.agent_core import AgentActionStatus
from app.models.llm import LlmModel, LlmProvider
from app.models.workspace import Workspace
from app.repositories.agent_core_repo import (
    AgentActionRepository,
    AgentArtifactRepository,
    AgentEventRepository,
    AgentMessageRepository,
)
from app.config import settings
from app.services.agent_core import AgentCoreService
from app.services.agent_core.actions import AgentActionService
from app.services.agent_core.core import AgentLoopController
from app.services.agent_core.core.types import LoopResult
from app.services.agent_core.runtime import AgentCoreRuntime
from app.services.agent_core.tools import AgentToolContext, AgentToolSpec
from app.services.agent_core.tools.executor import AgentToolExecutor, ToolExecutionResult
from app.services.agent_core.tools.registry import AgentToolRegistry
from app.services.agent_core.transcript import (
    AgentTranscriptStore,
    text_part,
    tool_calls_part,
)
from app.utils.exceptions import ConflictError
from app.workspace import DEFAULT_WORKSPACE_ID


async def _workspace(db_session) -> Workspace:
    workspace = Workspace(id=DEFAULT_WORKSPACE_ID, name="Team", slug="team")
    db_session.add(workspace)
    await db_session.commit()
    return workspace


async def _seed_model(db_session, *, model_id: str = "durable-model") -> LlmModel:
    provider = LlmProvider(
        name=f"{model_id} provider",
        kind="openai_compatible",
        base_url="https://models.internal.example/v1",
        scope="user",
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        enabled=True,
        provider_metadata={"providerTemplate": "openai-compatible"},
    )
    db_session.add(provider)
    await db_session.commit()
    await db_session.refresh(provider)
    model = LlmModel(
        provider_id=str(provider.id),
        model_id=model_id,
        display_name=model_id,
        supports_tools=True,
        supports_streaming=False,
    )
    db_session.add(model)
    await db_session.commit()
    await db_session.refresh(model)
    return model


def _tool_call_response(*, call_id: str, name: str, arguments: dict):
    class FakeResponse:
        usage = None

    class FakeChoice:
        pass

    class FakeMessage:
        content = ""

    class FakeFunction:
        pass

    class FakeToolCall:
        pass

    function = FakeFunction()
    function.name = name
    function.arguments = json.dumps(arguments)
    tool_call = FakeToolCall()
    tool_call.id = call_id
    tool_call.function = function
    message = FakeMessage()
    message.tool_calls = [tool_call]
    choice = FakeChoice()
    choice.message = message
    response = FakeResponse()
    response.choices = [choice]
    return response


@dataclass
class _CountingMutationTool:
    calls: list[str]
    name: str = "counting.mutate"

    @property
    def spec(self) -> AgentToolSpec:
        return AgentToolSpec(
            name=self.name,
            description="Count one durable mutation.",
            input_schema={"type": "object", "additionalProperties": False},
            output_schema={
                "type": "object",
                "properties": {"ok": {"type": "boolean"}},
                "required": ["ok"],
                "additionalProperties": False,
            },
            risk_level="act_high",
            write_scope=["test:mutation"],
        )

    async def run(self, input, context):
        del input
        self.calls.append(context.turn_id)
        await asyncio.sleep(0.02)
        return {"ok": True}


@dataclass
class _BlockingMutationTool:
    started: asyncio.Event
    release: asyncio.Event
    cancelled: asyncio.Event | None = None
    name: str = "blocking.mutate"

    @property
    def spec(self) -> AgentToolSpec:
        return AgentToolSpec(
            name=self.name,
            description="Block one durable mutation until the test releases it.",
            input_schema={"type": "object", "additionalProperties": False},
            output_schema={
                "type": "object",
                "properties": {"ok": {"type": "boolean"}},
                "required": ["ok"],
                "additionalProperties": False,
            },
            risk_level="act_high",
            write_scope=["test:mutation"],
        )

    async def run(self, input, context):
        del input, context
        self.started.set()
        try:
            await self.release.wait()
        except asyncio.CancelledError:
            if self.cancelled is not None:
                self.cancelled.set()
            raise
        return {"ok": True}


async def _session_turn_and_action(
    db_session,
    *,
    tool_name: str,
    execution_target: dict | None = None,
):
    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=None,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        execution_target=execution_target,
    )
    turn = await service.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Run one approved mutation.",
    )
    target = execution_target or {"type": "local"}
    action = await AgentActionRepository(db_session).create(
        session_id=str(session.id),
        turn_id=str(turn.id),
        kind="tool",
        name=tool_name,
        tool_call_id="durable-call",
        input={},
        normalized_input={},
        exposure_policy={"name": "execution", "execution_target": target},
        risk_level="act_high",
        permission_decision={"decision": "approve"},
        status=AgentActionStatus.REQUESTED,
    )
    return service, session, turn, action


@pytest.mark.asyncio
async def test_two_independent_resumes_claim_approved_action_exactly_once(
    db_session,
    db_engine,
):
    await _workspace(db_session)
    calls: list[str] = []
    tool = _CountingMutationTool(calls)
    _service, session, turn, action = await _session_turn_and_action(
        db_session,
        tool_name=tool.name,
    )

    maker = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)

    async def resume_once():
        async with maker() as independent_db:
            registry = AgentToolRegistry()
            registry.register(tool)
            return await AgentToolExecutor(independent_db, registry).resume_action(
                action_id=str(action.id),
                context=AgentToolContext(
                    db=independent_db,
                    workspace_id=DEFAULT_WORKSPACE_ID,
                    user_id="dev",
                    session_id=str(session.id),
                    turn_id=str(turn.id),
                ),
            )

    results = await asyncio.gather(resume_once(), resume_once())

    assert calls == [str(turn.id)]
    assert sum(result.status == AgentActionStatus.COMPLETED for result in results) == 1
    assert all(result.status != AgentActionStatus.REQUESTED for result in results)
    loser = next(result for result in results if result.status != AgentActionStatus.COMPLETED)
    assert loser.error["type"] == "ActionAlreadyClaimed"
    stored = await AgentActionRepository(db_session).get(str(action.id))
    await db_session.refresh(stored)
    assert stored.status == AgentActionStatus.COMPLETED


@pytest.mark.asyncio
async def test_interrupt_cannot_be_overwritten_after_action_is_claimed(
    db_session,
    db_engine,
):
    await _workspace(db_session)
    started = asyncio.Event()
    release = asyncio.Event()
    cancelled = asyncio.Event()
    tool = _BlockingMutationTool(started, release, cancelled)
    _service, session, turn, action = await _session_turn_and_action(
        db_session,
        tool_name=tool.name,
    )
    maker = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)

    async def execute_claimed_action():
        async with maker() as run_db:
            registry = AgentToolRegistry()
            registry.register(tool)
            return await AgentToolExecutor(run_db, registry).resume_action(
                action_id=str(action.id),
                context=AgentToolContext(
                    db=run_db,
                    workspace_id=DEFAULT_WORKSPACE_ID,
                    user_id="dev",
                    session_id=str(session.id),
                    turn_id=str(turn.id),
                ),
            )

    run_task = asyncio.create_task(execute_claimed_action())
    await started.wait()
    async with maker() as interrupt_db:
        await AgentCoreService(interrupt_db).interrupt_turn(
            turn_id=str(turn.id),
            workspace_id=DEFAULT_WORKSPACE_ID,
            user_id="dev",
        )
    await asyncio.wait_for(cancelled.wait(), timeout=1)
    release.set()
    result = await run_task

    async with maker() as inspect_db:
        stored = await AgentActionRepository(inspect_db).get(str(action.id))
        messages = await AgentMessageRepository(inspect_db).list_for_session(
            str(session.id)
        )

    assert stored.status == AgentActionStatus.CANCELLED
    assert result.status == AgentActionStatus.CANCELLED
    tool_results = [
        message
        for message in messages
        if message.role == "tool"
        and (message.message_metadata or {}).get("tool_call_id") == "durable-call"
    ]
    assert len(tool_results) == 1
    assert json.loads(tool_results[0].content_parts[0]["text"])["status"] == "cancelled"


@pytest.mark.asyncio
async def test_completed_action_cannot_be_cancelled_after_terminal_write_wins(
    db_session,
    db_engine,
):
    await _workspace(db_session)
    calls: list[str] = []
    tool = _CountingMutationTool(calls)
    _service, session, turn, action = await _session_turn_and_action(
        db_session,
        tool_name=tool.name,
    )
    registry = AgentToolRegistry()
    registry.register(tool)
    completed = await AgentToolExecutor(db_session, registry).resume_action(
        action_id=str(action.id),
        context=AgentToolContext(
            db=db_session,
            workspace_id=DEFAULT_WORKSPACE_ID,
            user_id="dev",
            session_id=str(session.id),
            turn_id=str(turn.id),
        ),
    )
    assert completed.status == AgentActionStatus.COMPLETED

    maker = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    async with maker() as cancel_db:
        await AgentCoreService(cancel_db).cancel_turn(
            turn_id=str(turn.id),
            workspace_id=DEFAULT_WORKSPACE_ID,
            user_id="dev",
        )
    async with maker() as inspect_db:
        stored = await AgentActionRepository(inspect_db).get(str(action.id))

    assert stored.status == AgentActionStatus.COMPLETED
    assert stored.result == {"ok": True}


@pytest.mark.asyncio
async def test_action_completion_artifact_and_events_commit_atomically(
    db_session,
    db_engine,
):
    await _workspace(db_session)
    _service, session, turn, action = await _session_turn_and_action(
        db_session,
        tool_name="atomic.artifact",
    )
    action_id = str(action.id)
    session_id = str(session.id)
    turn_id = str(turn.id)
    claimed = await AgentActionRepository(db_session).claim_requested(
        action_id, started_at=datetime.now(timezone.utc)
    )
    assert claimed is not None
    await db_session.execute(
        text(
            """
            CREATE TRIGGER fail_action_completed_event
            BEFORE INSERT ON agent_events
            WHEN NEW.type = 'action.completed'
            BEGIN
                SELECT RAISE(ABORT, 'forced action event failure');
            END
            """
        )
    )
    await db_session.commit()

    with pytest.raises(Exception, match="forced action event failure"):
        await AgentActionRepository(db_session).complete_running(
            action_id,
            result={"ok": True},
            output_summary="done",
            completed_at=datetime.now(timezone.utc),
            artifact_descriptor={
                "type": "command",
                "title": "Atomic artifact",
                "summary": "Must roll back with completion.",
                "payload": {"ok": True},
            },
            artifact_event_type="artifact.created",
            action_event_type="action.completed",
        )
    await db_session.rollback()

    maker = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    async with maker() as inspect_db:
        stored = await AgentActionRepository(inspect_db).get(action_id)
        artifacts = await AgentArtifactRepository(inspect_db).list_for_session(
            session_id
        )
        events = await AgentEventRepository(inspect_db).list_for_turn(
            turn_id=turn_id, after_seq=0
        )

    assert stored.status == AgentActionStatus.RUNNING
    assert stored.result is None
    assert artifacts == []
    assert all(event.type != "action.completed" for event in events)
    assert all(event.type != "artifact.created" for event in events)


@pytest.mark.asyncio
async def test_concurrent_action_completions_allocate_unique_event_sequences(
    db_session,
    db_engine,
):
    await _workspace(db_session)
    _service, session, turn, first_action = await _session_turn_and_action(
        db_session,
        tool_name="concurrent.first",
    )
    second_action = await AgentActionRepository(db_session).create(
        session_id=str(session.id),
        turn_id=str(turn.id),
        kind="tool",
        name="concurrent.second",
        tool_call_id="concurrent-second-call",
        input={},
        normalized_input={},
        exposure_policy={"name": "execution", "execution_target": {"type": "local"}},
        risk_level="read",
        permission_decision={"decision": "approve"},
        status=AgentActionStatus.REQUESTED,
    )
    now = datetime.now(timezone.utc)
    await AgentActionRepository(db_session).claim_requested(
        str(first_action.id), started_at=now
    )
    await AgentActionRepository(db_session).claim_requested(
        str(second_action.id), started_at=now
    )
    maker = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)

    async def complete(action_id: str):
        async with maker() as independent_db:
            return await AgentActionRepository(independent_db).complete_running(
                action_id,
                result={"ok": True},
                output_summary="done",
                completed_at=datetime.now(timezone.utc),
                artifact_descriptor=None,
                artifact_event_type="artifact.created",
                action_event_type="action.completed",
            )

    completions = await asyncio.gather(
        complete(str(first_action.id)),
        complete(str(second_action.id)),
    )

    assert all(item is not None for item in completions)
    async with maker() as inspect_db:
        events = await AgentEventRepository(inspect_db).list_for_turn(
            turn_id=str(turn.id), after_seq=0
        )
    completion_events = [event for event in events if event.type == "action.completed"]
    assert len(completion_events) == 2
    assert len({event.seq for event in completion_events}) == 2


@pytest.mark.asyncio
async def test_resume_fails_closed_when_remote_target_changes_without_input_connection_id(
    db_session,
):
    await _workspace(db_session)
    calls: list[str] = []
    tool = _CountingMutationTool(calls, name="remote.mutate")
    target_a = {"type": "remote_ssh", "connection_id": "remote-a"}
    service, session, turn, action = await _session_turn_and_action(
        db_session,
        tool_name=tool.name,
        execution_target=target_a,
    )
    await service.update_session(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        updates={
            "execution_target": {
                "type": "remote_ssh",
                "connection_id": "remote-b",
            }
        },
    )
    registry = AgentToolRegistry()
    registry.register(tool)

    result = await AgentToolExecutor(db_session, registry).resume_action(
        action_id=str(action.id),
        context=AgentToolContext(
            db=db_session,
            workspace_id=DEFAULT_WORKSPACE_ID,
            user_id="dev",
            session_id=str(session.id),
            turn_id=str(turn.id),
        ),
    )

    assert calls == []
    assert result.status == AgentActionStatus.FAILED
    assert result.error["type"] == "ExecutionTargetMismatch"
    assert "remote-a" in result.error["message"]
    assert "remote-b" in result.error["message"]


@pytest.mark.asyncio
async def test_cross_session_interrupt_after_model_response_executes_no_tool(
    db_session,
    db_engine,
    monkeypatch,
):
    await _workspace(db_session)
    await _seed_model(db_session, model_id="interrupt-model")
    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=None,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )
    turn = await service.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Run a mutation after thinking.",
    )
    model_started = asyncio.Event()
    release_model = asyncio.Event()
    executor_calls: list[str] = []

    async def blocked_completion(*args, **kwargs):
        del args, kwargs
        model_started.set()
        await release_model.wait()
        return _tool_call_response(
            call_id="interrupt-call",
            name="todo_write",
            arguments={"todos": [{"content": "mutate", "status": "pending"}]},
        )

    async def spy_execute(self, **kwargs):
        del self
        executor_calls.append(kwargs["tool_name"])
        return ToolExecutionResult(action_id="spy", status="completed", result={})

    monkeypatch.setattr("app.services.agent_core.runtime.acompletion", blocked_completion)
    monkeypatch.setattr(AgentToolExecutor, "execute", spy_execute)
    maker = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)

    async with maker() as run_db:
        run_task = asyncio.create_task(AgentCoreRuntime(run_db).run_turn(str(turn.id)))
        await model_started.wait()
        async with maker() as interrupt_db:
            await AgentCoreService(interrupt_db).interrupt_turn(
                turn_id=str(turn.id),
                workspace_id=DEFAULT_WORKSPACE_ID,
                user_id="dev",
            )
        release_model.set()
        interrupted_turn = await run_task

    assert interrupted_turn.status == "cancelled"
    assert executor_calls == []


@pytest.mark.asyncio
async def test_interrupt_between_tool_eligibility_and_action_creation_executes_no_tool(
    db_session,
    db_engine,
    monkeypatch,
):
    await _workspace(db_session)
    calls: list[str] = []
    tool = _CountingMutationTool(calls, name="interrupt-window.mutate")
    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=None,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        permission_mode="bypass",
    )
    turn = await service.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Interrupt after eligibility but before action creation.",
    )
    maker = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    request_entered = asyncio.Event()
    release_request = asyncio.Event()
    original_request_action = AgentActionService.request_action

    async def blocked_request_action(self, *args, **kwargs):
        request_entered.set()
        await release_request.wait()
        return await original_request_action(self, *args, **kwargs)

    monkeypatch.setattr(AgentActionService, "request_action", blocked_request_action)

    async with maker() as run_db:
        run_service = AgentCoreService(run_db)
        claimed_at = datetime.now(timezone.utc)
        claimed_turn = await run_service.turn_repo.claim_for_run(
            str(turn.id),
            claimed_at=claimed_at,
            lease_until=claimed_at + timedelta(minutes=5),
        )
        assert claimed_turn is not None
        agent_session = await run_service.session_repo.get(str(session.id))
        assert agent_session is not None
        controller = AgentLoopController(run_db)
        controller.registry.register(tool)
        tool_calls = [
            {
                "id": "interrupt-window-call",
                "name": tool.name,
                "arguments": {},
            }
        ]
        await controller._append_assistant_tool_calls(
            agent_session=agent_session,
            turn=claimed_turn,
            provider="test",
            model="test",
            tool_calls=tool_calls,
        )
        execute_task = asyncio.create_task(
            controller._execute_tool_calls(
                agent_session=agent_session,
                turn=claimed_turn,
                tool_calls=tool_calls,
            )
        )
        await request_entered.wait()
        async with maker() as interrupt_db:
            await AgentCoreService(interrupt_db).interrupt_turn(
                turn_id=str(turn.id),
                workspace_id=DEFAULT_WORKSPACE_ID,
                user_id="dev",
            )
        release_request.set()
        await asyncio.gather(execute_task, return_exceptions=True)

    async with maker() as inspect_db:
        actions = await AgentActionRepository(inspect_db).list_for_turn(str(turn.id))

    assert calls == []
    assert all(
        action.status
        not in {
            AgentActionStatus.REQUESTED,
            AgentActionStatus.WAITING_DECISION,
            AgentActionStatus.RUNNING,
        }
        for action in actions
    )


@pytest.mark.asyncio
async def test_session_rejects_second_turn_while_first_waits_on_model(
    db_session,
    db_engine,
    monkeypatch,
):
    await _workspace(db_session)
    await _seed_model(db_session, model_id="serialized-turn-model")
    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=None,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )
    first_turn = await service.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="First turn blocks in the model.",
    )
    model_started = asyncio.Event()
    release_model = asyncio.Event()

    async def blocked_completion(*args, **kwargs):
        del args, kwargs
        model_started.set()
        await release_model.wait()

        class FakeMessage:
            content = "First turn complete."
            tool_calls = None

        class FakeChoice:
            message = FakeMessage()

        class FakeResponse:
            usage = None
            choices = [FakeChoice()]

        return FakeResponse()

    monkeypatch.setattr("app.services.agent_core.runtime.acompletion", blocked_completion)
    maker = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)

    async with maker() as run_db:
        run_task = asyncio.create_task(
            AgentCoreRuntime(run_db).run_turn(str(first_turn.id))
        )
        await model_started.wait()
        try:
            async with maker() as competing_db:
                with pytest.raises(ConflictError):
                    await AgentCoreService(competing_db).create_turn_record(
                        session_id=str(session.id),
                        workspace_id=DEFAULT_WORKSPACE_ID,
                        user_id="dev",
                        input_text="Second turn must not enter the transcript yet.",
                    )
        finally:
            release_model.set()
        completed = await run_task

    assert completed.status == "completed"
    async with maker() as inspect_db:
        messages = await AgentMessageRepository(inspect_db).list_for_session(
            str(session.id)
        )
    assert [message.role for message in messages] == ["user", "assistant"]
    async with maker() as next_db:
        next_turn = await AgentCoreService(next_db).create_turn_record(
            session_id=str(session.id),
            workspace_id=DEFAULT_WORKSPACE_ID,
            user_id="dev",
            input_text="A new turn is allowed after the first terminates.",
        )
        assert next_turn.status == "queued"


@pytest.mark.asyncio
async def test_terminal_stale_session_claim_is_replaced_by_new_turn(
    db_session,
):
    await _workspace(db_session)
    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=None,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )
    stale_turn = await service.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="This terminal turn leaves a stale session claim.",
    )
    await service.turn_repo.update_all(
        stale_turn,
        status="completed",
        completed_at=stale_turn.created_at,
    )

    next_turn = await service.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Replace the stale terminal claim atomically.",
    )
    await service.session_repo.release_active_turn(
        str(session.id), str(stale_turn.id)
    )
    await db_session.refresh(session)

    assert session.active_turn_id == str(next_turn.id)


@pytest.mark.asyncio
async def test_concurrent_turn_creation_writes_one_turn_and_one_user_message(
    db_session,
    db_engine,
):
    await _workspace(db_session)
    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=None,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )
    maker = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)

    async def create_once(text):
        async with maker() as independent_db:
            try:
                turn = await AgentCoreService(independent_db).create_turn_record(
                    session_id=str(session.id),
                    workspace_id=DEFAULT_WORKSPACE_ID,
                    user_id="dev",
                    input_text=text,
                )
            except ConflictError:
                return None
            return str(turn.id)

    created = await asyncio.gather(
        create_once("Concurrent turn A"),
        create_once("Concurrent turn B"),
    )
    winner_ids = [turn_id for turn_id in created if turn_id is not None]

    async with maker() as inspect_db:
        turns = await AgentCoreService(inspect_db).turn_repo.list_for_session(
            str(session.id)
        )
        messages = await AgentMessageRepository(inspect_db).list_for_session(
            str(session.id)
        )
        stored_session = await AgentCoreService(inspect_db).session_repo.get(
            str(session.id)
        )

    assert len(winner_ids) == 1
    assert [str(turn.id) for turn in turns] == winner_ids
    assert [message.role for message in messages] == ["user"]
    assert stored_session.active_turn_id == winner_ids[0]


@pytest.mark.asyncio
async def test_turn_claim_and_initial_transcript_commit_atomically(
    db_session,
    db_engine,
):
    await _workspace(db_session)
    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=None,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )
    session_id = str(session.id)
    await db_session.execute(
        text(
            """
            CREATE TRIGGER fail_initial_agent_message
            BEFORE INSERT ON agent_messages
            BEGIN
                SELECT RAISE(ABORT, 'forced initial transcript failure');
            END
            """
        )
    )
    await db_session.commit()

    with pytest.raises(Exception, match="forced initial transcript failure"):
        await service.create_turn_record(
            session_id=session_id,
            workspace_id=DEFAULT_WORKSPACE_ID,
            user_id="dev",
            input_text="This turn must roll back as one aggregate.",
        )
    await db_session.rollback()

    maker = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    async with maker() as inspect_db:
        stored_session = await AgentCoreService(inspect_db).session_repo.get(
            session_id
        )
        turns = await AgentCoreService(inspect_db).turn_repo.list_for_session(
            session_id
        )
        messages = await AgentMessageRepository(inspect_db).list_for_session(
            session_id
        )

    assert stored_session.active_turn_id is None
    assert turns == []
    assert messages == []


@pytest.mark.asyncio
async def test_recovery_skips_running_turn_with_unexpired_lease(
    db_session,
    monkeypatch,
):
    await _workspace(db_session)
    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=None,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )
    turn = await service.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="A different worker still owns this turn.",
    )
    now = datetime.now(timezone.utc)
    await service.turn_repo.update_all(
        turn,
        status="running",
        claimed_at=now,
        lease_until=now + timedelta(minutes=5),
    )
    enqueued: list[str] = []
    monkeypatch.setattr(
        "app.services.agent_core.service.enqueue_turn_run",
        lambda turn_id, _session_id=None: enqueued.append(turn_id),
    )

    summary = await service.recover_orphaned_turns()
    await db_session.refresh(turn)

    assert summary["skipped"] == 1
    assert turn.status == "running"
    assert turn.claimed_at.replace(tzinfo=timezone.utc) == now
    assert turn.lease_until is not None
    assert enqueued == []


@pytest.mark.asyncio
async def test_recovery_cannot_requeue_turn_claimed_after_stale_state_read(
    db_session,
    db_engine,
    monkeypatch,
):
    await _workspace(db_session)
    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=None,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )
    turn = await service.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Race a stale recovery read against a live worker claim.",
    )
    maker = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    recovery_reached_session_claim = asyncio.Event()
    release_recovery = asyncio.Event()
    enqueued: list[str] = []
    monkeypatch.setattr(
        "app.services.agent_core.service.enqueue_turn_run",
        lambda turn_id, _session_id=None: enqueued.append(turn_id),
    )

    async with maker() as recovery_db:
        recovery_service = AgentCoreService(recovery_db)
        original_claim_for_recovery = recovery_service.turn_repo.claim_for_recovery

        async def blocked_claim_for_recovery(*args, **kwargs):
            recovery_reached_session_claim.set()
            await release_recovery.wait()
            return await original_claim_for_recovery(*args, **kwargs)

        monkeypatch.setattr(
            recovery_service.turn_repo,
            "claim_for_recovery",
            blocked_claim_for_recovery,
        )
        recovery_task = asyncio.create_task(recovery_service.recover_orphaned_turns())
        await recovery_reached_session_claim.wait()

        worker_claimed_at = datetime.now(timezone.utc)
        async with maker() as worker_db:
            worker_turn = await AgentCoreService(worker_db).turn_repo.claim_for_run(
                str(turn.id),
                claimed_at=worker_claimed_at,
                lease_until=worker_claimed_at + timedelta(minutes=5),
            )
            assert worker_turn is not None

        release_recovery.set()
        summary = await recovery_task

    async with maker() as inspect_db:
        stored = await AgentCoreService(inspect_db).turn_repo.get(str(turn.id))

    assert stored.status == "running"
    assert stored.claimed_at.replace(tzinfo=timezone.utc) == worker_claimed_at
    assert stored.lease_until is not None
    assert enqueued == []
    assert summary["skipped"] == 1


@pytest.mark.asyncio
async def test_recovery_claim_and_worker_renewal_are_atomic(
    db_session,
    db_engine,
):
    await _workspace(db_session)
    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=None,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )
    turn = await service.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Race recovery against a worker heartbeat.",
    )
    old_claim = datetime.now(timezone.utc) - timedelta(minutes=10)
    await service.turn_repo.update_all(
        turn,
        status="running",
        claimed_at=old_claim,
        lease_until=old_claim + timedelta(minutes=1),
    )
    maker = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    recovery_claim = datetime.now(timezone.utc)

    async def renew_worker():
        async with maker() as renew_db:
            return await AgentCoreService(renew_db).turn_repo.update_if_claimed(
                str(turn.id),
                expected_claimed_at=old_claim,
                lease_until=recovery_claim + timedelta(minutes=5),
            )

    async def claim_recovery():
        async with maker() as recovery_db:
            return await AgentCoreService(
                recovery_db
            ).turn_repo.claim_expired_for_recovery(
                str(turn.id),
                expected_claimed_at=old_claim,
                claimed_at=recovery_claim,
                lease_until=recovery_claim + timedelta(minutes=5),
            )

    renewed, recovered = await asyncio.gather(renew_worker(), claim_recovery())

    assert sum(item is not None for item in (renewed, recovered)) == 1
    async with maker() as inspect_db:
        stored = await AgentCoreService(inspect_db).turn_repo.get(str(turn.id))
    expected_claim = recovery_claim if recovered is not None else old_claim
    assert stored.claimed_at.replace(tzinfo=timezone.utc) == expected_claim


@pytest.mark.asyncio
async def test_stale_turn_owner_cannot_overwrite_takeover_completion(
    db_session,
    db_engine,
):
    await _workspace(db_session)
    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=None,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )
    turn = await service.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Fence stale turn ownership.",
    )
    maker = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    first_claim_time = datetime.now(timezone.utc)

    async with maker() as old_worker_db:
        old_repo = AgentCoreService(old_worker_db).turn_repo
        old_turn = await old_repo.claim_for_run(
            str(turn.id),
            claimed_at=first_claim_time,
            lease_until=first_claim_time + timedelta(seconds=1),
        )
        assert old_turn is not None

        async with maker() as takeover_db:
            takeover_repo = AgentCoreService(takeover_db).turn_repo
            await takeover_repo.update_all(
                await takeover_repo.get(str(turn.id)),
                lease_until=first_claim_time - timedelta(seconds=1),
            )
            takeover_time = first_claim_time + timedelta(seconds=2)
            takeover_turn = await takeover_repo.claim_for_run(
                str(turn.id),
                claimed_at=takeover_time,
                lease_until=takeover_time + timedelta(minutes=5),
            )
            assert takeover_turn is not None
            completed = await AgentLoopController(
                takeover_db
            ).complete_turn_from_result(
                turn=takeover_turn,
                result=LoopResult(
                    termination_reason="assistant_final",
                    final_text="new owner",
                    iteration_count=1,
                ),
            )
            assert completed.final_text == "new owner"

        stale_result = await AgentLoopController(
            old_worker_db
        ).complete_turn_from_result(
            turn=old_turn,
            result=LoopResult(
                termination_reason="assistant_final",
                final_text="stale owner",
                iteration_count=1,
            ),
        )

    async with maker() as inspect_db:
        stored = await AgentCoreService(inspect_db).turn_repo.get(str(turn.id))

    assert stale_result.final_text == "new owner"
    assert stored.final_text == "new owner"


@pytest.mark.asyncio
async def test_stale_stream_owner_emits_no_assistant_events_after_takeover(
    db_session,
    db_engine,
    monkeypatch,
):
    await _workspace(db_session)
    model = await _seed_model(db_session, model_id="stream-owner-model")
    model.supports_streaming = True
    await db_session.commit()
    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=None,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )
    turn = await service.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Do not emit after losing stream ownership.",
    )
    stream_waiting = asyncio.Event()
    release_stream = asyncio.Event()

    async def blocked_stream():
        stream_waiting.set()
        await release_stream.wait()
        yield {"choices": [{"delta": {"content": "stale output"}}]}

    async def fake_completion(*args, **kwargs):
        del args, kwargs
        return blocked_stream()

    monkeypatch.setattr("app.services.agent_core.runtime.acompletion", fake_completion)
    maker = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)

    async with maker() as old_worker_db:
        old_task = asyncio.create_task(
            AgentCoreRuntime(old_worker_db).run_turn(str(turn.id))
        )
        await stream_waiting.wait()
        async with maker() as takeover_db:
            takeover_service = AgentCoreService(takeover_db)
            current = await takeover_service.turn_repo.get(str(turn.id))
            await takeover_service.turn_repo.update_all(
                current,
                lease_until=datetime.now(timezone.utc) - timedelta(seconds=1),
            )
            takeover_time = datetime.now(timezone.utc)
            claimed = await takeover_service.turn_repo.claim_for_run(
                str(turn.id),
                claimed_at=takeover_time,
                lease_until=takeover_time + timedelta(minutes=5),
            )
            assert claimed is not None
        release_stream.set()
        returned = await old_task

    async with maker() as inspect_db:
        events = await AgentEventRepository(inspect_db).list_for_turn(
            turn_id=str(turn.id), after_seq=0
        )

    assert returned.status == "running"
    assert all(not event.type.startswith("assistant.text") for event in events)


@pytest.mark.asyncio
async def test_same_turn_is_claimed_by_only_one_runtime_worker(
    db_session,
    db_engine,
    monkeypatch,
):
    await _workspace(db_session)
    await _seed_model(db_session, model_id="single-worker-model")
    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=None,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )
    turn = await service.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Only one worker may run this turn.",
    )
    model_started = asyncio.Event()
    release_model = asyncio.Event()
    model_calls = 0

    async def blocked_completion(*args, **kwargs):
        nonlocal model_calls
        del args, kwargs
        model_calls += 1
        model_started.set()
        await release_model.wait()

        class FakeMessage:
            content = "Claimed once."
            tool_calls = None

        class FakeChoice:
            message = FakeMessage()

        class FakeResponse:
            usage = None
            choices = [FakeChoice()]

        return FakeResponse()

    monkeypatch.setattr("app.services.agent_core.runtime.acompletion", blocked_completion)
    maker = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)

    async def run_once():
        async with maker() as independent_db:
            return await AgentCoreRuntime(independent_db).run_turn(str(turn.id))

    first = asyncio.create_task(run_once())
    await model_started.wait()
    second = await run_once()
    release_model.set()
    completed = await first

    assert second.status == "running"
    assert completed.status == "completed"
    assert model_calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("forced_dialect", [None, "legacy"])
async def test_tool_result_append_is_atomic_across_sessions(
    db_session,
    db_engine,
    monkeypatch,
    forced_dialect,
):
    await _workspace(db_session)
    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=None,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )
    turn = await service.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Append one durable tool result.",
    )
    await AgentTranscriptStore(db_session).append_parts(
        session_id=str(session.id),
        turn_id=str(turn.id),
        role="assistant",
        parts=[
            tool_calls_part(
                [
                    {
                        "id": "atomic-result-call",
                        "type": "function",
                        "function": {"name": "projects.list", "arguments": "{}"},
                    }
                ]
            )
        ],
    )
    maker = async_sessionmaker(db_engine, expire_on_commit=False, class_=AsyncSession)
    if forced_dialect is not None:
        monkeypatch.setattr(db_engine.dialect, "name", forced_dialect)
    original_next_index = AgentMessageRepository.next_ordering_index
    both_read_index = asyncio.Event()
    arrivals = 0
    arrivals_lock = asyncio.Lock()

    async def synchronized_next_index(repository, session_id):
        nonlocal arrivals
        value = await original_next_index(repository, session_id)
        async with arrivals_lock:
            arrivals += 1
            if arrivals == 2:
                both_read_index.set()
        await both_read_index.wait()
        return value

    monkeypatch.setattr(
        AgentMessageRepository,
        "next_ordering_index",
        synchronized_next_index,
    )

    async def append_once():
        async with maker() as independent_db:
            return await AgentTranscriptStore(independent_db).append_tool_result_once(
                session_id=str(session.id),
                turn_id=str(turn.id),
                tool_call_id="atomic-result-call",
                tool_name="projects.list",
                status="completed",
                result={"ok": True},
            )

    outcomes = await asyncio.gather(append_once(), append_once())

    async with maker() as inspect_db:
        messages = await AgentMessageRepository(inspect_db).list_for_session(
            str(session.id)
        )
    stored_results = [
        message
        for message in messages
        if message.role == "tool"
        and str(message.turn_id) == str(turn.id)
        and (message.message_metadata or {}).get("tool_call_id")
        == "atomic-result-call"
    ]
    assert sorted(outcomes) == [False, True]
    assert len(stored_results) == 1
    async with maker() as unresolved_db:
        assert await AgentTranscriptStore(unresolved_db).unresolved_tool_calls(
            str(session.id), turn_id=str(turn.id)
        ) == []


@pytest.mark.asyncio
async def test_nonstream_tool_call_ids_are_unique_when_provider_omits_or_reuses_them(
    db_session,
):
    await _workspace(db_session)
    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=None,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )
    turn = await service.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Normalize provider tool call identities.",
    )
    controller = AgentLoopController(db_session)

    first = await controller._consume_response(
        agent_session=session,
        turn=turn,
        response=_tool_call_response(
            call_id=None,
            name="projects.list",
            arguments={},
        ),
        message_id=f"assistant:{turn.id}:1",
        allow_thinking=False,
    )
    await controller._append_assistant_tool_calls(
        agent_session=session,
        turn=turn,
        provider="test",
        model="test",
        tool_calls=[
            {
                "id": first.tool_calls[0].call_id,
                "name": first.tool_calls[0].name,
                "arguments": first.tool_calls[0].arguments(),
            }
        ],
    )
    second = await controller._consume_response(
        agent_session=session,
        turn=turn,
        response=_tool_call_response(
            call_id=None,
            name="projects.list",
            arguments={},
        ),
        message_id=f"assistant:{turn.id}:2",
        allow_thinking=False,
    )
    await controller._append_assistant_tool_calls(
        agent_session=session,
        turn=turn,
        provider="test",
        model="test",
        tool_calls=[
            {
                "id": "provider-reused-id",
                "name": "projects.list",
                "arguments": {},
            }
        ],
    )
    reused = await controller._consume_response(
        agent_session=session,
        turn=turn,
        response=_tool_call_response(
            call_id="provider-reused-id",
            name="projects.list",
            arguments={},
        ),
        message_id=f"assistant:{turn.id}:3",
        allow_thinking=False,
    )

    assert first.tool_calls[0].call_id != second.tool_calls[0].call_id
    assert reused.tool_calls[0].call_id != "provider-reused-id"


@pytest.mark.asyncio
async def test_stream_tool_call_ids_are_unique_when_provider_omits_them(
    db_session,
):
    await _workspace(db_session)
    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=None,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )
    turn = await service.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Normalize streamed tool call identities.",
    )
    claim_time = datetime.now(timezone.utc)
    turn = await service.turn_repo.claim_for_run(
        str(turn.id),
        claimed_at=claim_time,
        lease_until=claim_time + timedelta(minutes=5),
    )
    assert turn is not None
    controller = AgentLoopController(db_session)

    async def missing_id_stream():
        yield {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [
                            {
                                "index": 0,
                                "function": {
                                    "name": "projects.list",
                                    "arguments": "{}",
                                },
                            }
                        ]
                    }
                }
            ]
        }

    first = await controller._consume_stream_response(
        agent_session=session,
        turn=turn,
        response=missing_id_stream(),
        message_id=f"assistant:{turn.id}:1",
        allow_thinking=False,
    )
    second = await controller._consume_stream_response(
        agent_session=session,
        turn=turn,
        response=missing_id_stream(),
        message_id=f"assistant:{turn.id}:2",
        allow_thinking=False,
    )

    assert first.tool_calls[0].call_id != second.tool_calls[0].call_id


@pytest.mark.asyncio
async def test_interrupt_closes_already_emitted_tool_call_before_execution(
    db_session,
    monkeypatch,
):
    await _workspace(db_session)
    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=None,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )
    turn = await service.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Emit, then interrupt.",
    )
    controller = AgentLoopController(db_session)
    tool_calls = [
        {
            "id": "emitted-interrupt-call",
            "name": "todo_write",
            "arguments": {"todos": [{"content": "mutate", "status": "pending"}]},
        }
    ]
    await controller._append_assistant_tool_calls(
        agent_session=session,
        turn=turn,
        provider="test",
        model="test",
        tool_calls=tool_calls,
    )
    executor_calls: list[str] = []

    async def spy_execute(self, **kwargs):
        del self
        executor_calls.append(kwargs["tool_name"])
        return ToolExecutionResult(action_id="spy", status="completed", result={})

    monkeypatch.setattr(AgentToolExecutor, "execute", spy_execute)
    await service.interrupt_turn(
        turn_id=str(turn.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )

    with pytest.raises(asyncio.CancelledError):
        await controller._execute_tool_calls(
            agent_session=session,
            turn=turn,
            tool_calls=tool_calls,
        )

    messages = await AgentMessageRepository(db_session).list_for_session(str(session.id))
    results = [
        message
        for message in messages
        if message.role == "tool"
        and (message.message_metadata or {}).get("tool_call_id")
        == "emitted-interrupt-call"
    ]
    assert executor_calls == []
    assert len(results) == 1
    assert json.loads(results[0].content_parts[0]["text"])["status"] == "cancelled"


@pytest.mark.asyncio
async def test_permission_denied_tool_call_is_closed_exactly_once(
    db_session,
    monkeypatch,
):
    await _workspace(db_session)
    await _seed_model(db_session, model_id="permission-model")

    async def unexposed_completion(*args, **kwargs):
        del args, kwargs
        return _tool_call_response(
            call_id="permission-call",
            name="bash",
            arguments={"command": "pwd"},
        )

    monkeypatch.setattr("app.services.agent_core.runtime.acompletion", unexposed_completion)
    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=None,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        toolset_policy={"name": "plan"},
    )
    turn = await service.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Try a hidden mutation.",
    )

    failed_turn = await service.runtime.run_turn(str(turn.id))
    messages = await AgentMessageRepository(db_session).list_for_session(str(session.id))
    matching_results = [
        message
        for message in messages
        if message.role == "tool"
    ]

    assert failed_turn.status == "failed"
    assert len(matching_results) == 1
    assert (matching_results[0].message_metadata or {})["tool_call_id"].startswith(
        "tc_"
    )
    payload = json.loads(matching_results[0].content_parts[0]["text"])
    assert payload["status"] == "failed"
    assert payload["error"]["type"] == "PermissionDeniedError"


@pytest.mark.asyncio
async def test_cancel_pending_action_closes_its_tool_call_once(
    db_session,
    monkeypatch,
):
    await _workspace(db_session)
    await _seed_model(db_session, model_id="cancel-model")

    async def approval_completion(*args, **kwargs):
        del args, kwargs
        response = _tool_call_response(
            call_id="cancel-call",
            name="bash",
            arguments={
                "command": f"{sys.executable} -c 'print(1)'",
                "cwd": str(settings.bioinfoflow_home),
            },
        )
        deferred = _tool_call_response(
            call_id="cancel-deferred-call",
            name="projects__list",
            arguments={},
        )
        response.choices[0].message.tool_calls.append(
            deferred.choices[0].message.tool_calls[0]
        )
        return response

    monkeypatch.setattr("app.services.agent_core.runtime.acompletion", approval_completion)
    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=None,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )
    turn = await service.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Request approval then cancel.",
    )
    waiting = await service.runtime.run_turn(str(turn.id))
    assert waiting.status == "waiting_approval"

    await service.cancel_turn(
        turn_id=str(turn.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )
    messages = await AgentMessageRepository(db_session).list_for_session(str(session.id))
    results = {
        (message.message_metadata or {}).get("tool_call_id"): json.loads(
            message.content_parts[0]["text"]
        )
        for message in messages
        if message.role == "tool"
    }
    assistant_call_ids = {
        call["id"]
        for message in messages
        if message.role == "assistant"
        for part in message.content_parts
        if part.get("type") == "tool_calls"
        for call in part.get("tool_calls") or []
    }

    assert set(results) == assistant_call_ids
    assert sorted(item["status"] for item in results.values()) == [
        "cancelled",
        "deferred",
    ]


@pytest.mark.asyncio
async def test_new_turn_conflicts_with_prior_unresolved_tool_call(
    db_session,
    monkeypatch,
):
    await _workspace(db_session)
    await _seed_model(db_session, model_id="serialize-model")

    async def approval_completion(*args, **kwargs):
        del args, kwargs
        return _tool_call_response(
            call_id="serialize-call",
            name="bash",
            arguments={
                "command": f"{sys.executable} -c 'print(1)'",
                "cwd": str(settings.bioinfoflow_home),
            },
        )

    monkeypatch.setattr("app.services.agent_core.runtime.acompletion", approval_completion)
    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=None,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )
    first = await service.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="First turn.",
    )
    assert (await service.runtime.run_turn(str(first.id))).status == "waiting_approval"

    with pytest.raises(ConflictError, match="unresolved"):
        await service.create_turn_record(
            session_id=str(session.id),
            workspace_id=DEFAULT_WORKSPACE_ID,
            user_id="dev",
            input_text="Second turn must wait.",
        )


@pytest.mark.asyncio
async def test_unmatched_transcript_tool_call_blocks_new_turn_without_loop_state(
    db_session,
):
    await _workspace(db_session)
    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=None,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )
    turn = await service.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Crash after emitting a tool call.",
    )
    await AgentTranscriptStore(db_session).append_parts(
        session_id=str(session.id),
        turn_id=str(turn.id),
        role="assistant",
        parts=[
            tool_calls_part(
                [
                    {
                        "id": "orphan-call",
                        "type": "function",
                        "function": {"name": "projects__list", "arguments": "{}"},
                    }
                ]
            )
        ],
    )

    with pytest.raises(ConflictError, match="unresolved"):
        await service.create_turn_record(
            session_id=str(session.id),
            workspace_id=DEFAULT_WORKSPACE_ID,
            user_id="dev",
            input_text="Do not replay across the orphan call.",
        )


@pytest.mark.asyncio
async def test_recovery_closes_unmatched_transcript_call_without_action(
    db_session,
    monkeypatch,
):
    await _workspace(db_session)
    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=None,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )
    turn = await service.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Recover an orphan tool call.",
    )
    await service.turn_repo.update_all(turn, status="running")
    await AgentTranscriptStore(db_session).append_parts(
        session_id=str(session.id),
        turn_id=str(turn.id),
        role="assistant",
        parts=[
            tool_calls_part(
                [
                    {
                        "id": "recovery-orphan-call",
                        "type": "function",
                        "function": {"name": "projects__list", "arguments": "{}"},
                    }
                ]
            )
        ],
    )
    enqueued: list[str] = []
    monkeypatch.setattr(
        "app.services.agent_core.service.enqueue_turn_run",
        lambda turn_id, _session_id=None: enqueued.append(turn_id),
    )

    summary = await service.recover_orphaned_turns()
    unresolved = await AgentTranscriptStore(db_session).unresolved_tool_calls(
        str(session.id),
        turn_id=str(turn.id),
    )
    messages = await AgentMessageRepository(db_session).list_for_session(str(session.id))
    result = next(
        message
        for message in messages
        if message.role == "tool"
        and (message.message_metadata or {}).get("tool_call_id")
        == "recovery-orphan-call"
    )

    assert summary["enqueued"] == 1
    assert enqueued == [str(turn.id)]
    assert unresolved == []
    payload = json.loads(result.content_parts[0]["text"])
    assert payload["status"] == "failed"
    assert payload["error"]["type"] == "RecoveryInterruptedToolCall"

@pytest.mark.asyncio
async def test_compaction_keeps_tool_call_and_result_on_same_side_of_boundary(
    db_session,
):
    await _workspace(db_session)
    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=None,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )
    turn = await service.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Old user message " * 20,
    )
    transcript = AgentTranscriptStore(db_session)
    assistant_call = await transcript.append_parts(
        session_id=str(session.id),
        turn_id=str(turn.id),
        role="assistant",
        parts=[
            tool_calls_part(
                [
                    {
                        "id": "compact-call",
                        "type": "function",
                        "function": {"name": "projects__list", "arguments": "{}"},
                    }
                ]
            )
        ],
    )
    tool_result = await transcript.append_parts(
        session_id=str(session.id),
        turn_id=str(turn.id),
        role="tool",
        parts=[text_part('{"status":"completed"}')],
        metadata={"tool_call_id": "compact-call", "tool": "projects.list"},
    )
    await transcript.append_text(
        session_id=str(session.id),
        turn_id=str(turn.id),
        role="user",
        text="Recent user message.",
    )
    await transcript.append_text(
        session_id=str(session.id),
        turn_id=str(turn.id),
        role="assistant",
        text="Recent assistant message.",
    )

    await transcript.compact_session(
        session_id=str(session.id),
        turn_id=str(turn.id),
        threshold_chars=1,
        preserve_recent_messages=3,
    )
    await db_session.refresh(assistant_call)
    await db_session.refresh(tool_result)

    assert assistant_call.status == tool_result.status


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("terminal_status", "terminal_result", "terminal_error"),
    [
        (AgentActionStatus.COMPLETED, {"exit_code": 0, "stdout": "already done"}, None),
        (
            AgentActionStatus.FAILED,
            None,
            {"type": "ToolError", "message": "already failed"},
        ),
        (
            AgentActionStatus.CANCELLED,
            None,
            {"type": "CancelledError", "message": "already cancelled"},
        ),
    ],
)
async def test_recovery_closes_terminal_action_pending_observation(
    db_session,
    monkeypatch,
    terminal_status,
    terminal_result,
    terminal_error,
):
    await _workspace(db_session)
    await _seed_model(db_session, model_id="reconcile-model")

    async def approval_completion(*args, **kwargs):
        del args, kwargs
        return _tool_call_response(
            call_id="reconcile-call",
            name="bash",
            arguments={
                "command": f"{sys.executable} -c 'print(1)'",
                "cwd": str(settings.bioinfoflow_home),
            },
        )

    enqueued: list[str] = []
    monkeypatch.setattr("app.services.agent_core.runtime.acompletion", approval_completion)
    monkeypatch.setattr(
        "app.services.agent_core.service.enqueue_turn_run",
        lambda turn_id, _session_id=None: enqueued.append(turn_id),
    )
    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=None,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )
    turn = await service.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Recover terminal result.",
    )
    waiting = await service.runtime.run_turn(str(turn.id))
    assert waiting.status == "waiting_approval"
    action = (await AgentActionRepository(db_session).list_for_turn(str(turn.id)))[0]
    await AgentActionRepository(db_session).update_all(
        action,
        status=terminal_status,
        result=terminal_result,
        error=terminal_error,
        requires_resume=False,
    )

    summary = await service.recover_orphaned_turns()
    recovered = await service.turn_repo.get(str(turn.id))
    messages = await AgentMessageRepository(db_session).list_for_session(str(session.id))
    results = [
        message
        for message in messages
        if message.role == "tool"
        and (message.message_metadata or {}).get("tool_call_id") == action.tool_call_id
    ]

    assert summary["enqueued"] == 1
    assert enqueued == [str(turn.id)]
    assert len(results) == 1
    assert json.loads(results[0].content_parts[0]["text"])["status"] == terminal_status
    assert "pending_observation" not in recovered.loop_state["progress"]


@pytest.mark.asyncio
async def test_recovery_cancels_running_action_and_closes_pending_call(
    db_session,
    monkeypatch,
):
    await _workspace(db_session)
    await _seed_model(db_session, model_id="running-recovery-model")

    async def approval_completion(*args, **kwargs):
        del args, kwargs
        return _tool_call_response(
            call_id="running-recovery-call",
            name="bash",
            arguments={
                "command": f"{sys.executable} -c 'print(1)'",
                "cwd": str(settings.bioinfoflow_home),
            },
        )

    monkeypatch.setattr("app.services.agent_core.runtime.acompletion", approval_completion)
    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=None,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )
    turn = await service.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Recover an in-flight action.",
    )
    assert (await service.runtime.run_turn(str(turn.id))).status == "waiting_approval"
    action = (await AgentActionRepository(db_session).list_for_turn(str(turn.id)))[0]
    await AgentActionRepository(db_session).update_all(
        action,
        status=AgentActionStatus.RUNNING,
        requires_resume=False,
    )

    summary = await service.recover_orphaned_turns()
    recovered = await service.turn_repo.get(str(turn.id))
    messages = await AgentMessageRepository(db_session).list_for_session(str(session.id))
    results = [
        message
        for message in messages
        if message.role == "tool"
        and (message.message_metadata or {}).get("tool_call_id")
        == action.tool_call_id
    ]

    assert summary["failed"] == 1
    assert recovered.status == "failed"
    assert recovered.error_code == "recovery_inflight_action"
    assert len(results) == 1
    assert json.loads(results[0].content_parts[0]["text"])["status"] == "cancelled"
