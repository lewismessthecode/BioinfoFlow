from __future__ import annotations

import asyncio
import sys

import pytest

from app.config import settings
from app.models.llm import LlmModel, LlmProvider
from app.models.project import Project
from app.models.workspace import Workspace
from app.repositories.agent_core_repo import (
    AgentActionRepository,
    AgentEventRepository,
    AgentMessageRepository,
)
from app.services.agent_core import AgentCoreService
from app.services.agent_core.ledger import AgentEventLedger
from app.services.agent_core.tools import AgentToolContext, build_default_tool_registry
from app.services.agent_core.tools.executor import AgentToolExecutor
from app.services.agent_core.tools.toolsets import ToolsetExposure
from app.utils.exceptions import PermissionDeniedError
from app.workspace import DEFAULT_WORKSPACE_ID


async def _workspace(db_session) -> Workspace:
    workspace = Workspace(id=DEFAULT_WORKSPACE_ID, name="Team", slug="team")
    db_session.add(workspace)
    await db_session.commit()
    return workspace


async def _project(db_session) -> Project:
    project = Project(
        name="Harness Project",
        description="Agent harness invariant tests",
        user_id="dev",
        created_by_user_id="dev",
        workspace_id=DEFAULT_WORKSPACE_ID,
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)
    return project


async def _seed_catalog_model(db_session, *, model_id: str = "harness-model") -> LlmModel:
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
        supports_streaming=True,
    )
    db_session.add(model)
    await db_session.commit()
    await db_session.refresh(model)
    return model


@pytest.mark.asyncio
async def test_session_can_start_without_project_and_keeps_prompt_snapshot(db_session):
    await _workspace(db_session)

    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=None,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        title="Workspace triage",
    )

    assert session.project_id is None
    assert session.runtime_mode == "api"
    assert session.prompt_snapshot["id"] == "bioinfoflow-agent-v1"
    assert session.toolset_policy["name"] == "default"


@pytest.mark.asyncio
async def test_turn_writes_canonical_user_and_assistant_messages(db_session, monkeypatch):
    async def fake_completion(*args, **kwargs):
        class FakeUsage:
            def model_dump(self):
                return {"prompt_tokens": 3, "completion_tokens": 5, "total_tokens": 8}

        class FakeMessage:
            content = "Use hg38 for this project."
            tool_calls = None

        class FakeChoice:
            message = FakeMessage()

        class FakeResponse:
            choices = [FakeChoice()]
            usage = FakeUsage()

        return FakeResponse()

    monkeypatch.setattr("app.services.agent_core.core.loop.acompletion", fake_completion)
    await _workspace(db_session)
    await _seed_catalog_model(db_session)

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
        input_text="Remember that we use hg38.",
    )
    turn = await service.runtime.run_turn(str(turn.id))

    messages = await AgentMessageRepository(db_session).list_for_session(str(session.id))
    assert turn.termination_reason == "assistant_final"
    assert [(message.role, message.status) for message in messages] == [
        ("user", "committed"),
        ("assistant", "committed"),
    ]
    assert messages[0].content_parts == [
        {"type": "text", "text": "Remember that we use hg38."}
    ]
    assert messages[1].content_parts == [
        {"type": "text", "text": "Use hg38 for this project."}
    ]


@pytest.mark.asyncio
async def test_event_sequence_is_session_scoped_across_turns(db_session, monkeypatch):
    async def fake_completion(*args, **kwargs):
        class FakeMessage:
            content = "ok"
            tool_calls = None

        class FakeChoice:
            message = FakeMessage()

        class FakeResponse:
            choices = [FakeChoice()]
            usage = None

        return FakeResponse()

    monkeypatch.setattr("app.services.agent_core.core.loop.acompletion", fake_completion)
    await _workspace(db_session)
    await _seed_catalog_model(db_session)

    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=None,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )
    for text in ["first", "second"]:
        turn = await service.create_turn_record(
            session_id=str(session.id),
            workspace_id=DEFAULT_WORKSPACE_ID,
            user_id="dev",
            input_text=text,
        )
        await service.runtime.run_turn(str(turn.id))

    events = await AgentEventRepository(db_session).list_for_session(
        session_id=str(session.id)
    )
    assert [event.seq for event in events] == list(range(1, len(events) + 1))


