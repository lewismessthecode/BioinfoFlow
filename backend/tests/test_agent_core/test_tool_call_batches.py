from __future__ import annotations

import json
import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app.config import settings
from app.models.agent_core import (
    AgentActionStatus,
    AgentToolCallBatchStatus,
    AgentTurnStatus,
)
from app.models.llm import LlmModel, LlmProvider
from app.models.workspace import Workspace
from app.repositories.agent_core_repo import (
    AgentActionRepository,
    AgentEventRepository,
    AgentMessageRepository,
    AgentSessionRepository,
    AgentToolCallBatchRepository,
    AgentTurnRepository,
)
from app.services.agent_core import AgentCoreService
from app.services.agent_core.context import AgentContextAssembler
from app.services.agent_core.core.loop import AgentLoopController
from app.services.agent_core.ownership import TurnOwnership, TurnOwnershipLostError
from app.services.agent_core.transcript import AgentTranscriptStore, tool_calls_part
from app.services.agent_core.tools.batches import ToolCallBatchCoordinator
from app.services.agent_core.tools.execution import ExecuteShellTool
from app.services.agent_core.tools.executor import ToolExecutionResult
from app.services.agent_core.tools.specs import AgentToolSpec
from app.services.model_runtime.contracts import (
    CompletionMetadata,
    ModelInvocation,
    ModelTarget,
    ResponseStarted,
    TextDelta,
    TextPart,
    ToolCallDelta,
    ToolCallPart,
    ToolResultPart,
    UsageReport,
)
from app.services.model_runtime.gateway import ModelGateway
from app.schemas.agent_core import AgentActionRead
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from app.workspace import DEFAULT_WORKSPACE_ID


async def _seed_runtime(db_session) -> None:
    db_session.add(Workspace(id=DEFAULT_WORKSPACE_ID, name="Team", slug="team"))
    provider = LlmProvider(
        name="batch provider",
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
    db_session.add(
        LlmModel(
            provider_id=str(provider.id),
            model_id="batch-model",
            display_name="batch-model",
            supports_tools=True,
            supports_streaming=False,
        )
    )
    await db_session.commit()


async def _mark_turn_as_expired_execution(service, turn):
    now = datetime.now(timezone.utc)
    return await service.turn_repo.update_all(
        turn,
        status=AgentTurnStatus.RUNNING,
        claimed_at=now - timedelta(minutes=2),
        lease_until=now - timedelta(minutes=1),
        owner_token="expired-worker",
    )


def test_action_read_contract_exposes_batch_identity_and_ordinal():
    assert "tool_batch_id" in AgentActionRead.model_fields
    assert "tool_call_ordinal" in AgentActionRead.model_fields


def _response(*, tool_calls: list[tuple[str, str, dict]] | None = None, text: str = ""):
    class Usage:
        def model_dump(self):
            return {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}

    class Response:
        usage = Usage()

    class Choice:
        pass

    class Message:
        pass

    message = Message()
    message.content = text
    message.tool_calls = []
    for call_id, name, arguments in tool_calls or []:
        function = type(
            "Function", (), {"name": name, "arguments": json.dumps(arguments)}
        )()
        message.tool_calls.append(
            type("ToolCall", (), {"id": call_id, "function": function})()
        )
    if not message.tool_calls:
        message.tool_calls = None
    choice = Choice()
    choice.message = message
    response = Response()
    response.choices = [choice]
    return response


def _legacy_messages(invocation: ModelInvocation) -> list[dict]:
    messages: list[dict] = []
    for item in invocation.input_items:
        if isinstance(item, TextPart):
            messages.append(
                {
                    "role": "assistant" if item.phase is not None else "user",
                    "content": item.text,
                }
            )
        elif isinstance(item, ToolCallPart):
            messages.append(
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": item.call_id,
                            "type": "function",
                            "function": {
                                "name": item.name,
                                "arguments": json.dumps(item.arguments),
                            },
                        }
                    ],
                }
            )
        elif isinstance(item, ToolResultPart):
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": item.call_id,
                    "content": item.output,
                }
            )
    return messages


def _patch_model_gateway(monkeypatch, completion) -> None:
    async def invoke(_gateway, invocation: ModelInvocation):
        response = await completion(
            model=invocation.target.model_name,
            messages=_legacy_messages(invocation),
        )
        yield ResponseStarted(streaming=False)
        message = response.choices[0].message
        for index, tool_call in enumerate(message.tool_calls or []):
            yield ToolCallDelta(
                index=index,
                call_id=tool_call.id,
                name=tool_call.function.name,
                arguments_delta=tool_call.function.arguments,
            )
        if message.content:
            yield TextDelta(text=message.content)
        usage = response.usage.model_dump()
        yield UsageReport(
            input_tokens=usage["prompt_tokens"],
            output_tokens=usage["completion_tokens"],
            total_tokens=usage["total_tokens"],
        )
        yield CompletionMetadata(
            response_id=None,
            finish_reason="tool_calls" if message.tool_calls else "stop",
        )

    monkeypatch.setattr(ModelGateway, "invoke", invoke)


def _target() -> ModelTarget:
    return ModelTarget(
        endpoint_id="batch-provider",
        provider_kind="openai_compatible",
        model_name="batch-model",
        routed_model_name="batch-model",
        wire_protocol="chat_completions",
    )


def _ownership(session: AsyncSession, *, turn_id: str, token: str) -> TurnOwnership:
    assert session.bind is not None
    return TurnOwnership(
        bind=session.bind,
        turn_id=turn_id,
        owner_token=token,
        lease_duration=timedelta(minutes=1),
    )


def _test_tool_spec(**overrides) -> AgentToolSpec:
    values = {
        "name": "test.read",
        "description": "Test tool.",
        "input_schema": {"type": "object"},
        "output_schema": {"type": "object"},
        "risk_level": "read",
    }
    values.update(overrides)
    return AgentToolSpec(**values)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"risk_level": "act_low", "parallel_safe": True}, "read-only"),
        ({"write_scope": ["workspace"], "parallel_safe": True}, "write scope"),
        (
            {"interaction": "user_input", "parallel_safe": True},
            "interaction",
        ),
    ],
)
def test_parallel_safe_tool_metadata_rejects_unsafe_specs(overrides, message):
    with pytest.raises(ValueError, match=message):
        _test_tool_spec(**overrides)


def test_ordered_tool_segments_keep_approval_and_interaction_as_barriers(db_session):
    controller = AgentLoopController(db_session)
    requested = ToolExecutionResult(action_id="requested", status="requested")
    approval = ToolExecutionResult(
        action_id="approval",
        status="waiting_decision",
        requires_resume=True,
    )
    prepared = [
        ({"id": "read-1"}, "projects.list", requested),
        ({"id": "read-2"}, "projects.get", requested),
        ({"id": "approval"}, "projects.list", approval),
        ({"id": "read-3"}, "projects.list", requested),
        ({"id": "interaction"}, "ask_user", requested),
        ({"id": "read-4"}, "projects.list", requested),
    ]

    segments = controller._ordered_tool_execution_segments(prepared)

    assert [[item[0]["id"] for item in segment] for segment in segments] == [
        ["read-1", "read-2"],
        ["approval"],
        ["read-3"],
        ["interaction"],
        ["read-4"],
    ]


@pytest.mark.asyncio
async def test_tool_batch_parallelizes_only_adjacent_safe_calls(
    db_session,
    monkeypatch,
):
    await _seed_runtime(db_session)
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
        input_text="Preserve tool-call barriers.",
    )
    controller = AgentLoopController(db_session)
    events: list[str] = []
    safe_call_count = 0
    original_isolated = controller._execute_tool_call_isolated
    original_resume = controller.executor.resume_action

    async def observe_isolated(**kwargs):
        nonlocal safe_call_count
        ordinal = safe_call_count
        safe_call_count += 1
        events.append(f"safe-{ordinal}-start")
        result = await original_isolated(**kwargs)
        events.append(f"safe-{ordinal}-end")
        return result

    async def observe_serial(**kwargs):
        events.append("serial-start")
        result = await original_resume(**kwargs)
        events.append("serial-end")
        return result

    monkeypatch.setattr(controller, "_execute_tool_call_isolated", observe_isolated)
    monkeypatch.setattr(controller.executor, "resume_action", observe_serial)

    await controller._execute_tool_calls(
        agent_session=session,
        turn=turn,
        tool_calls=[
            {"id": "read-before", "name": "projects__list", "arguments": {}},
            {
                "id": "serial",
                "name": "todo_write",
                "arguments": {
                    "todos": [{"content": "barrier", "status": "in_progress"}]
                },
            },
            {"id": "read-after", "name": "projects__list", "arguments": {}},
        ],
        provider="openai_compatible",
        model="batch-model",
    )

    assert events == [
        "safe-0-start",
        "safe-0-end",
        "serial-start",
        "serial-end",
        "safe-1-start",
        "safe-1-end",
    ]

    messages = await AgentMessageRepository(db_session).list_for_session(
        str(session.id)
    )
    assert [
        message.message_metadata["tool_call_id"]
        for message in messages
        if message.role == "tool"
    ] == ["read-before", "serial", "read-after"]


