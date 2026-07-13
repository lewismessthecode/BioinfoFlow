from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import dataclass

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.agent_core import AgentActionStatus
from app.models.llm import LlmModel, LlmProvider
from app.models.workspace import Workspace
from app.repositories.agent_core_repo import (
    AgentActionRepository,
    AgentMessageRepository,
)
from app.config import settings
from app.services.agent_core import AgentCoreService
from app.services.agent_core.core import AgentLoopController
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
        and (message.message_metadata or {}).get("tool_call_id") == "permission-call"
    ]

    assert failed_turn.status == "failed"
    assert len(matching_results) == 1
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

    assert set(results) == {"cancel-call", "cancel-deferred-call"}
    assert results["cancel-call"]["status"] == "cancelled"
    assert results["cancel-deferred-call"]["status"] == "deferred"


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
        and (message.message_metadata or {}).get("tool_call_id") == "reconcile-call"
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
        == "running-recovery-call"
    ]

    assert summary["failed"] == 1
    assert recovered.status == "failed"
    assert recovered.error_code == "recovery_inflight_action"
    assert len(results) == 1
    assert json.loads(results[0].content_parts[0]["text"])["status"] == "cancelled"
