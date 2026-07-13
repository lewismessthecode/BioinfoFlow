from __future__ import annotations

import json
import asyncio

import pytest

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
from app.services.agent_core.transcript import AgentTranscriptStore, tool_calls_part
from app.services.agent_core.tools.batches import ToolCallBatchCoordinator
from app.schemas.agent_core import AgentActionRead
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
        function = type("Function", (), {"name": name, "arguments": json.dumps(arguments)})()
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

    monkeypatch.setattr("app.services.agent_core.core.loop.acompletion", fake_completion)
    monkeypatch.setattr("app.services.agent_core.service.enqueue_turn_resume", lambda *_: None)
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
    batch = await AgentToolCallBatchRepository(db_session).get(str(actions[0].tool_batch_id))
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
    messages = await AgentMessageRepository(db_session).list_for_session(str(session.id))
    tool_messages = [message for message in messages if message.role == "tool"]
    assert [message.message_metadata["tool_call_id"] for message in tool_messages] == [
        "call-1",
        "call-2",
        "call-3",
    ]
    batch = await AgentToolCallBatchRepository(db_session).get(str(actions[0].tool_batch_id))
    assert batch is not None
    assert batch.status == AgentToolCallBatchStatus.TERMINAL


@pytest.mark.asyncio
async def test_batch_repository_restart_decision_uses_persisted_action_state(db_session):
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

    monkeypatch.setattr("app.services.agent_core.runtime.acompletion", fake_completion)
    monkeypatch.setattr("app.services.agent_core.service.enqueue_turn_resume", lambda *_: None)
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
async def test_provider_messages_repair_and_audit_incomplete_tool_call_group(db_session):
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
                    {"id": "old-1", "type": "function", "function": {"name": "x", "arguments": "{}"}},
                    {"id": "old-2", "type": "function", "function": {"name": "x", "arguments": "{}"}},
                ]
            )
        ],
    )
    await transcript.append_text(
        session_id=str(session.id),
        turn_id=str(turn.id),
        role="tool",
        text="old first",
        metadata={"tool_call_id": "old-1", "tool_batch_id": "old-batch", "action_id": "old-action-1"},
    )
    await transcript.append_text(
        session_id=str(session.id), turn_id=str(turn.id), role="user", text="later user"
    )
    await transcript.append_text(
        session_id=str(session.id), turn_id=str(turn.id), role="assistant", text="later assistant"
    )

    messages = await AgentContextAssembler(db_session).provider_messages(
        agent_session=session,
        turn=turn,
    )
    relevant = [message for message in messages if message["role"] != "system"]

    tool_group_index = next(i for i, message in enumerate(relevant) if message.get("tool_calls"))
    assert [message["role"] for message in relevant[tool_group_index : tool_group_index + 5]] == [
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
async def test_mixed_reads_complete_but_model_waits_for_approval(db_session, monkeypatch):
    calls = 0

    async def fake_completion(*args, **kwargs):
        nonlocal calls
        del args, kwargs
        calls += 1
        return _response(
            tool_calls=[
                ("read-1", "projects__list", {}),
                ("approval", "bash", {"command": "printf approved"}),
                ("read-2", "projects__list", {}),
            ]
        )

    monkeypatch.setattr("app.services.agent_core.runtime.acompletion", fake_completion)
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
        AgentActionStatus.COMPLETED,
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
        session_id=str(session.id), turn_id=str(turn.id), role="assistant", text="old" * 100
    )
    batch_message = await transcript.append_parts(
        session_id=str(session.id),
        turn_id=str(turn.id),
        role="assistant",
        parts=[
            tool_calls_part(
                [
                    {"id": "compact-1", "type": "function", "function": {"name": "x", "arguments": "{}"}},
                    {"id": "compact-2", "type": "function", "function": {"name": "x", "arguments": "{}"}},
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
    assert [message.get("tool_call_id") for message in messages if message["role"] == "tool"] == [
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
    maker = async_sessionmaker(bind=db_session.bind, expire_on_commit=False, class_=AsyncSession)
    async with maker() as first, maker() as second:
        results = await asyncio.gather(
            ToolCallBatchCoordinator(first).claim_continuation(str(batch.id)),
            ToolCallBatchCoordinator(second).claim_continuation(str(batch.id)),
        )

    assert sorted(results) == [False, True]


@pytest.mark.asyncio
async def test_duplicate_settle_never_downgrades_claimed_or_terminal_batch(db_session):
    await _seed_runtime(db_session)
    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=None, workspace_id=DEFAULT_WORKSPACE_ID, user_id="dev"
    )
    turn = await service.create_turn_record(
        session_id=str(session.id), workspace_id=DEFAULT_WORKSPACE_ID, user_id="dev", input_text="Settle once."
    )
    batches = ToolCallBatchCoordinator(db_session)
    batch = await batches.create(session_id=str(session.id), turn_id=str(turn.id), tool_call_count=1)
    await AgentActionRepository(db_session).create(
        session_id=str(session.id), turn_id=str(turn.id), tool_batch_id=str(batch.id),
        tool_call_ordinal=0, tool_call_id="settle", kind="tool", name="x", input={},
        risk_level="read", status=AgentActionStatus.COMPLETED,
    )
    assert await batches.settle(str(batch.id)) == "ready"
    assert await batches.claim_continuation(str(batch.id)) is True
    assert await batches.settle(str(batch.id)) == "ready"
    assert (await AgentToolCallBatchRepository(db_session).get_fresh(str(batch.id))).status == AgentToolCallBatchStatus.CONTINUING
    await batches.mark_terminal(str(batch.id))
    assert await batches.settle(str(batch.id)) == "ready"
    assert (await AgentToolCallBatchRepository(db_session).get_fresh(str(batch.id))).status == AgentToolCallBatchStatus.TERMINAL


@pytest.mark.asyncio
async def test_empty_ordinary_turn_has_no_continuation_state_error(db_session, monkeypatch):
    async def empty_completion(*args, **kwargs):
        del args, kwargs
        return _response(text="")

    monkeypatch.setattr("app.services.agent_core.runtime.acompletion", empty_completion)
    await _seed_runtime(db_session)
    service = AgentCoreService(db_session)
    session = await service.create_session(project_id=None, workspace_id=DEFAULT_WORKSPACE_ID, user_id="dev")
    turn = await service.create_turn_record(
        session_id=str(session.id), workspace_id=DEFAULT_WORKSPACE_ID, user_id="dev", input_text="Return empty."
    )
    failed = await service.runtime.run_turn(str(turn.id))
    assert failed.error_code == "empty_model_response"


@pytest.mark.asyncio
async def test_reads_overlap_across_non_read_sibling(db_session, monkeypatch):
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
    monkeypatch.setattr("app.services.agent_core.service.enqueue_turn_resume", lambda *_: None)
    calls = 0

    async def fake_completion(*args, **kwargs):
        nonlocal calls
        del args, kwargs
        calls += 1
        return _response(
            tool_calls=[
                ("overlap-1", "projects__list", {}),
                ("approval-between", "bash", {"command": "printf later"}),
                ("overlap-2", "projects__list", {}),
            ]
        )

    monkeypatch.setattr("app.services.agent_core.runtime.acompletion", fake_completion)
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
    assert [actions[0].status, actions[2].status] == [
        AgentActionStatus.COMPLETED,
        AgentActionStatus.COMPLETED,
    ]


@pytest.mark.asyncio
async def test_duplicate_provider_call_id_is_scoped_to_each_batch(db_session, monkeypatch):
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

    monkeypatch.setattr("app.services.agent_core.runtime.acompletion", fake_completion)
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
async def test_prepare_failure_repairs_every_call_with_terminal_result(db_session, monkeypatch):
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

    monkeypatch.setattr("app.services.agent_core.runtime.acompletion", fake_completion)
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
    batch = await AgentToolCallBatchRepository(db_session).get(str(actions[0].tool_batch_id))
    assert batch is not None
    assert batch.status == AgentToolCallBatchStatus.FAILED


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

    monkeypatch.setattr("app.services.agent_core.runtime.acompletion", fake_completion)
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
    session = await service.create_session(project_id=None, workspace_id=DEFAULT_WORKSPACE_ID, user_id="dev")
    turn = await service.create_turn_record(
        session_id=str(session.id), workspace_id=DEFAULT_WORKSPACE_ID, user_id="dev", input_text="Cancel prepare."
    )
    cancelled = await service.runtime.run_turn(str(turn.id))
    assert cancelled.status == "cancelled"
    actions = await AgentActionRepository(db_session).list_for_turn(str(turn.id))
    assert len(actions) == 2
    assert all(action.status == AgentActionStatus.CANCELLED for action in actions)
    batch = await AgentToolCallBatchRepository(db_session).get(str(actions[0].tool_batch_id))
    assert batch.status == AgentToolCallBatchStatus.CANCELLED


@pytest.mark.asyncio
async def test_execution_cancellation_cancels_committed_batch(db_session, monkeypatch):
    async def fake_completion(*args, **kwargs):
        del args, kwargs
        return _response(tool_calls=[("cancel-run", "projects__list", {})])

    async def cancel_run(self, input, context):
        del self, input, context
        raise asyncio.CancelledError

    monkeypatch.setattr("app.services.agent_core.runtime.acompletion", fake_completion)
    monkeypatch.setattr(
        "app.services.agent_core.tools.platform.projects.ListProjectsTool.run", cancel_run
    )
    await _seed_runtime(db_session)
    service = AgentCoreService(db_session)
    session = await service.create_session(project_id=None, workspace_id=DEFAULT_WORKSPACE_ID, user_id="dev")
    turn = await service.create_turn_record(
        session_id=str(session.id), workspace_id=DEFAULT_WORKSPACE_ID, user_id="dev", input_text="Cancel execution."
    )
    cancelled = await service.runtime.run_turn(str(turn.id))
    assert cancelled.status == "cancelled"
    actions = await AgentActionRepository(db_session).list_for_turn(str(turn.id))
    batch = await AgentToolCallBatchRepository(db_session).get_fresh(str(actions[0].tool_batch_id))
    assert actions[0].status == AgentActionStatus.CANCELLED
    assert batch.status == AgentToolCallBatchStatus.CANCELLED


@pytest.mark.asyncio
async def test_failed_b_preparation_terminalizes_prior_a_in_same_transition(db_session, monkeypatch):
    calls = 0

    async def fake_completion(*args, **kwargs):
        nonlocal calls
        del args, kwargs
        calls += 1
        if calls == 1:
            return _response(tool_calls=[("a-read", "projects__list", {})])
        return _response(tool_calls=[("b-denied", "ask_user", {"questions": []})])

    monkeypatch.setattr("app.services.agent_core.runtime.acompletion", fake_completion)
    await _seed_runtime(db_session)
    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=None, workspace_id=DEFAULT_WORKSPACE_ID, user_id="dev", role_profile="worker"
    )
    turn = await service.create_turn_record(
        session_id=str(session.id), workspace_id=DEFAULT_WORKSPACE_ID, user_id="dev", input_text="A then denied B."
    )
    failed = await service.runtime.run_turn(str(turn.id))
    assert failed.error_code == "tool_not_exposed"
    batches, _ = await AgentToolCallBatchRepository(db_session).list(limit=10)
    batches.sort(key=lambda batch: batch.batch_ordinal)
    assert [batch.batch_ordinal for batch in batches] == [1, 2]
    assert batches[0].status == AgentToolCallBatchStatus.TERMINAL
    assert batches[1].status == AgentToolCallBatchStatus.FAILED


@pytest.mark.asyncio
async def test_assistant_batch_and_all_actions_become_visible_atomically(db_session, monkeypatch):
    model_calls = 0

    async def fake_completion(*args, **kwargs):
        nonlocal model_calls
        del args, kwargs
        model_calls += 1
        if model_calls > 1:
            return _response(text="atomic complete")
        return _response(tool_calls=[("atomic-1", "projects__list", {}), ("atomic-2", "projects__list", {})])

    monkeypatch.setattr("app.services.agent_core.runtime.acompletion", fake_completion)
    from app.services.agent_core.tools.executor import AgentToolExecutor

    original_execute = AgentToolExecutor.execute
    count = 0
    maker = async_sessionmaker(bind=db_session.bind, expire_on_commit=False, class_=AsyncSession)

    async def inspect_second_prepare(self, **kwargs):
        nonlocal count
        count += 1
        if count == 2:
            async with maker() as observer:
                observed_actions, _ = await AgentActionRepository(observer).list(limit=10)
                observed_batches, _ = await AgentToolCallBatchRepository(observer).list(limit=10)
                observed_messages, _ = await AgentMessageRepository(observer).list(limit=20)
                assert observed_actions == []
                assert observed_batches == []
                assert not any(message.role == "assistant" for message in observed_messages)
        return await original_execute(self, **kwargs)

    monkeypatch.setattr(AgentToolExecutor, "execute", inspect_second_prepare)
    await _seed_runtime(db_session)
    service = AgentCoreService(db_session)
    session = await service.create_session(project_id=None, workspace_id=DEFAULT_WORKSPACE_ID, user_id="dev")
    turn = await service.create_turn_record(
        session_id=str(session.id), workspace_id=DEFAULT_WORKSPACE_ID, user_id="dev", input_text="Commit atomically."
    )
    await service.runtime.run_turn(str(turn.id))
    actions = await AgentActionRepository(db_session).list_for_turn(str(turn.id))
    assert len(actions) == 2
    assert len({action.tool_batch_id for action in actions}) == 1


@pytest.mark.asyncio
async def test_batch_stays_continuing_until_next_model_message_is_persisted(
    db_session,
    monkeypatch,
):
    calls = 0
    maker = async_sessionmaker(bind=db_session.bind, expire_on_commit=False, class_=AsyncSession)

    async def fake_completion(*args, **kwargs):
        nonlocal calls
        del args, kwargs
        calls += 1
        if calls == 1:
            return _response(tool_calls=[("continue-state", "projects__list", {})])
        async with maker() as check_session:
            batches, _ = await AgentToolCallBatchRepository(check_session).list(limit=10)
            assert batches[0].status == AgentToolCallBatchStatus.CONTINUING
        return _response(text="persisted continuation")

    monkeypatch.setattr("app.services.agent_core.runtime.acompletion", fake_completion)
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
async def test_model_failure_releases_and_retries_continuing_batch(db_session, monkeypatch):
    calls = 0

    async def fake_completion(*args, **kwargs):
        nonlocal calls
        del args, kwargs
        calls += 1
        if calls == 1:
            return _response(tool_calls=[("recover-continuing", "projects__list", {})])
        raise RuntimeError("model unavailable after claim")

    monkeypatch.setattr("app.services.agent_core.core.loop.acompletion", fake_completion)
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
        provider="openai_compatible",
        model="batch-model",
        request_args={},
        continuation_failure_mode="ready",
    )

    assert failed.termination_reason == "model_failed"
    batches, _ = await AgentToolCallBatchRepository(db_session).list(limit=10)
    assert batches[0].status == AgentToolCallBatchStatus.READY

    async def recovered_completion(*args, **kwargs):
        del args, kwargs
        return _response(text="recovered continuation")

    monkeypatch.setattr(
        "app.services.agent_core.core.loop.acompletion", recovered_completion
    )
    recovered = await controller.run_turn(
        turn_id=str(turn.id),
        provider="openai_compatible",
        model="batch-model",
        request_args={},
        continuation_batch_id=str(batches[0].id),
    )

    assert recovered.final_text == "recovered continuation"
    recovered_batch = await AgentToolCallBatchRepository(db_session).get(str(batches[0].id))
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
    turn = await service.turn_repo.update_all(turn, status="waiting_approval")
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
    maker = async_sessionmaker(bind=db_session.bind, expire_on_commit=False, class_=AsyncSession)
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
async def test_restart_repairs_partially_prepared_evaluating_batch(db_session, monkeypatch):
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
    await service.turn_repo.update_all(turn, status="waiting_approval")
    transcript = AgentTranscriptStore(db_session)
    await transcript.append_parts(
        session_id=str(session.id),
        turn_id=str(turn.id),
        role="assistant",
        parts=[
            tool_calls_part(
                [
                    {"id": "partial-1", "type": "function", "function": {"name": "projects__list", "arguments": "{}"}},
                    {"id": "partial-2", "type": "function", "function": {"name": "projects__list", "arguments": "{}"}},
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
    maker = async_sessionmaker(bind=db_session.bind, expire_on_commit=False, class_=AsyncSession)
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
    await service.turn_repo.update_all(turn, status="waiting_approval")
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
    session = await service.create_session(project_id=None, workspace_id=DEFAULT_WORKSPACE_ID, user_id="dev")
    turn = await service.create_turn_record(
        session_id=str(session.id), workspace_id=DEFAULT_WORKSPACE_ID, user_id="dev", input_text="Order barriers."
    )
    await service.turn_repo.update_all(turn, status="waiting_approval")
    batches = ToolCallBatchCoordinator(db_session)
    first = await batches.create(session_id=str(session.id), turn_id=str(turn.id), tool_call_count=1)
    second = await batches.create(session_id=str(session.id), turn_id=str(turn.id), tool_call_count=1)
    await batches.batches.update_all(first, status=AgentToolCallBatchStatus.WAITING)
    await batches.batches.update_all(second, status=AgentToolCallBatchStatus.WAITING, created_at=first.created_at)
    await AgentActionRepository(db_session).create(
        session_id=str(session.id), turn_id=str(turn.id), tool_batch_id=str(first.id), tool_call_ordinal=0,
        tool_call_id="earlier", kind="tool", name="bash", input={}, risk_level="act_high",
        status=AgentActionStatus.WAITING_DECISION,
    )
    await AgentActionRepository(db_session).create(
        session_id=str(session.id), turn_id=str(turn.id), tool_batch_id=str(second.id), tool_call_ordinal=0,
        tool_call_id="later", kind="tool", name="bash", input={}, risk_level="act_high",
        status=AgentActionStatus.REQUESTED,
    )
    from app.services.agent_core import service as service_module
    wakeups: list[str] = []
    monkeypatch.setattr(service_module, "enqueue_turn_resume", lambda action_id, *_: wakeups.append(action_id))
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

    monkeypatch.setattr("app.services.agent_core.runtime.acompletion", fake_completion)
    monkeypatch.setattr("app.services.agent_core.service.cancel_turn_run", lambda *_: False)
    await _seed_runtime(db_session)
    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=None, workspace_id=DEFAULT_WORKSPACE_ID, user_id="dev", permission_mode="ask_each_action"
    )
    turn = await service.create_turn_record(
        session_id=str(session.id), workspace_id=DEFAULT_WORKSPACE_ID, user_id="dev", input_text="Wait then stop."
    )
    session_id = str(session.id)
    turn_id = str(turn.id)
    waiting = await service.runtime.run_turn(str(turn.id))
    assert waiting.status == "waiting_approval"

    method = getattr(service, operation)
    first = await method(turn_id=turn_id, workspace_id=DEFAULT_WORKSPACE_ID, user_id="dev")
    second = await method(turn_id=turn_id, workspace_id=DEFAULT_WORKSPACE_ID, user_id="dev")
    assert first.status == second.status == AgentTurnStatus.CANCELLED

    maker = async_sessionmaker(bind=db_session.bind, expire_on_commit=False, class_=AsyncSession)
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
        "stop-1", "stop-2"
    ]
    event_type = "turn.cancelled" if operation == "cancel_turn" else "turn.interrupted"
    assert sum(event.type == event_type for event in events) == 1
    provider_tools = [message for message in provider_messages if message.get("role") == "tool"]
    assert [message["tool_call_id"] for message in provider_tools] == ["stop-1", "stop-2"]


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

    monkeypatch.setattr("app.services.agent_core.runtime.acompletion", delayed_completion)
    monkeypatch.setattr("app.services.agent_core.service.cancel_turn_run", lambda *_: False)
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

    monkeypatch.setattr("app.services.agent_core.runtime.acompletion", fake_completion)
    monkeypatch.setattr("app.services.agent_core.service.cancel_turn_run", lambda *_: False)
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