@pytest.mark.asyncio
async def test_three_approvals_continue_only_after_entire_batch_is_terminal(
    db_session,
    monkeypatch,
):
    calls = 0

    async def fake_completion(*args, **kwargs):
        nonlocal calls
        del args
        calls += 1
        if calls == 1:
            return _response(
                tool_calls=[
                    ("call-1", "bash", {"command": "printf one"}),
                    ("call-2", "bash", {"command": "printf two"}),
                    ("call-3", "bash", {"command": "printf three"}),
                ]
            )
        tool_results = [item for item in kwargs["messages"] if item["role"] == "tool"]
        assert [item["tool_call_id"] for item in tool_results] == [
            "call-1",
            "call-2",
            "call-3",
        ]
        assert len({item["tool_call_id"] for item in tool_results}) == 3
        return _response(text="batch complete")

    _patch_model_gateway(monkeypatch, fake_completion)
    monkeypatch.setattr(
        "app.services.agent_core.service.enqueue_turn_resume", lambda *_: None
    )
    await _seed_runtime(db_session)
    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=None,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        permission_mode="ask_each_action",
    )
    turn = await service.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Run three commands.",
    )
    waiting = await service.runtime.run_turn(str(turn.id))

    assert waiting.status == "waiting_approval"
    actions = await AgentActionRepository(db_session).list_for_turn(str(turn.id))
    actions.sort(key=lambda action: action.tool_call_ordinal)
    assert [action.tool_call_ordinal for action in actions] == [0, 1, 2]
    assert len({action.tool_batch_id for action in actions}) == 1
    batch = await AgentToolCallBatchRepository(db_session).get(
        str(actions[0].tool_batch_id)
    )
    assert batch is not None
    assert batch.status == AgentToolCallBatchStatus.WAITING

    for action in actions[:2]:
        await service.decide_action(
            action_id=str(action.id),
            workspace_id=DEFAULT_WORKSPACE_ID,
            user_id="dev",
            decision="approve",
        )
        assert calls == 1

    await service.decide_action(
        action_id=str(actions[2].id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        decision="reject",
    )
    # The in-process runner coalesces wakeups by turn and may retain only the
    # latest action id. That wakeup must drain every persisted requested action
    # in the batch; correctness cannot depend on one callback per decision.
    completed = await service.runtime.resume_turn_after_action(str(actions[2].id))

    assert completed.status == "completed"
    assert completed.final_text == "batch complete"
    assert calls == 2
    messages = await AgentMessageRepository(db_session).list_for_session(
        str(session.id)
    )
    tool_messages = [message for message in messages if message.role == "tool"]
    assert [message.message_metadata["tool_call_id"] for message in tool_messages] == [
        "call-1",
        "call-2",
        "call-3",
    ]
    batch = await AgentToolCallBatchRepository(db_session).get(
        str(actions[0].tool_batch_id)
    )
    assert batch is not None
    assert batch.status == AgentToolCallBatchStatus.TERMINAL


@pytest.mark.asyncio
async def test_decision_during_running_resume_is_durably_drained_once(
    db_session,
    monkeypatch,
):
    model_calls = 0

    async def fake_completion(*args, **kwargs):
        nonlocal model_calls
        del args, kwargs
        model_calls += 1
        if model_calls == 1:
            return _response(
                tool_calls=[
                    ("race-first", "bash", {"command": "first"}),
                    ("race-second", "bash", {"command": "second"}),
                ]
            )
        return _response(text="race complete")

    side_effects: list[str] = []

    async def record_run(self, input, context):
        del self, context
        side_effects.append(str(input["command"]))
        return {
            "exit_code": 0,
            "stdout": "ok",
            "stderr": "",
            "cwd": ".",
            "command": input["command"],
        }

    _patch_model_gateway(monkeypatch, fake_completion)
    monkeypatch.setattr(ExecuteShellTool, "run", record_run)
    monkeypatch.setattr(
        "app.services.agent_core.service.enqueue_turn_resume", lambda *_: None
    )
    await _seed_runtime(db_session)
    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=None,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        permission_mode="ask_each_action",
    )
    turn = await service.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Run both race commands.",
    )
    waiting = await service.runtime.run_turn(str(turn.id))
    assert waiting.status == AgentTurnStatus.WAITING_APPROVAL
    actions = await AgentActionRepository(db_session).list_for_turn(str(turn.id))
    actions.sort(key=lambda item: item.tool_call_ordinal)
    await service.decide_action(
        action_id=str(actions[0].id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        decision="approve",
    )

    settle_entered = asyncio.Event()
    release_settle = asyncio.Event()
    original_settle = ToolCallBatchCoordinator.settle

    async def pause_resume_settle(coordinator, batch_id):
        settle_entered.set()
        await release_settle.wait()
        return await original_settle(coordinator, batch_id)

    monkeypatch.setattr(ToolCallBatchCoordinator, "settle", pause_resume_settle)
    maker = async_sessionmaker(
        bind=db_session.bind,
        expire_on_commit=False,
        class_=AsyncSession,
    )

    async def resume_first():
        async with maker() as worker:
            return await AgentCoreService(worker).runtime.resume_turn_after_action(
                str(actions[0].id)
            )

    resume_task = asyncio.create_task(resume_first())
    await asyncio.wait_for(settle_entered.wait(), timeout=2)
    async with maker() as decision_session:
        await AgentCoreService(decision_session).decide_action(
            action_id=str(actions[1].id),
            workspace_id=DEFAULT_WORKSPACE_ID,
            user_id="dev",
            decision="approve",
        )
        running = await AgentTurnRepository(decision_session).get_fresh(str(turn.id))
        assert running.status == AgentTurnStatus.RUNNING
        assert running.owner_token is not None
        assert running.resume_batch_token == str(actions[1].tool_batch_id)
    release_settle.set()
    completed = await asyncio.wait_for(resume_task, timeout=3)

    assert completed.status == AgentTurnStatus.COMPLETED
    assert completed.final_text == "race complete"
    assert side_effects == ["first", "second"]
    assert model_calls == 2
    async with maker() as observer:
        persisted = await AgentActionRepository(observer).list_for_turn(str(turn.id))
    assert [
        item.status for item in sorted(persisted, key=lambda i: i.tool_call_ordinal)
    ] == [
        AgentActionStatus.COMPLETED,
        AgentActionStatus.COMPLETED,
    ]


@pytest.mark.asyncio
async def test_batch_repository_restart_decision_uses_persisted_action_state(
    db_session,
):
    await _seed_runtime(db_session)
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
        input_text="Recover this batch.",
    )
    batches = AgentToolCallBatchRepository(db_session)
    batch = await batches.create(
        session_id=str(session.id),
        turn_id=str(turn.id),
        status=AgentToolCallBatchStatus.WAITING,
        tool_call_count=2,
    )
    actions = AgentActionRepository(db_session)
    for ordinal, status in enumerate(
        [AgentActionStatus.COMPLETED, AgentActionStatus.WAITING_DECISION]
    ):
        await actions.create(
            session_id=str(session.id),
            turn_id=str(turn.id),
            tool_batch_id=str(batch.id),
            tool_call_ordinal=ordinal,
            tool_call_id=f"recover-{ordinal}",
            kind="tool",
            name="bash",
            input={},
            risk_level="act_high",
            status=status,
        )

    assert await batches.continuation_state(str(batch.id)) == "waiting"
    second = (await actions.list_for_batch(str(batch.id)))[1]
    await actions.update_all(second, status=AgentActionStatus.REJECTED)

    assert await batches.continuation_state(str(batch.id)) == "ready"


@pytest.mark.asyncio
async def test_incompletely_persisted_batch_never_becomes_ready(db_session):
    await _seed_runtime(db_session)
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
        input_text="Persist every call before continuation.",
    )
    batches = AgentToolCallBatchRepository(db_session)
    batch = await batches.create(
        session_id=str(session.id),
        turn_id=str(turn.id),
        status=AgentToolCallBatchStatus.EVALUATING,
        tool_call_count=2,
    )
    await AgentActionRepository(db_session).create(
        session_id=str(session.id),
        turn_id=str(turn.id),
        tool_batch_id=str(batch.id),
        tool_call_ordinal=0,
        tool_call_id="only-one",
        kind="tool",
        name="projects.list",
        input={},
        risk_level="read",
        status=AgentActionStatus.COMPLETED,
    )

    assert await batches.continuation_state(str(batch.id)) == "evaluating"


@pytest.mark.asyncio
async def test_interaction_call_is_exclusive_and_cancels_batch_siblings(
    db_session,
    monkeypatch,
):
    calls = 0

    async def fake_completion(*args, **kwargs):
        nonlocal calls
        del args
        calls += 1
        if calls == 1:
            return _response(
                tool_calls=[
                    ("read-before", "projects__list", {}),
                    (
                        "question",
                        "ask_user",
                        {
                            "questions": [
                                {
                                    "question": "Continue?",
                                    "header": "Choice",
                                    "options": [
                                        {"label": "Yes", "description": "Continue"},
                                        {"label": "No", "description": "Stop"},
                                    ],
                                }
                            ]
                        },
                    ),
                    ("read-after", "projects__list", {}),
                ]
            )
        tool_results = [item for item in kwargs["messages"] if item["role"] == "tool"]
        assert [item["tool_call_id"] for item in tool_results] == [
            "read-before",
            "question",
            "read-after",
        ]
        return _response(text="interaction complete")

    _patch_model_gateway(monkeypatch, fake_completion)
    monkeypatch.setattr(
        "app.services.agent_core.service.enqueue_turn_resume", lambda *_: None
    )
    await _seed_runtime(db_session)
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
        input_text="Ask before any sibling work.",
    )

    waiting = await service.runtime.run_turn(str(turn.id))

    assert waiting.status == "waiting_approval"
    actions = await AgentActionRepository(db_session).list_for_turn(str(turn.id))
    actions.sort(key=lambda action: action.tool_call_ordinal)
    assert [action.status for action in actions] == [
        AgentActionStatus.CANCELLED,
        AgentActionStatus.WAITING_DECISION,
        AgentActionStatus.CANCELLED,
    ]
    assert all(action.tool_batch_id == actions[1].tool_batch_id for action in actions)
    await service.decide_action(
        action_id=str(actions[1].id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        decision="answer",
        answer={"Choice": "Yes"},
    )

    completed = await service.runtime.resume_turn_after_action(str(actions[1].id))

    assert completed.status == "completed"
    assert completed.final_text == "interaction complete"


@pytest.mark.asyncio
async def test_provider_messages_repair_and_audit_incomplete_tool_call_group(
    db_session,
):
    await _seed_runtime(db_session)
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
        input_text="Do not expose unmatched provider messages.",
    )
    transcript = AgentTranscriptStore(db_session)
    await transcript.append_parts(
        session_id=str(session.id),
        turn_id=str(turn.id),
        role="assistant",
        parts=[
            tool_calls_part(
                [
                    {
                        "id": "unmatched-1",
                        "type": "function",
                        "function": {"name": "bash", "arguments": "{}"},
                    },
                    {
                        "id": "unmatched-2",
                        "type": "function",
                        "function": {"name": "bash", "arguments": "{}"},
                    },
                ]
            )
        ],
    )
    await transcript.append_text(
        session_id=str(session.id),
        turn_id=str(turn.id),
        role="tool",
        text="first only",
        metadata={"tool_call_id": "unmatched-1"},
    )

    messages = await AgentContextAssembler(db_session).provider_messages(
        agent_session=session,
        turn=turn,
    )

    assistant = next(message for message in messages if message.get("tool_calls"))
    assert [call["id"] for call in assistant["tool_calls"]] == [
        "unmatched-1",
        "unmatched-2",
    ]
    tool_messages = [message for message in messages if message.get("role") == "tool"]
    assert [message["tool_call_id"] for message in tool_messages] == [
        "unmatched-1",
        "unmatched-2",
    ]
    assert "TranscriptRepair" in tool_messages[1]["content"]
    stored = await AgentMessageRepository(db_session).list_for_session(str(session.id))
    repairs = [
        message
        for message in stored
        if (message.message_metadata or {}).get("transcript_repair") is True
    ]
    assert len(repairs) == 2
    events = await service.event_repo.list_for_turn(turn_id=str(turn.id))
    assert any(event.type == "transcript.tool_group_repaired" for event in events)