@pytest.mark.asyncio
async def test_event_ledger_serializes_concurrent_sequence_allocation():
    class FakeSession:
        async def rollback(self):
            return None

    class FakeEvent:
        def __init__(self, seq: int):
            self.seq = seq

    class RacingEventRepository:
        session = FakeSession()

        def __init__(self):
            self.current = 0

        async def next_seq(self, session_id: str) -> int:
            assert session_id == "session-1"
            next_seq = self.current + 1
            await asyncio.sleep(0)
            return next_seq

        async def create(self, **payload):
            await asyncio.sleep(0)
            seq = payload["seq"]
            if seq != self.current + 1:
                raise AssertionError("event sequence allocation raced")
            self.current = seq
            return FakeEvent(seq)

    ledger = AgentEventLedger.__new__(AgentEventLedger)
    ledger.event_repo = RacingEventRepository()

    first, second = await asyncio.gather(
        ledger.append(
            session_id="session-1",
            turn_id="turn-1",
            type="turn.created",
        ),
        ledger.append(
            session_id="session-1",
            turn_id="turn-2",
            type="turn.created",
        ),
    )

    assert sorted([first.seq, second.seq]) == [1, 2]


def test_toolset_exposure_does_not_expose_shell_by_default():
    registry = build_default_tool_registry()

    default_tools = ToolsetExposure(registry).exposed_specs(
        policy={"name": "default"},
        role="orchestrator",
    )
    elevated_tools = ToolsetExposure(registry).exposed_specs(
        policy={"name": "execution"},
        role="orchestrator",
    )

    assert "execution.shell" not in {tool.name for tool in default_tools}
    assert "execution.shell" in {tool.name for tool in elevated_tools}


@pytest.mark.asyncio
async def test_unexposed_tool_is_denied_before_argument_validation(db_session):
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
        input_text="Try hidden tool.",
    )

    executor = AgentToolExecutor(db_session, build_default_tool_registry())
    with pytest.raises(PermissionDeniedError, match="not exposed"):
        await executor.execute(
            tool_name="execution.shell",
            input={},
            context=AgentToolContext(
                db=db_session,
                workspace_id=DEFAULT_WORKSPACE_ID,
                user_id="dev",
                session_id=str(session.id),
                turn_id=str(turn.id),
            ),
            toolset_policy={"name": "default"},
        )