@pytest.mark.asyncio
async def test_transcript_repair_rebuilds_group_before_later_messages(db_session):
    await _seed_runtime(db_session)
    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=None, workspace_id=DEFAULT_WORKSPACE_ID, user_id="dev"
    )
    turn = await service.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Repair in place.",
    )
    transcript = AgentTranscriptStore(db_session)
    await transcript.append_parts(
        session_id=str(session.id),
        turn_id=str(turn.id),
        role="assistant",
        parts=[
            tool_calls_part(
                [
                    {
                        "id": "old-1",
                        "type": "function",
                        "function": {"name": "x", "arguments": "{}"},
                    },
                    {
                        "id": "old-2",
                        "type": "function",
                        "function": {"name": "x", "arguments": "{}"},
                    },
                ]
            )
        ],
    )
    await transcript.append_text(
        session_id=str(session.id),
        turn_id=str(turn.id),
        role="tool",
        text="old first",
        metadata={
            "tool_call_id": "old-1",
            "tool_batch_id": "old-batch",
            "action_id": "old-action-1",
        },
    )
    await transcript.append_text(
        session_id=str(session.id), turn_id=str(turn.id), role="user", text="later user"
    )
    await transcript.append_text(
        session_id=str(session.id),
        turn_id=str(turn.id),
        role="assistant",
        text="later assistant",
    )

    messages = await AgentContextAssembler(db_session).provider_messages(
        agent_session=session,
        turn=turn,
    )
    relevant = [message for message in messages if message["role"] != "system"]

    tool_group_index = next(
        i for i, message in enumerate(relevant) if message.get("tool_calls")
    )
    assert [
        message["role"] for message in relevant[tool_group_index : tool_group_index + 5]
    ] == [
        "assistant",
        "tool",
        "tool",
        "user",
        "assistant",
    ]
    assert [
        message["tool_call_id"]
        for message in relevant[tool_group_index + 1 : tool_group_index + 3]
    ] == ["old-1", "old-2"]
    assert relevant[tool_group_index + 3]["content"] == "later user"


@pytest.mark.asyncio
async def test_mixed_reads_stop_at_approval_before_model_continues(
    db_session, monkeypatch
):
    calls = 0

    async def fake_completion(*args, **kwargs):
        nonlocal calls
        del args, kwargs
        calls += 1
        if calls > 1:
            return _response(text="unexpected continuation")
        return _response(
            tool_calls=[
                ("read-1", "projects__list", {}),
                ("approval", "bash", {"command": "python -c 'print(1)'"}),
                ("read-2", "projects__list", {}),
            ]
        )

    _patch_model_gateway(monkeypatch, fake_completion)
    await _seed_runtime(db_session)
    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=None,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        permission_mode="guarded_auto",
    )
    turn = await service.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Read around one approval.",
    )

    waiting = await service.runtime.run_turn(str(turn.id))

    assert waiting.status == "waiting_approval"
    assert calls == 1
    actions = await AgentActionRepository(db_session).list_for_turn(str(turn.id))
    actions.sort(key=lambda action: action.tool_call_ordinal)
    assert [action.status for action in actions] == [
        AgentActionStatus.COMPLETED,
        AgentActionStatus.WAITING_DECISION,
        AgentActionStatus.REQUESTED,
    ]
    batch_actions = await AgentActionRepository(db_session).list_for_batch(
        str(actions[0].tool_batch_id)
    )
    assert [action.tool_call_id for action in batch_actions] == [
        "read-1",
        "approval",
        "read-2",
    ]


@pytest.mark.asyncio
async def test_compaction_does_not_split_assistant_tool_result_group(db_session):
    await _seed_runtime(db_session)
    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=None,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )
    session = await service.session_repo.update_all(
        session,
        compression_state={
            "enabled": True,
            "threshold_chars": 1,
            "preserve_recent_messages": 2,
        },
    )
    turn = await service.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Keep tool groups atomic.",
    )
    transcript = AgentTranscriptStore(db_session)
    await transcript.append_text(
        session_id=str(session.id),
        turn_id=str(turn.id),
        role="assistant",
        text="old" * 100,
    )
    batch_message = await transcript.append_parts(
        session_id=str(session.id),
        turn_id=str(turn.id),
        role="assistant",
        parts=[
            tool_calls_part(
                [
                    {
                        "id": "compact-1",
                        "type": "function",
                        "function": {"name": "x", "arguments": "{}"},
                    },
                    {
                        "id": "compact-2",
                        "type": "function",
                        "function": {"name": "x", "arguments": "{}"},
                    },
                ]
            )
        ],
    )
    first_result = await transcript.append_text(
        session_id=str(session.id),
        turn_id=str(turn.id),
        role="tool",
        text="one",
        metadata={"tool_call_id": "compact-1"},
    )
    second_result = await transcript.append_text(
        session_id=str(session.id),
        turn_id=str(turn.id),
        role="tool",
        text="two",
        metadata={"tool_call_id": "compact-2"},
    )

    messages = await AgentContextAssembler(db_session).provider_messages(
        agent_session=session,
        turn=turn,
    )
    stored = await AgentMessageRepository(db_session).list_for_session(str(session.id))
    by_id = {str(message.id): message for message in stored}

    assert by_id[str(batch_message.id)].status == "committed"
    assert by_id[str(first_result.id)].status == "committed"
    assert by_id[str(second_result.id)].status == "committed"
    assert [
        message.get("tool_call_id") for message in messages if message["role"] == "tool"
    ] == [
        "compact-1",
        "compact-2",
    ]


@pytest.mark.asyncio
async def test_continuation_claim_has_one_winner_across_database_sessions(db_session):
    await _seed_runtime(db_session)
    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=None, workspace_id=DEFAULT_WORKSPACE_ID, user_id="dev"
    )
    turn = await service.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Claim once.",
    )
    batch = await AgentToolCallBatchRepository(db_session).create(
        session_id=str(session.id),
        turn_id=str(turn.id),
        status=AgentToolCallBatchStatus.READY,
        tool_call_count=1,
    )
    await AgentActionRepository(db_session).create(
        session_id=str(session.id),
        turn_id=str(turn.id),
        tool_batch_id=str(batch.id),
        tool_call_ordinal=0,
        tool_call_id="claim",
        kind="tool",
        name="projects.list",
        input={},
        risk_level="read",
        status=AgentActionStatus.COMPLETED,
    )
    maker = async_sessionmaker(
        bind=db_session.bind, expire_on_commit=False, class_=AsyncSession
    )
    async with maker() as first, maker() as second:
        results = await asyncio.gather(
            ToolCallBatchCoordinator(first).claim_continuation(str(batch.id)),
            ToolCallBatchCoordinator(second).claim_continuation(str(batch.id)),
        )

    assert sorted(results) == [False, True]


@pytest.mark.asyncio
async def test_concurrent_batch_preparation_reserves_distinct_turn_ordinals(
    db_session, monkeypatch
):
    await _seed_runtime(db_session)
    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=None, workspace_id=DEFAULT_WORKSPACE_ID, user_id="dev"
    )
    turn = await service.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Prepare concurrently.",
    )
    maker = async_sessionmaker(
        bind=db_session.bind, expire_on_commit=False, class_=AsyncSession
    )
    both_read_same_counter = asyncio.Event()
    readers = 0

    async def synchronize_legacy_read(self, turn_id):
        nonlocal readers
        current = await self.session.scalar(
            select(func.max(self.model.batch_ordinal)).where(
                self.model.turn_id == turn_id
            )
        )
        readers += 1
        if readers == 2:
            both_read_same_counter.set()
        await both_read_same_counter.wait()
        return int(current or 0) + 1

    monkeypatch.setattr(
        AgentToolCallBatchRepository,
        "next_ordinal",
        synchronize_legacy_read,
        raising=False,
    )

    async def prepare(worker_session):
        batch = await ToolCallBatchCoordinator(worker_session).create(
            session_id=str(session.id),
            turn_id=str(turn.id),
            tool_call_count=1,
            commit=False,
        )
        await worker_session.commit()
        return batch.batch_ordinal

    async with maker() as first, maker() as second:
        ordinals = await asyncio.gather(prepare(first), prepare(second))

    assert sorted(ordinals) == [1, 2]


@pytest.mark.asyncio
async def test_duplicate_settle_never_downgrades_claimed_or_terminal_batch(db_session):
    await _seed_runtime(db_session)
    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=None, workspace_id=DEFAULT_WORKSPACE_ID, user_id="dev"
    )
    turn = await service.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Settle once.",
    )
    batches = ToolCallBatchCoordinator(db_session)
    batch = await batches.create(
        session_id=str(session.id), turn_id=str(turn.id), tool_call_count=1
    )
    await AgentActionRepository(db_session).create(
        session_id=str(session.id),
        turn_id=str(turn.id),
        tool_batch_id=str(batch.id),
        tool_call_ordinal=0,
        tool_call_id="settle",
        kind="tool",
        name="x",
        input={},
        risk_level="read",
        status=AgentActionStatus.COMPLETED,
    )
    assert await batches.settle(str(batch.id)) == "ready"
    assert await batches.claim_continuation(str(batch.id)) is True
    assert await batches.settle(str(batch.id)) == "ready"
    assert (
        await AgentToolCallBatchRepository(db_session).get_fresh(str(batch.id))
    ).status == AgentToolCallBatchStatus.CONTINUING
    await batches.mark_terminal(str(batch.id))
    assert await batches.settle(str(batch.id)) == "ready"
    assert (
        await AgentToolCallBatchRepository(db_session).get_fresh(str(batch.id))
    ).status == AgentToolCallBatchStatus.TERMINAL


@pytest.mark.asyncio
async def test_empty_ordinary_turn_has_no_continuation_state_error(
    db_session, monkeypatch
):
    async def empty_completion(*args, **kwargs):
        del args, kwargs
        return _response(text="")

    _patch_model_gateway(monkeypatch, empty_completion)
    await _seed_runtime(db_session)
    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=None, workspace_id=DEFAULT_WORKSPACE_ID, user_id="dev"
    )
    turn = await service.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Return empty.",
    )
    failed = await service.runtime.run_turn(str(turn.id))
    assert failed.error_code == "empty_model_response"


@pytest.mark.asyncio
async def test_adjacent_reads_overlap_before_approval_barrier(db_session, monkeypatch):
    started = 0
    both_started = asyncio.Event()

    async def overlapping_read(self, input, context):
        nonlocal started
        del self, input, context
        started += 1
        if started == 2:
            both_started.set()
        await asyncio.wait_for(both_started.wait(), timeout=1)
        return {"projects": [], "total_count": 0}

    monkeypatch.setattr(
        "app.services.agent_core.tools.platform.projects.ListProjectsTool.run",
        overlapping_read,
    )
    monkeypatch.setattr(
        "app.services.agent_core.service.enqueue_turn_resume", lambda *_: None
    )
    calls = 0

    async def fake_completion(*args, **kwargs):
        nonlocal calls
        del args, kwargs
        calls += 1
        if calls > 1:
            return _response(text="unexpected continuation")
        return _response(
            tool_calls=[
                ("overlap-1", "projects__list", {}),
                ("overlap-2", "projects__list", {}),
                (
                    "approval-between",
                    "bash",
                    {"command": "python -c 'print(1)'"},
                ),
            ]
        )

    _patch_model_gateway(monkeypatch, fake_completion)
    await _seed_runtime(db_session)
    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=None,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        permission_mode="guarded_auto",
    )
    turn = await service.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Overlap independent reads.",
    )

    waiting = await service.runtime.run_turn(str(turn.id))

    assert waiting.status == "waiting_approval"
    assert started == 2
    actions = await AgentActionRepository(db_session).list_for_turn(str(turn.id))
    actions.sort(key=lambda action: action.tool_call_ordinal)
    assert [actions[0].status, actions[1].status] == [
        AgentActionStatus.COMPLETED,
        AgentActionStatus.COMPLETED,
    ]
    assert actions[2].status == AgentActionStatus.WAITING_DECISION


@pytest.mark.asyncio
async def test_approval_barrier_defers_later_safe_calls_until_resume(
    db_session,
    monkeypatch,
):
    read_calls = 0

    async def counted_read(self, input, context):
        nonlocal read_calls
        del self, input, context
        read_calls += 1
        return {"projects": [], "total_count": 0}

    monkeypatch.setattr(
        "app.services.agent_core.tools.platform.projects.ListProjectsTool.run",
        counted_read,
    )
    monkeypatch.setattr(
        "app.services.agent_core.service.enqueue_turn_resume", lambda *_: None
    )
    calls = 0

    async def fake_completion(*args, **kwargs):
        nonlocal calls
        del args, kwargs
        calls += 1
        if calls == 1:
            return _response(
                tool_calls=[
                    ("read-before-approval", "projects__list", {}),
                    (
                        "approval-barrier",
                        "bash",
                        {"command": "python -c 'print(1)'"},
                    ),
                    ("read-after-approval", "projects__list", {}),
                ]
            )
        return _response(text="approval batch complete")

    _patch_model_gateway(monkeypatch, fake_completion)
    await _seed_runtime(db_session)
    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=None,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        permission_mode="guarded_auto",
    )
    turn = await service.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Stop at the approval barrier.",
    )

    waiting = await service.runtime.run_turn(str(turn.id))

    assert waiting.status == AgentTurnStatus.WAITING_APPROVAL
    assert read_calls == 1
    actions = await AgentActionRepository(db_session).list_for_turn(str(turn.id))
    actions.sort(key=lambda action: action.tool_call_ordinal)
    assert [action.status for action in actions] == [
        AgentActionStatus.COMPLETED,
        AgentActionStatus.WAITING_DECISION,
        AgentActionStatus.REQUESTED,
    ]

    approved = await service.decide_action(
        action_id=str(actions[1].id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        decision="approve",
    )
    completed = await service.runtime.resume_turn_after_action(str(approved.id))

    assert completed.status == AgentTurnStatus.COMPLETED
    assert completed.final_text == "approval batch complete"
    assert read_calls == 2


@pytest.mark.asyncio
async def test_dynamic_approval_recheck_stops_later_safe_calls(
    db_session,
    monkeypatch,
):
    read_calls = 0

    async def counted_read(self, input, context):
        nonlocal read_calls
        del self, input, context
        read_calls += 1
        return {"projects": [], "total_count": 0}

    monkeypatch.setattr(
        "app.services.agent_core.tools.platform.projects.ListProjectsTool.run",
        counted_read,
    )
    await _seed_runtime(db_session)
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
        input_text="Recheck policy at the serial barrier.",
    )
    controller = AgentLoopController(db_session)
    original_resume = controller.executor.resume_action
    policy_changed = False

    async def tighten_policy_before_resume(**kwargs):
        nonlocal policy_changed
        if not policy_changed:
            policy_changed = True
            await service.update_session(
                session_id=str(session.id),
                workspace_id=DEFAULT_WORKSPACE_ID,
                user_id="dev",
                updates={"permission_mode": "ask_each_action"},
            )
        return await original_resume(**kwargs)

    monkeypatch.setattr(
        controller.executor,
        "resume_action",
        tighten_policy_before_resume,
    )

    waiting, _signatures, _claimed_batch_id = await controller._execute_tool_calls(
        agent_session=session,
        turn=turn,
        tool_calls=[
            {"id": "read-before-recheck", "name": "projects__list", "arguments": {}},
            {
                "id": "dynamic-approval",
                "name": "bash",
                "arguments": {"command": "touch policy-recheck"},
            },
            {"id": "read-after-recheck", "name": "projects__list", "arguments": {}},
        ],
        provider="openai_compatible",
        model="batch-model",
    )

    assert waiting is True
    assert read_calls == 1
    actions = await AgentActionRepository(db_session).list_for_turn(str(turn.id))
    actions.sort(key=lambda action: action.tool_call_ordinal)
    assert [action.status for action in actions] == [
        AgentActionStatus.COMPLETED,
        AgentActionStatus.WAITING_DECISION,
        AgentActionStatus.REQUESTED,
    ]


@pytest.mark.asyncio
async def test_parallel_result_approval_stops_later_serial_segment(
    db_session,
    monkeypatch,
):
    await _seed_runtime(db_session)
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
        input_text="Honor approvals returned by parallel execution.",
    )
    controller = AgentLoopController(db_session)
    serial_calls = 0

    async def parallel_result(**kwargs):
        return ToolExecutionResult(
            action_id=kwargs["action_id"],
            status=AgentActionStatus.WAITING_DECISION,
            requires_resume=True,
        )

    async def observe_serial(**kwargs):
        nonlocal serial_calls
        serial_calls += 1
        return ToolExecutionResult(
            action_id=kwargs["action_id"],
            status=AgentActionStatus.COMPLETED,
            result={"todos": []},
        )

    monkeypatch.setattr(controller, "_execute_tool_call_isolated", parallel_result)
    monkeypatch.setattr(controller.executor, "resume_action", observe_serial)

    waiting, _signatures, _claimed_batch_id = await controller._execute_tool_calls(
        agent_session=session,
        turn=turn,
        tool_calls=[
            {"id": "parallel-approval", "name": "projects__list", "arguments": {}},
            {
                "id": "later-serial",
                "name": "todo_write",
                "arguments": {
                    "todos": [{"content": "must wait", "status": "in_progress"}]
                },
            },
        ],
        provider="openai_compatible",
        model="batch-model",
    )

    assert waiting is True
    assert serial_calls == 0


@pytest.mark.asyncio
async def test_duplicate_provider_call_id_is_scoped_to_each_batch(
    db_session, monkeypatch
):
    calls = 0

    async def fake_completion(*args, **kwargs):
        nonlocal calls
        del args
        calls += 1
        if calls <= 2:
            return _response(tool_calls=[("duplicate-id", "projects__list", {})])
        tool_results = [item for item in kwargs["messages"] if item["role"] == "tool"]
        assert [item["tool_call_id"] for item in tool_results] == [
            "duplicate-id",
            "duplicate-id",
        ]
        return _response(text="two batches complete")

    _patch_model_gateway(monkeypatch, fake_completion)
    await _seed_runtime(db_session)
    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=None, workspace_id=DEFAULT_WORKSPACE_ID, user_id="dev"
    )
    turn = await service.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Reuse provider ids safely.",
    )

    completed = await service.runtime.run_turn(str(turn.id))

    assert completed.status == "completed"
    assert completed.final_text == "two batches complete"