@pytest.mark.asyncio
async def test_approval_resume_executes_tool_and_continues_turn(db_session, monkeypatch):
    calls = 0

    async def fake_completion(*args, **kwargs):
        nonlocal calls
        calls += 1

        class FakeUsage:
            def model_dump(self):
                return {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}

        class FakeResponse:
            usage = FakeUsage()

        class FakeChoice:
            pass

        class FakeMessage:
            pass

        message = FakeMessage()
        if calls == 1:
            class FakeFunction:
                name = "execution__shell"
                arguments = (
                    '{"command":["'
                    + sys.executable
                    + '","-c","print(\\\"approved-tool\\\")"],"cwd":"'
                    + str(settings.bioinfoflow_home)
                    + '"}'
                )

            class FakeToolCall:
                id = "tool-call-1"
                function = FakeFunction()

            message.content = ""
            message.tool_calls = [FakeToolCall()]
        else:
            messages = kwargs["messages"]
            assistant_tool_call = next(
                message for message in messages if message.get("tool_calls")
            )
            tool_result = next(message for message in messages if message["role"] == "tool")
            assert assistant_tool_call["tool_calls"][0]["id"] == "tool-call-1"
            assert assistant_tool_call["tool_calls"][0]["function"]["name"] == "execution__shell"
            assert tool_result["tool_call_id"] == "tool-call-1"
            message.content = "Final after approved tool."
            message.tool_calls = None

        choice = FakeChoice()
        choice.message = message
        response = FakeResponse()
        response.choices = [choice]
        return response

    monkeypatch.setattr("app.services.agent_core.runtime.acompletion", fake_completion)
    monkeypatch.setattr("app.services.agent_core.service.enqueue_turn_resume", lambda *_args: None)
    await _workspace(db_session)
    await _seed_catalog_model(db_session)

    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=None,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )
    session = await service.session_repo.update_all(session, toolset_policy={"name": "execution"})
    turn = await service.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Run approved shell and report back.",
    )

    waiting_turn = await service.runtime.run_turn(str(turn.id))
    assert waiting_turn.status == "waiting_approval"
    actions = await AgentActionRepository(db_session).list_for_turn(str(turn.id))
    assert actions[0].status == "waiting_decision"

    decided = await service.decide_action(
        action_id=str(actions[0].id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        decision="approve",
    )
    assert decided.status == "requested"

    resumed_turn = await service.runtime.resume_turn_after_action(str(actions[0].id))
    assert resumed_turn.status == "completed"
    assert resumed_turn.final_text == "Final after approved tool."

    messages = await AgentMessageRepository(db_session).list_for_session(str(session.id))
    assert [message.role for message in messages] == ["user", "assistant", "tool", "assistant"]
    assert "approved-tool" in messages[2].content_parts[0]["text"]


@pytest.mark.asyncio
async def test_rejected_tool_decision_continues_turn_with_tool_result(db_session, monkeypatch):
    calls = 0

    async def fake_completion(*args, **kwargs):
        nonlocal calls
        calls += 1

        class FakeResponse:
            usage = None

        class FakeChoice:
            pass

        class FakeMessage:
            pass

        message = FakeMessage()
        if calls == 1:
            class FakeFunction:
                name = "execution__shell"
                arguments = (
                    '{"command":["'
                    + sys.executable
                    + '","-c","print(\\\"should-not-run\\\")"],"cwd":"'
                    + str(settings.bioinfoflow_home)
                    + '"}'
                )

            class FakeToolCall:
                id = "tool-call-rejected"
                function = FakeFunction()

            message.content = ""
            message.tool_calls = [FakeToolCall()]
        else:
            tool_result = next(
                item for item in kwargs["messages"] if item["role"] == "tool"
            )
            assert tool_result["tool_call_id"] == "tool-call-rejected"
            assert "UserRejected" in tool_result["content"]
            message.content = "I will continue without running that tool."
            message.tool_calls = None

        choice = FakeChoice()
        choice.message = message
        response = FakeResponse()
        response.choices = [choice]
        return response

    monkeypatch.setattr("app.services.agent_core.runtime.acompletion", fake_completion)
    monkeypatch.setattr("app.services.agent_core.service.enqueue_turn_resume", lambda *_args: None)
    await _workspace(db_session)
    await _seed_catalog_model(db_session)

    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=None,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )
    session = await service.session_repo.update_all(session, toolset_policy={"name": "execution"})
    turn = await service.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Try shell only if approved.",
    )

    waiting_turn = await service.runtime.run_turn(str(turn.id))
    assert waiting_turn.status == "waiting_approval"
    actions = await AgentActionRepository(db_session).list_for_turn(str(turn.id))

    decided = await service.decide_action(
        action_id=str(actions[0].id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        decision="reject",
    )
    assert decided.status == "rejected"

    resumed_turn = await service.runtime.resume_turn_after_action(str(actions[0].id))
    assert resumed_turn.status == "completed"
    assert resumed_turn.final_text == "I will continue without running that tool."


@pytest.mark.asyncio
async def test_interrupt_marks_turn_with_named_termination_reason(db_session):
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
        input_text="Stop before running.",
    )

    interrupted = await service.interrupt_turn(
        turn_id=str(turn.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )

    assert interrupted.status == "cancelled"
    assert interrupted.termination_reason == "interrupted"
    assert interrupted.interrupt_requested_at is not None