@pytest.mark.asyncio
async def test_duplicate_provider_call_ids_are_normalized_within_one_batch(
    db_session, monkeypatch
):
    async def fake_completion(*args, **kwargs):
        del args, kwargs
        return _response(
            tool_calls=[
                ("same-provider-id", "bash", {"command": "printf one"}),
                ("same-provider-id", "bash", {"command": "printf two"}),
                ("", "bash", {"command": "printf three"}),
            ]
        )

    _patch_model_gateway(monkeypatch, fake_completion)
    monkeypatch.setattr(
        "app.services.agent_core.service.cancel_turn_run", lambda *_: False
    )
    await _seed_runtime(db_session)
    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=None,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        permission_mode="ask_each_action",
    )
    turn = await service.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Keep duplicate provider calls pairable.",
    )

    waiting = await service.runtime.run_turn(str(turn.id))

    assert waiting.status == "waiting_approval"
    actions = await AgentActionRepository(db_session).list_for_turn(str(turn.id))
    actions.sort(key=lambda action: action.tool_call_ordinal)
    action_call_ids = [action.tool_call_id for action in actions]
    assert len(action_call_ids) == len(set(action_call_ids)) == 3
    messages = await AgentMessageRepository(db_session).list_for_session(
        str(session.id)
    )
    assistant = next(message for message in messages if message.role == "assistant")
    assistant_calls = next(
        part["tool_calls"]
        for part in assistant.content_parts
        if part.get("type") == "tool_calls"
    )
    assert [call["id"] for call in assistant_calls] == action_call_ids
    assert assistant.message_metadata["provider_tool_call_ids"] == [
        {
            "ordinal": 0,
            "provider_id": "same-provider-id",
            "internal_id": action_call_ids[0],
        },
        {
            "ordinal": 1,
            "provider_id": "same-provider-id",
            "internal_id": action_call_ids[1],
        },
        {
            "ordinal": 2,
            "provider_id": None,
            "internal_id": action_call_ids[2],
        },
    ]
    await service.cancel_turn(
        turn_id=str(turn.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )
    messages = await AgentMessageRepository(db_session).list_for_session(
        str(session.id)
    )
    tool_messages = [message for message in messages if message.role == "tool"]
    assert [message.message_metadata["tool_call_id"] for message in tool_messages] == (
        action_call_ids
    )


@pytest.mark.asyncio
async def test_prepare_failure_repairs_every_call_with_terminal_result(
    db_session, monkeypatch
):
    calls = 0

    async def fake_completion(*args, **kwargs):
        nonlocal calls
        del args
        calls += 1
        if calls == 1:
            return _response(
                tool_calls=[
                    ("prepare-1", "projects__list", {}),
                    ("prepare-2", "projects__list", {}),
                    ("prepare-3", "projects__list", {}),
                ]
            )
        tool_results = [item for item in kwargs["messages"] if item["role"] == "tool"]
        assert [item["tool_call_id"] for item in tool_results] == [
            "prepare-1",
            "prepare-2",
            "prepare-3",
        ]
        assert all("BatchPreparationError" in item["content"] for item in tool_results)
        return _response(text="repaired")

    _patch_model_gateway(monkeypatch, fake_completion)
    from app.services.agent_core.tools.executor import AgentToolExecutor

    original_execute = AgentToolExecutor.execute
    prepares = 0

    async def fail_second_prepare(self, **kwargs):
        nonlocal prepares
        prepares += 1
        if prepares == 2:
            raise RuntimeError("synthetic prepare failure")
        return await original_execute(self, **kwargs)

    monkeypatch.setattr(AgentToolExecutor, "execute", fail_second_prepare)
    await _seed_runtime(db_session)
    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=None, workspace_id=DEFAULT_WORKSPACE_ID, user_id="dev"
    )
    turn = await service.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Repair preparation.",
    )

    completed = await service.runtime.run_turn(str(turn.id))

    assert completed.status == "completed"
    actions = await AgentActionRepository(db_session).list_for_turn(str(turn.id))
    actions.sort(key=lambda action: action.tool_call_ordinal)
    assert len(actions) == 3
    assert all(action.status == AgentActionStatus.FAILED for action in actions)
    batch = await AgentToolCallBatchRepository(db_session).get(
        str(actions[0].tool_batch_id)
    )
    assert batch is not None
    assert batch.status == AgentToolCallBatchStatus.FAILED


@pytest.mark.asyncio
async def test_batch_flush_failure_rolls_back_and_repairs_complete_terminal_group(
    db_session, monkeypatch
):
    model_calls = 0

    async def fake_completion(*args, **kwargs):
        nonlocal model_calls
        del args
        model_calls += 1
        if model_calls == 1:
            return _response(
                tool_calls=[
                    ("flush-1", "bash", {"command": "printf one"}),
                    ("flush-2", "bash", {"command": "printf two"}),
                ]
            )
        tool_results = [item for item in kwargs["messages"] if item["role"] == "tool"]
        assert [item["tool_call_id"] for item in tool_results] == [
            "flush-1",
            "flush-2",
        ]
        assert all("BatchPreparationError" in item["content"] for item in tool_results)
        return _response(text="flush repaired")

    original_create = ToolCallBatchCoordinator.create
    create_calls = 0

    async def fail_first_batch_flush(self, **kwargs):
        nonlocal create_calls
        create_calls += 1
        if create_calls == 1:
            raise IntegrityError(
                "INSERT agent_tool_call_batches", {}, Exception("race")
            )
        return await original_create(self, **kwargs)

    _patch_model_gateway(monkeypatch, fake_completion)
    monkeypatch.setattr(ToolCallBatchCoordinator, "create", fail_first_batch_flush)
    await _seed_runtime(db_session)
    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=None, workspace_id=DEFAULT_WORKSPACE_ID, user_id="dev"
    )
    turn = await service.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Repair a failed batch flush.",
    )

    completed = await service.runtime.run_turn(str(turn.id))

    assert completed.status == AgentTurnStatus.COMPLETED
    assert completed.final_text == "flush repaired"
    actions = await AgentActionRepository(db_session).list_for_turn(str(turn.id))
    assert len(actions) == 2
    assert all(action.status == AgentActionStatus.FAILED for action in actions)
    batches, _ = await AgentToolCallBatchRepository(db_session).list(limit=10)
    assert len(batches) == 1
    assert batches[0].status == AgentToolCallBatchStatus.FAILED


@pytest.mark.asyncio
async def test_stale_turn_batch_sequence_self_heals_before_reserving_next_ordinal(
    db_session, monkeypatch
):
    model_calls = 0

    async def fake_completion(*args, **kwargs):
        nonlocal model_calls
        del args
        model_calls += 1
        if model_calls == 1:
            return _response(
                tool_calls=[
                    ("stale-ordinal", "projects__list", {}),
                ]
            )
        tool_results = [item for item in kwargs["messages"] if item["role"] == "tool"]
        assert [item["tool_call_id"] for item in tool_results] == ["stale-ordinal"]
        payload = json.loads(tool_results[0]["content"])
        assert payload["tool"] == "projects.list"
        assert payload["status"] == AgentActionStatus.COMPLETED
        return _response(text="stale ordinal repaired")

    _patch_model_gateway(monkeypatch, fake_completion)
    await _seed_runtime(db_session)
    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=None, workspace_id=DEFAULT_WORKSPACE_ID, user_id="dev"
    )
    turn = await service.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Repair stale batch sequence.",
    )
    await AgentToolCallBatchRepository(db_session).create(
        session_id=str(session.id),
        turn_id=str(turn.id),
        status=AgentToolCallBatchStatus.TERMINAL,
        tool_call_count=1,
        batch_ordinal=1,
    )

    completed = await service.runtime.run_turn(str(turn.id))

    assert completed.status == AgentTurnStatus.COMPLETED
    assert completed.final_text == "stale ordinal repaired"
    batches, _ = await AgentToolCallBatchRepository(db_session).list(limit=10)
    assert sorted(batch.batch_ordinal for batch in batches) == [1, 2]
    assert all(batch.status == AgentToolCallBatchStatus.TERMINAL for batch in batches)


@pytest.mark.asyncio
async def test_prepare_cancellation_terminalizes_entire_batch(db_session, monkeypatch):
    async def fake_completion(*args, **kwargs):
        del args, kwargs
        return _response(
            tool_calls=[
                ("cancel-1", "projects__list", {}),
                ("cancel-2", "projects__list", {}),
            ]
        )

    _patch_model_gateway(monkeypatch, fake_completion)
    from app.services.agent_core.tools.executor import AgentToolExecutor

    original_execute = AgentToolExecutor.execute
    count = 0

    async def cancel_second(self, **kwargs):
        nonlocal count
        count += 1
        if count == 2:
            raise asyncio.CancelledError
        return await original_execute(self, **kwargs)

    monkeypatch.setattr(AgentToolExecutor, "execute", cancel_second)
    await _seed_runtime(db_session)
    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=None, workspace_id=DEFAULT_WORKSPACE_ID, user_id="dev"
    )
    turn = await service.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Cancel prepare.",
    )
    cancelled = await service.runtime.run_turn(str(turn.id))
    assert cancelled.status == "cancelled"
    actions = await AgentActionRepository(db_session).list_for_turn(str(turn.id))
    assert len(actions) == 2
    assert all(action.status == AgentActionStatus.CANCELLED for action in actions)
    batch = await AgentToolCallBatchRepository(db_session).get(
        str(actions[0].tool_batch_id)
    )
    assert batch.status == AgentToolCallBatchStatus.CANCELLED


@pytest.mark.asyncio
async def test_execution_cancellation_cancels_committed_batch(db_session, monkeypatch):
    async def fake_completion(*args, **kwargs):
        del args, kwargs
        return _response(tool_calls=[("cancel-run", "projects__list", {})])

    async def cancel_run(self, input, context):
        del self, input, context
        raise asyncio.CancelledError

    _patch_model_gateway(monkeypatch, fake_completion)
    monkeypatch.setattr(
        "app.services.agent_core.tools.platform.projects.ListProjectsTool.run",
        cancel_run,
    )
    await _seed_runtime(db_session)
    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=None, workspace_id=DEFAULT_WORKSPACE_ID, user_id="dev"
    )
    turn = await service.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Cancel execution.",
    )
    cancelled = await service.runtime.run_turn(str(turn.id))
    assert cancelled.status == "cancelled"
    actions = await AgentActionRepository(db_session).list_for_turn(str(turn.id))
    batch = await AgentToolCallBatchRepository(db_session).get_fresh(
        str(actions[0].tool_batch_id)
    )
    assert actions[0].status == AgentActionStatus.CANCELLED
    assert batch.status == AgentToolCallBatchStatus.CANCELLED


@pytest.mark.asyncio
async def test_heartbeat_lease_loss_fences_running_tool_until_recovery(
    db_session, monkeypatch
):
    monkeypatch.setattr(settings, "agent_turn_lease_seconds", 1)

    async def fake_completion(*args, **kwargs):
        del args, kwargs
        return _response(
            tool_calls=[("lease-loss", "bash", {"command": "printf fenced"})]
        )

    entered = asyncio.Event()

    async def blocked_run(self, input, context):
        del self, input, context
        entered.set()
        await asyncio.Event().wait()

    _patch_model_gateway(monkeypatch, fake_completion)
    monkeypatch.setattr(ExecuteShellTool, "run", blocked_run)
    await _seed_runtime(db_session)
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
        input_text="Fence the running tool when ownership changes.",
    )
    maker = async_sessionmaker(
        bind=db_session.bind, expire_on_commit=False, class_=AsyncSession
    )
    async with maker() as execution_session, maker() as takeover_session:
        execution = asyncio.create_task(
            AgentCoreService(execution_session).runtime.run_turn(str(turn.id))
        )
        await asyncio.wait_for(entered.wait(), timeout=2)
        replacement = await AgentTurnRepository(takeover_session).get_fresh(
            str(turn.id)
        )
        await AgentTurnRepository(takeover_session).update_all(
            replacement,
            owner_token="replacement-owner",
            lease_until=datetime.now(timezone.utc) + timedelta(minutes=1),
        )

        fenced_turn = await asyncio.wait_for(execution, timeout=2)
        actions = await AgentActionRepository(takeover_session).list_for_turn(
            str(turn.id)
        )
        assert fenced_turn.owner_token == "replacement-owner"
        assert len(actions) == 1
        assert actions[0].status == AgentActionStatus.RUNNING

        replacement = await AgentTurnRepository(takeover_session).get_fresh(
            str(turn.id)
        )
        await AgentTurnRepository(takeover_session).update_all(
            replacement,
            lease_until=datetime.now(timezone.utc) - timedelta(seconds=1),
        )
        summary = await AgentCoreService(takeover_session).recover_orphaned_turns()
        reconciled_action = await AgentActionRepository(takeover_session).get_fresh(
            str(actions[0].id)
        )
        reconciled_turn = await AgentTurnRepository(takeover_session).get_fresh(
            str(turn.id)
        )

    assert summary["failed"] == 1
    assert reconciled_action.status == AgentActionStatus.CANCELLED
    assert reconciled_turn.status == AgentTurnStatus.FAILED
    assert reconciled_turn.error_code == "recovery_inflight_action"


@pytest.mark.asyncio
async def test_failed_b_preparation_terminalizes_prior_a_in_same_transition(
    db_session, monkeypatch
):
    calls = 0

    async def fake_completion(*args, **kwargs):
        nonlocal calls
        del args, kwargs
        calls += 1
        if calls == 1:
            return _response(tool_calls=[("a-read", "projects__list", {})])
        return _response(tool_calls=[("b-denied", "ask_user", {"questions": []})])

    _patch_model_gateway(monkeypatch, fake_completion)
    await _seed_runtime(db_session)
    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=None,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        role_profile="worker",
    )
    turn = await service.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="A then denied B.",
    )
    failed = await service.runtime.run_turn(str(turn.id))
    assert failed.error_code == "tool_not_exposed"
    batches, _ = await AgentToolCallBatchRepository(db_session).list(limit=10)
    batches.sort(key=lambda batch: batch.batch_ordinal)
    assert [batch.batch_ordinal for batch in batches] == [1, 2]
    assert batches[0].status == AgentToolCallBatchStatus.TERMINAL
    assert batches[1].status == AgentToolCallBatchStatus.FAILED


@pytest.mark.asyncio
async def test_assistant_batch_and_all_actions_become_visible_atomically(
    db_session, monkeypatch
):
    model_calls = 0

    async def fake_completion(*args, **kwargs):
        nonlocal model_calls
        del args, kwargs
        model_calls += 1
        if model_calls > 1:
            return _response(text="atomic complete")
        return _response(
            tool_calls=[
                ("atomic-1", "projects__list", {}),
                ("atomic-2", "projects__list", {}),
            ]
        )

    _patch_model_gateway(monkeypatch, fake_completion)
    from app.services.agent_core.tools.executor import AgentToolExecutor

    original_execute = AgentToolExecutor.execute
    count = 0
    maker = async_sessionmaker(
        bind=db_session.bind, expire_on_commit=False, class_=AsyncSession
    )

    async def inspect_second_prepare(self, **kwargs):
        nonlocal count
        count += 1
        if count == 2:
            async with maker() as observer:
                observed_actions, _ = await AgentActionRepository(observer).list(
                    limit=10
                )
                observed_batches, _ = await AgentToolCallBatchRepository(observer).list(
                    limit=10
                )
                observed_messages, _ = await AgentMessageRepository(observer).list(
                    limit=20
                )
                assert observed_actions == []
                assert observed_batches == []
                assert not any(
                    message.role == "assistant" for message in observed_messages
                )
        return await original_execute(self, **kwargs)

    monkeypatch.setattr(AgentToolExecutor, "execute", inspect_second_prepare)
    await _seed_runtime(db_session)
    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=None, workspace_id=DEFAULT_WORKSPACE_ID, user_id="dev"
    )
    turn = await service.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Commit atomically.",
    )
    await service.runtime.run_turn(str(turn.id))
    actions = await AgentActionRepository(db_session).list_for_turn(str(turn.id))
    assert len(actions) == 2
    assert len({action.tool_batch_id for action in actions}) == 1


@pytest.mark.asyncio
async def test_atomic_batch_preparation_locks_permission_policy_before_actions(
    db_session, monkeypatch
):
    async def fake_completion(*args, **kwargs):
        del args, kwargs
        return _response(tool_calls=[("policy-lock", "projects__list", {})])

    from app.repositories.agent_core_repo import AgentSessionRepository
    from app.repositories.agent_core_repo import AgentTurnRepository
    from app.services.agent_core.tools.executor import AgentToolExecutor

    policy_locked = False

    async def observe_policy_lock(repository, session_id):
        nonlocal policy_locked
        policy_locked = True
        return await repository.get_fresh(session_id)

    original_owner_lock = AgentTurnRepository.lock_execution_owner

    async def require_policy_before_owner_lock(repository, turn_id, *, owner_token):
        assert policy_locked is True
        return await original_owner_lock(
            repository,
            turn_id,
            owner_token=owner_token,
        )

    original_execute = AgentToolExecutor.execute

    async def require_policy_lock(self, **kwargs):
        assert policy_locked is True
        return await original_execute(self, **kwargs)

    _patch_model_gateway(monkeypatch, fake_completion)
    monkeypatch.setattr(
        AgentSessionRepository,
        "lock_policy",
        observe_policy_lock,
        raising=False,
    )
    monkeypatch.setattr(
        AgentTurnRepository,
        "lock_execution_owner",
        require_policy_before_owner_lock,
    )
    monkeypatch.setattr(AgentToolExecutor, "execute", require_policy_lock)
    await _seed_runtime(db_session)
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
        input_text="Lock policy before preparing actions.",
    )

    await service.runtime.run_turn(str(turn.id))

    assert policy_locked is True


@pytest.mark.asyncio
async def test_stale_turn_owner_cannot_commit_tool_batch_preparation(db_session):
    from app.services.agent_core.core.loop import AgentLoopController

    await _seed_runtime(db_session)
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
        input_text="Fence stale preparation.",
    )
    turn = await AgentTurnRepository(db_session).update_all(
        turn,
        status=AgentTurnStatus.RUNNING,
        owner_token="stale-owner",
        lease_until=datetime.now(timezone.utc) + timedelta(minutes=1),
    )
    maker = async_sessionmaker(
        bind=db_session.bind, expire_on_commit=False, class_=AsyncSession
    )

    async with maker() as worker, maker() as takeover:
        stale_turn = await AgentTurnRepository(worker).get_fresh(str(turn.id))
        stale_session = await AgentSessionRepository(worker).get_fresh(str(session.id))
        replacement = await AgentTurnRepository(takeover).get_fresh(str(turn.id))
        await AgentTurnRepository(takeover).update_all(
            replacement,
            owner_token="replacement-owner",
            lease_until=datetime.now(timezone.utc) + timedelta(minutes=1),
        )
        baseline_actions = await AgentActionRepository(takeover).list_for_turn(
            str(turn.id)
        )
        baseline_batches, _ = await AgentToolCallBatchRepository(takeover).list(
            limit=20
        )
        baseline_messages = await AgentMessageRepository(takeover).list_for_session(
            str(session.id)
        )
        baseline_events = await AgentEventRepository(takeover).list_for_turn(
            turn_id=str(turn.id)
        )

        controller = AgentLoopController(
            worker,
            ownership=_ownership(
                worker,
                turn_id=str(turn.id),
                token="stale-owner",
            ),
        )
        with pytest.raises(TurnOwnershipLostError):
            await controller._execute_tool_calls(
                agent_session=stale_session,
                turn=stale_turn,
                tool_calls=[
                    {
                        "id": "stale-preparation",
                        "name": "projects__list",
                        "arguments": {},
                    }
                ],
                provider="openai_compatible",
                model="batch-model",
                text=None,
                prior_continuation_batch_id=None,
            )

    async with maker() as observer:
        actions = await AgentActionRepository(observer).list_for_turn(str(turn.id))
        batches, _ = await AgentToolCallBatchRepository(observer).list(limit=20)
        messages = await AgentMessageRepository(observer).list_for_session(
            str(session.id)
        )
        events = await AgentEventRepository(observer).list_for_turn(
            turn_id=str(turn.id)
        )

    assert [str(item.id) for item in actions] == [
        str(item.id) for item in baseline_actions
    ]
    assert [str(item.id) for item in batches] == [
        str(item.id) for item in baseline_batches
    ]
    assert [str(item.id) for item in messages] == [
        str(item.id) for item in baseline_messages
    ]
    assert [str(item.id) for item in events] == [
        str(item.id) for item in baseline_events
    ]


@pytest.mark.asyncio
async def test_current_turn_owner_can_commit_tool_batch_preparation(db_session):
    from app.services.agent_core.core.loop import AgentLoopController

    await _seed_runtime(db_session)
    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=None,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        permission_mode="ask_each_action",
    )
    turn = await service.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Prepare with the current owner.",
    )
    turn = await AgentTurnRepository(db_session).update_all(
        turn,
        status=AgentTurnStatus.RUNNING,
        owner_token="current-owner",
        lease_until=datetime.now(timezone.utc) + timedelta(minutes=1),
    )

    controller = AgentLoopController(
        db_session,
        ownership=_ownership(
            db_session,
            turn_id=str(turn.id),
            token="current-owner",
        ),
    )
    waiting, _signatures, _claimed_batch_id = await controller._execute_tool_calls(
        agent_session=session,
        turn=turn,
        tool_calls=[
            {
                "id": "healthy-preparation",
                "name": "bash",
                "arguments": {"command": "printf healthy"},
            }
        ],
        provider="openai_compatible",
        model="batch-model",
        text=None,
        prior_continuation_batch_id=None,
    )

    actions = await AgentActionRepository(db_session).list_for_turn(str(turn.id))
    batches, _ = await AgentToolCallBatchRepository(db_session).list(limit=20)
    messages = await AgentMessageRepository(db_session).list_for_session(
        str(session.id)
    )

    assert waiting is True
    assert len(actions) == 1
    assert len(batches) == 1
    assert any(message.role == "assistant" for message in messages)


@pytest.mark.asyncio
async def test_batch_stays_continuing_until_next_model_message_is_persisted(
    db_session,
    monkeypatch,
):
    calls = 0
    maker = async_sessionmaker(
        bind=db_session.bind, expire_on_commit=False, class_=AsyncSession
    )

    async def fake_completion(*args, **kwargs):
        nonlocal calls
        del args, kwargs
        calls += 1
        if calls == 1:
            return _response(tool_calls=[("continue-state", "projects__list", {})])
        async with maker() as check_session:
            batches, _ = await AgentToolCallBatchRepository(check_session).list(
                limit=10
            )
            assert batches[0].status == AgentToolCallBatchStatus.CONTINUING
        return _response(text="persisted continuation")

    _patch_model_gateway(monkeypatch, fake_completion)
    await _seed_runtime(db_session)
    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=None, workspace_id=DEFAULT_WORKSPACE_ID, user_id="dev"
    )
    turn = await service.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Keep claim until persistence.",
    )

    completed = await service.runtime.run_turn(str(turn.id))

    assert completed.status == "completed"
    batches, _ = await AgentToolCallBatchRepository(db_session).list(limit=10)
    assert batches[0].status == AgentToolCallBatchStatus.TERMINAL


@pytest.mark.asyncio
async def test_model_failure_releases_and_retries_continuing_batch(
    db_session, monkeypatch
):
    calls = 0

    async def fake_completion(*args, **kwargs):
        nonlocal calls
        del args, kwargs
        calls += 1
        if calls == 1:
            return _response(tool_calls=[("recover-continuing", "projects__list", {})])
        raise RuntimeError("model unavailable after claim")

    _patch_model_gateway(monkeypatch, fake_completion)
    await _seed_runtime(db_session)
    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=None, workspace_id=DEFAULT_WORKSPACE_ID, user_id="dev"
    )
    turn = await service.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Recover a claimed continuation.",
    )
    turn = await AgentTurnRepository(db_session).update_all(
        turn,
        status=AgentTurnStatus.RUNNING,
    )

    from app.services.agent_core.core.loop import AgentLoopController

    controller = AgentLoopController(db_session)
    failed = await controller.run_turn(
        turn_id=str(turn.id),
        target=_target(),
        continuation_failure_mode="ready",
    )

    assert failed.termination_reason == "model_failed"
    batches, _ = await AgentToolCallBatchRepository(db_session).list(limit=10)
    assert batches[0].status == AgentToolCallBatchStatus.READY

    async def recovered_completion(*args, **kwargs):
        del args, kwargs
        return _response(text="recovered continuation")

    _patch_model_gateway(monkeypatch, recovered_completion)
    recovered = await controller.run_turn(
        turn_id=str(turn.id),
        target=_target(),
        continuation_batch_id=str(batches[0].id),
    )

    assert recovered.final_text == "recovered continuation"
    recovered_batch = await AgentToolCallBatchRepository(db_session).get(
        str(batches[0].id)
    )
    assert recovered_batch.status == AgentToolCallBatchStatus.TERMINAL


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("batch_status", "action_status", "expected_outcome", "expected_wakeup"),
    [
        (
            AgentToolCallBatchStatus.WAITING,
            AgentActionStatus.WAITING_DECISION,
            "waiting",
            None,
        ),
        (
            AgentToolCallBatchStatus.WAITING,
            AgentActionStatus.REQUESTED,
            "enqueued",
            "resume",
        ),
        (
            AgentToolCallBatchStatus.CONTINUING,
            AgentActionStatus.COMPLETED,
            "enqueued",
            "resume",
        ),
        (
            AgentToolCallBatchStatus.READY,
            AgentActionStatus.COMPLETED,
            "enqueued",
            "resume",
        ),
    ],
)
async def test_restart_recovery_is_batch_first_with_fresh_session_and_empty_runner(
    db_session,
    monkeypatch,
    batch_status,
    action_status,
    expected_outcome,
    expected_wakeup,
):
    await _seed_runtime(db_session)
    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=None, workspace_id=DEFAULT_WORKSPACE_ID, user_id="dev"
    )
    turn = await service.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Recover from durable batch state.",
    )
    turn = await _mark_turn_as_expired_execution(service, turn)
    batch = await AgentToolCallBatchRepository(db_session).create(
        session_id=str(session.id),
        turn_id=str(turn.id),
        status=batch_status,
        tool_call_count=1,
    )
    action = await AgentActionRepository(db_session).create(
        session_id=str(session.id),
        turn_id=str(turn.id),
        tool_batch_id=str(batch.id),
        tool_call_ordinal=0,
        tool_call_id="restart",
        kind="tool",
        name="projects.list",
        input={},
        risk_level="read",
        status=action_status,
        result={} if action_status == AgentActionStatus.COMPLETED else None,
    )

    from app.services.agent_core import runner as runner_module
    from app.services.agent_core import service as service_module

    runner_module._RUNNING_TURNS.clear()
    runner_module._PENDING_TURN_TASK_FACTORIES.clear()
    wakeups: list[tuple[str, str]] = []
    monkeypatch.setattr(
        service_module,
        "enqueue_turn_resume",
        lambda action_id, *_: wakeups.append(("resume", action_id)),
    )
    monkeypatch.setattr(
        service_module,
        "enqueue_turn_run",
        lambda turn_id, *_: wakeups.append(("run", turn_id)),
    )
    maker = async_sessionmaker(
        bind=db_session.bind, expire_on_commit=False, class_=AsyncSession
    )
    async with maker() as restarted_session:
        summary = await AgentCoreService(restarted_session).recover_orphaned_turns()
        recovered_batch = await AgentToolCallBatchRepository(restarted_session).get(
            str(batch.id)
        )

    assert summary[expected_outcome] == 1
    if expected_wakeup is None:
        assert wakeups == []
    else:
        assert wakeups == [(expected_wakeup, str(action.id))]
    if batch_status == AgentToolCallBatchStatus.CONTINUING:
        assert recovered_batch.status == AgentToolCallBatchStatus.READY


@pytest.mark.asyncio
async def test_restart_repairs_partially_prepared_evaluating_batch(
    db_session, monkeypatch
):
    await _seed_runtime(db_session)
    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=None, workspace_id=DEFAULT_WORKSPACE_ID, user_id="dev"
    )
    turn = await service.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Recover partial preparation.",
    )
    await _mark_turn_as_expired_execution(service, turn)
    transcript = AgentTranscriptStore(db_session)
    await transcript.append_parts(
        session_id=str(session.id),
        turn_id=str(turn.id),
        role="assistant",
        parts=[
            tool_calls_part(
                [
                    {
                        "id": "partial-1",
                        "type": "function",
                        "function": {"name": "projects__list", "arguments": "{}"},
                    },
                    {
                        "id": "partial-2",
                        "type": "function",
                        "function": {"name": "projects__list", "arguments": "{}"},
                    },
                ]
            )
        ],
    )
    batch = await AgentToolCallBatchRepository(db_session).create(
        session_id=str(session.id),
        turn_id=str(turn.id),
        status=AgentToolCallBatchStatus.EVALUATING,
        tool_call_count=2,
    )
    await AgentActionRepository(db_session).create(
        session_id=str(session.id),
        turn_id=str(turn.id),
        tool_batch_id=str(batch.id),
        tool_call_ordinal=0,
        tool_call_id="partial-1",
        kind="tool",
        name="projects.list",
        input={},
        risk_level="read",
        status=AgentActionStatus.COMPLETED,
        result={},
    )
    from app.services.agent_core import service as service_module

    wakeups: list[str] = []
    monkeypatch.setattr(
        service_module,
        "enqueue_turn_resume",
        lambda action_id, *_: wakeups.append(action_id),
    )
    maker = async_sessionmaker(
        bind=db_session.bind, expire_on_commit=False, class_=AsyncSession
    )
    async with maker() as restarted:
        summary = await AgentCoreService(restarted).recover_orphaned_turns()
        repaired = await AgentActionRepository(restarted).list_for_batch(str(batch.id))

    assert summary["enqueued"] == 1
    assert len(repaired) == 2
    assert repaired[1].status == AgentActionStatus.FAILED
    assert repaired[1].error["type"] == "BatchPreparationError"
    assert wakeups == [str(repaired[1].id)]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("statuses", "expected"),
    [
        ([AgentActionStatus.RUNNING, AgentActionStatus.WAITING_DECISION], "failed"),
        ([AgentActionStatus.RUNNING, AgentActionStatus.REQUESTED], "failed"),
        ([AgentActionStatus.WAITING_DECISION, AgentActionStatus.REQUESTED], "waiting"),
    ],
)
async def test_mixed_batch_recovery_uses_running_waiting_requested_priority(
    db_session,
    monkeypatch,
    statuses,
    expected,
):
    await _seed_runtime(db_session)
    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=None, workspace_id=DEFAULT_WORKSPACE_ID, user_id="dev"
    )
    turn = await service.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Recover mixed states.",
    )
    await _mark_turn_as_expired_execution(service, turn)
    batch = await AgentToolCallBatchRepository(db_session).create(
        session_id=str(session.id),
        turn_id=str(turn.id),
        status=AgentToolCallBatchStatus.WAITING,
        tool_call_count=2,
    )
    for ordinal, status in enumerate(statuses):
        await AgentActionRepository(db_session).create(
            session_id=str(session.id),
            turn_id=str(turn.id),
            tool_batch_id=str(batch.id),
            tool_call_ordinal=ordinal,
            tool_call_id=f"mixed-{ordinal}",
            kind="tool",
            name="bash",
            input={},
            risk_level="act_high",
            status=status,
        )
    from app.services.agent_core import service as service_module

    monkeypatch.setattr(service_module, "enqueue_turn_resume", lambda *_: None)
    outcome = await service._recover_turn(str(turn.id))

    assert outcome == expected


@pytest.mark.asyncio
async def test_recovery_never_crosses_earlier_unresolved_batch_when_timestamps_tie(
    db_session, monkeypatch
):
    await _seed_runtime(db_session)
    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=None, workspace_id=DEFAULT_WORKSPACE_ID, user_id="dev"
    )
    turn = await service.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Order barriers.",
    )
    await _mark_turn_as_expired_execution(service, turn)
    batches = ToolCallBatchCoordinator(db_session)
    first = await batches.create(
        session_id=str(session.id), turn_id=str(turn.id), tool_call_count=1
    )
    second = await batches.create(
        session_id=str(session.id), turn_id=str(turn.id), tool_call_count=1
    )
    await batches.batches.update_all(first, status=AgentToolCallBatchStatus.WAITING)
    await batches.batches.update_all(
        second, status=AgentToolCallBatchStatus.WAITING, created_at=first.created_at
    )
    await AgentActionRepository(db_session).create(
        session_id=str(session.id),
        turn_id=str(turn.id),
        tool_batch_id=str(first.id),
        tool_call_ordinal=0,
        tool_call_id="earlier",
        kind="tool",
        name="bash",
        input={},
        risk_level="act_high",
        status=AgentActionStatus.WAITING_DECISION,
    )
    await AgentActionRepository(db_session).create(
        session_id=str(session.id),
        turn_id=str(turn.id),
        tool_batch_id=str(second.id),
        tool_call_ordinal=0,
        tool_call_id="later",
        kind="tool",
        name="bash",
        input={},
        risk_level="act_high",
        status=AgentActionStatus.REQUESTED,
    )
    from app.services.agent_core import service as service_module

    wakeups: list[str] = []
    monkeypatch.setattr(
        service_module,
        "enqueue_turn_resume",
        lambda action_id, *_: wakeups.append(action_id),
    )
    assert await service._recover_turn(str(turn.id)) == "waiting"
    assert wakeups == []


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["cancel_turn", "interrupt_turn"])
async def test_cancel_and_interrupt_finalize_waiting_batch_idempotently(
    db_session, monkeypatch, operation
):
    async def fake_completion(*args, **kwargs):
        del args, kwargs
        return _response(
            tool_calls=[
                ("stop-1", "bash", {"command": "printf one"}),
                ("stop-2", "bash", {"command": "printf two"}),
            ]
        )

    _patch_model_gateway(monkeypatch, fake_completion)
    monkeypatch.setattr(
        "app.services.agent_core.service.cancel_turn_run", lambda *_: False
    )
    await _seed_runtime(db_session)
    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=None,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        permission_mode="ask_each_action",
    )
    turn = await service.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Wait then stop.",
    )
    session_id = str(session.id)
    turn_id = str(turn.id)
    waiting = await service.runtime.run_turn(str(turn.id))
    assert waiting.status == "waiting_approval"

    method = getattr(service, operation)
    first = await method(
        turn_id=turn_id, workspace_id=DEFAULT_WORKSPACE_ID, user_id="dev"
    )
    second = await method(
        turn_id=turn_id, workspace_id=DEFAULT_WORKSPACE_ID, user_id="dev"
    )
    assert first.status == second.status == AgentTurnStatus.CANCELLED

    maker = async_sessionmaker(
        bind=db_session.bind, expire_on_commit=False, class_=AsyncSession
    )
    async with maker() as fresh:
        actions = await AgentActionRepository(fresh).list_for_turn(turn_id)
        batches, _ = await AgentToolCallBatchRepository(fresh).list(limit=10)
        messages = await AgentMessageRepository(fresh).list_for_session(session_id)
        events = await AgentEventRepository(fresh).list_for_turn(turn_id=turn_id)
        fresh_session = await AgentSessionRepository(fresh).get(session_id)
        fresh_turn = await AgentTurnRepository(fresh).get(turn_id)
        provider_messages = await AgentContextAssembler(fresh).provider_messages(
            agent_session=fresh_session, turn=fresh_turn
        )

    assert all(action.status == AgentActionStatus.CANCELLED for action in actions)
    assert all(batch.status == AgentToolCallBatchStatus.CANCELLED for batch in batches)
    tool_messages = [message for message in messages if message.role == "tool"]
    assert [message.message_metadata["tool_call_id"] for message in tool_messages] == [
        "stop-1",
        "stop-2",
    ]
    event_type = "turn.cancelled" if operation == "cancel_turn" else "turn.interrupted"
    assert sum(event.type == event_type for event in events) == 1
    provider_tools = [
        message for message in provider_messages if message.get("role") == "tool"
    ]
    assert [message["tool_call_id"] for message in provider_tools] == [
        "stop-1",
        "stop-2",
    ]


@pytest.mark.asyncio
async def test_durable_cancel_while_model_is_awaiting_discards_tool_calls(
    db_session, monkeypatch
):
    completion_started = asyncio.Event()
    release_response = asyncio.Event()
    tool_runs = 0

    async def delayed_completion(*args, **kwargs):
        del args, kwargs
        completion_started.set()
        await release_response.wait()
        return _response(tool_calls=[("cancel-before-prepare", "projects__list", {})])

    async def count_run(self, input, context):
        nonlocal tool_runs
        del self, input, context
        tool_runs += 1
        return {"projects": [], "total_count": 0}

    _patch_model_gateway(monkeypatch, delayed_completion)
    monkeypatch.setattr(
        "app.services.agent_core.service.cancel_turn_run", lambda *_: False
    )
    monkeypatch.setattr(
        "app.services.agent_core.tools.platform.projects.ListProjectsTool.run",
        count_run,
    )
    await _seed_runtime(db_session)
    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=None, workspace_id=DEFAULT_WORKSPACE_ID, user_id="dev"
    )
    turn = await service.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Cancel while the model is responding.",
    )
    session_id = str(session.id)
    turn_id = str(turn.id)
    maker = async_sessionmaker(
        bind=db_session.bind, expire_on_commit=False, class_=AsyncSession
    )

    async with maker() as worker_session, maker() as cancelling_session:
        worker_task = asyncio.create_task(
            AgentCoreService(worker_session).runtime.run_turn(turn_id)
        )
        await asyncio.wait_for(completion_started.wait(), timeout=1)
        await AgentCoreService(cancelling_session).cancel_turn(
            turn_id=turn_id,
            workspace_id=DEFAULT_WORKSPACE_ID,
            user_id="dev",
        )
        release_response.set()
        cancelled = await asyncio.wait_for(worker_task, timeout=2)

    async with maker() as fresh:
        fresh_turn = await AgentTurnRepository(fresh).get_fresh(turn_id)
        batches, _ = await AgentToolCallBatchRepository(fresh).list(limit=10)
        actions = await AgentActionRepository(fresh).list_for_turn(turn_id)
        messages = await AgentMessageRepository(fresh).list_for_session(session_id)

    assert cancelled.status == AgentTurnStatus.CANCELLED
    assert fresh_turn.status == AgentTurnStatus.CANCELLED
    assert batches == []
    assert actions == []
    assert tool_runs == 0
    assert not any(message.role == "assistant" for message in messages)


@pytest.mark.asyncio
async def test_durable_cancel_after_prepare_commit_prevents_tool_execution(
    db_session, monkeypatch
):
    prepared_committed = asyncio.Event()
    release_execution_guard = asyncio.Event()
    tool_runs = 0
    model_calls = 0

    async def fake_completion(*args, **kwargs):
        nonlocal model_calls
        del args, kwargs
        model_calls += 1
        if model_calls == 1:
            return _response(
                tool_calls=[("cancel-after-prepare", "projects__list", {})]
            )
        return _response(text="must not continue")

    async def count_run(self, input, context):
        nonlocal tool_runs
        del self, input, context
        tool_runs += 1
        return {"projects": [], "total_count": 0}

    from app.services.agent_core.core.loop import AgentLoopController

    original_guard = getattr(
        AgentLoopController, "_ensure_turn_allows_tool_execution", None
    )

    async def pause_after_commit(self, turn_id):
        prepared_committed.set()
        await release_execution_guard.wait()
        assert original_guard is not None
        return await original_guard(self, turn_id)

    _patch_model_gateway(monkeypatch, fake_completion)
    monkeypatch.setattr(
        "app.services.agent_core.service.cancel_turn_run", lambda *_: False
    )
    monkeypatch.setattr(
        "app.services.agent_core.tools.platform.projects.ListProjectsTool.run",
        count_run,
    )
    monkeypatch.setattr(
        AgentLoopController,
        "_ensure_turn_allows_tool_execution",
        pause_after_commit,
        raising=False,
    )
    await _seed_runtime(db_session)
    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=None, workspace_id=DEFAULT_WORKSPACE_ID, user_id="dev"
    )
    turn = await service.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Cancel after durable preparation.",
    )
    session_id = str(session.id)
    turn_id = str(turn.id)
    maker = async_sessionmaker(
        bind=db_session.bind, expire_on_commit=False, class_=AsyncSession
    )

    async with maker() as worker_session, maker() as cancelling_session:
        worker_task = asyncio.create_task(
            AgentCoreService(worker_session).runtime.run_turn(turn_id)
        )
        await asyncio.wait_for(prepared_committed.wait(), timeout=1)
        await AgentCoreService(cancelling_session).cancel_turn(
            turn_id=turn_id,
            workspace_id=DEFAULT_WORKSPACE_ID,
            user_id="dev",
        )
        release_execution_guard.set()
        cancelled = await asyncio.wait_for(worker_task, timeout=2)

    async with maker() as fresh:
        fresh_turn = await AgentTurnRepository(fresh).get_fresh(turn_id)
        actions = await AgentActionRepository(fresh).list_for_turn(turn_id)
        batches, _ = await AgentToolCallBatchRepository(fresh).list(limit=10)
        messages = await AgentMessageRepository(fresh).list_for_session(session_id)

    assert cancelled.status == AgentTurnStatus.CANCELLED
    assert fresh_turn.status == AgentTurnStatus.CANCELLED
    assert tool_runs == 0
    assert len(batches) == 1
    assert batches[0].status == AgentToolCallBatchStatus.CANCELLED
    assert len(actions) == 1
    assert actions[0].status == AgentActionStatus.CANCELLED
    tool_messages = [message for message in messages if message.role == "tool"]
    assert [message.message_metadata["tool_call_id"] for message in tool_messages] == [
        "cancel-after-prepare"
    ]
