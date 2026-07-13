from __future__ import annotations

import asyncio
import json
import sys

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import settings
from app.models.agent_core import AgentActionStatus, AgentTurnStatus
from app.models.llm import LlmModel, LlmProvider
from app.models.workspace import Workspace
from app.repositories.agent_core_repo import (
    AgentActionRepository,
    AgentEventRepository,
    AgentMessageRepository,
    AgentTurnRepository,
)
from app.services.agent_core import AgentCoreService
from app.services.agent_core.execution_target import session_metadata_with_execution_target
from app.services.agent_core.events import AgentEventType
from app.services.agent_core.ledger import AgentEventLedger
from app.utils.exceptions import ConflictError
from app.workspace import DEFAULT_WORKSPACE_ID


async def _workspace(db_session: AsyncSession) -> Workspace:
    workspace = Workspace(id=DEFAULT_WORKSPACE_ID, name="Team", slug="team")
    db_session.add(workspace)
    await db_session.commit()
    return workspace


async def _seed_catalog_model(
    db_session: AsyncSession,
    *,
    model_id: str,
    supports_streaming: bool = True,
) -> LlmModel:
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
        supports_streaming=supports_streaming,
    )
    db_session.add(model)
    await db_session.commit()
    await db_session.refresh(model)
    return model


def _completion(*, tool_name: str | None = None, arguments: dict | None = None):
    class FakeResponse:
        usage = None

    class FakeChoice:
        pass

    class FakeMessage:
        pass

    message = FakeMessage()
    if tool_name is None:
        message.content = "Done."
        message.tool_calls = None
    else:
        encoded_arguments = json.dumps(arguments or {})

        class FakeFunction:
            name = tool_name
            arguments = encoded_arguments

        class FakeToolCall:
            id = f"provider-{tool_name}"
            function = FakeFunction()

        message.content = ""
        message.tool_calls = [FakeToolCall()]
    choice = FakeChoice()
    choice.message = message
    response = FakeResponse()
    response.choices = [choice]
    return response


def _provider_tool_names(kwargs: dict) -> set[str]:
    return {
        str(tool["function"]["name"])
        for tool in kwargs.get("tools", [])
        if tool.get("type") == "function"
    }


@pytest.mark.asyncio
async def test_update_session_rejects_target_change_until_active_turn_is_terminal(
    db_session: AsyncSession,
):
    await _workspace(db_session)
    service = AgentCoreService(db_session)
    local_target = {"type": "local"}
    remote_target = {
        "type": "remote_ssh",
        "connection_id": "conn-1",
    }
    session = await service.create_session(
        project_id=None,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        execution_target=local_target,
    )
    turn = await service.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Keep this turn on its original execution target.",
    )

    assert session.active_turn_id == str(turn.id)
    with pytest.raises(ConflictError):
        await service.update_session(
            session_id=str(session.id),
            workspace_id=DEFAULT_WORKSPACE_ID,
            user_id="dev",
            updates={"execution_target": remote_target},
        )

    session = await service.session_repo.get_fresh(str(session.id))
    assert session.session_metadata["execution_target"] == local_target

    await service.turn_repo.update_all(turn, status=AgentTurnStatus.COMPLETED)
    session = await service.session_repo.get_fresh(str(session.id))
    assert session.active_turn_id == str(turn.id)

    updated_session = await service.update_session(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        updates={"execution_target": remote_target},
    )

    assert updated_session.session_metadata["execution_target"] == remote_target


@pytest.mark.asyncio
async def test_active_turn_refreshes_target_before_next_tool_and_model_request(
    db_session: AsyncSession,
    db_engine,
    monkeypatch,
):
    first_request_started = asyncio.Event()
    release_first_response = asyncio.Event()
    request_tool_names: list[set[str]] = []
    model_calls = 0

    async def fake_completion(*args, **kwargs):
        del args
        nonlocal model_calls
        model_calls += 1
        request_tool_names.append(_provider_tool_names(kwargs))
        if model_calls == 1:
            first_request_started.set()
            await release_first_response.wait()
            return _completion(tool_name="plugins__list")
        if model_calls == 2:
            return _completion(
                tool_name="bash",
                arguments={
                    "command": f"{sys.executable} -c 'print(\"stale-local\")'",
                    "cwd": str(settings.bioinfoflow_home),
                },
            )
        return _completion()

    monkeypatch.setattr("app.services.agent_core.runtime.acompletion", fake_completion)
    await _workspace(db_session)
    await _seed_catalog_model(db_session, model_id="target-refresh-model")

    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=None,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        execution_target={"type": "local"},
    )
    turn = await service.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Continue safely if the execution target changes.",
    )

    run_task = asyncio.create_task(service.runtime.run_turn(str(turn.id)))
    await asyncio.wait_for(first_request_started.wait(), timeout=2)

    session_maker = async_sessionmaker(
        db_engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    async with session_maker() as independent_db:
        independent_service = AgentCoreService(independent_db)
        current_session = await independent_service.session_repo.get(str(session.id))
        await independent_service.session_repo.update_all(
            current_session,
            session_metadata=session_metadata_with_execution_target(
                current_session.session_metadata,
                {"type": "remote_ssh", "connection_id": "conn-1"},
            ),
        )

    release_first_response.set()
    completed_turn = await asyncio.wait_for(run_task, timeout=5)
    actions = await AgentActionRepository(db_session).list_for_turn(str(turn.id))

    assert "bash" in request_tool_names[0]
    assert "remote__exec" not in request_tool_names[0]
    observed = {
        "second_request_has_bash": "bash" in request_tool_names[1],
        "second_request_has_remote_exec": "remote__exec" in request_tool_names[1],
        "action_names": {action.name for action in actions},
        "turn_status": completed_turn.status,
        "error_code": completed_turn.error_code,
    }
    assert observed == {
        "second_request_has_bash": False,
        "second_request_has_remote_exec": True,
        "action_names": set(),
        "turn_status": AgentTurnStatus.FAILED,
        "error_code": "tool_not_exposed",
    }


@pytest.mark.asyncio
async def test_target_change_during_nonstream_response_commit_discards_stale_response(
    db_session: AsyncSession,
    db_engine,
    monkeypatch,
):
    assistant_append_started = asyncio.Event()
    release_assistant_append = asyncio.Event()
    requested_tool_names: list[set[str]] = []
    model_calls = 0

    async def fake_completion(*args, **kwargs):
        del args
        nonlocal model_calls
        model_calls += 1
        requested_tool_names.append(_provider_tool_names(kwargs))
        if model_calls == 1:
            response = _completion(tool_name="plugins__list")
            response.choices[0].message.content = "stale-local-response"
            return response
        response = _completion()
        response.choices[0].message.content = "fresh-remote-response"
        return response

    original_append = AgentEventLedger.append
    blocked_first_assistant_append = False

    async def blocking_append(ledger, **kwargs):
        nonlocal blocked_first_assistant_append
        if (
            not blocked_first_assistant_append
            and kwargs["type"]
            in {
                AgentEventType.ASSISTANT_TOOL_CALL_STARTED,
                AgentEventType.ASSISTANT_TOOL_CALL_COMPLETED,
                AgentEventType.ASSISTANT_TEXT_COMPLETED,
            }
        ):
            blocked_first_assistant_append = True
            assistant_append_started.set()
            await release_assistant_append.wait()
        return await original_append(ledger, **kwargs)

    monkeypatch.setattr("app.services.agent_core.runtime.acompletion", fake_completion)
    monkeypatch.setattr(AgentEventLedger, "append", blocking_append)
    await _workspace(db_session)
    await _seed_catalog_model(
        db_session,
        model_id="target-response-commit-model",
        supports_streaming=False,
    )

    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=None,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        execution_target={"type": "local"},
    )
    turn = await service.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Discard any response produced for a stale execution target.",
    )

    run_task = asyncio.create_task(service.runtime.run_turn(str(turn.id)))
    await asyncio.wait_for(assistant_append_started.wait(), timeout=2)

    session_maker = async_sessionmaker(
        db_engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    async with session_maker() as independent_db:
        independent_service = AgentCoreService(independent_db)
        current_session = await independent_service.session_repo.get(str(session.id))
        await independent_service.session_repo.update_all(
            current_session,
            session_metadata=session_metadata_with_execution_target(
                current_session.session_metadata,
                {"type": "remote_ssh", "connection_id": "conn-1"},
            ),
        )

    release_assistant_append.set()
    completed_turn = await asyncio.wait_for(run_task, timeout=5)

    async with session_maker() as inspect_db:
        events = await AgentEventRepository(inspect_db).list_for_turn(
            turn_id=str(turn.id)
        )
        messages = await AgentMessageRepository(inspect_db).list_for_session(
            str(session.id)
        )
        actions = await AgentActionRepository(inspect_db).list_for_turn(str(turn.id))

    stale_message_id = f"assistant:{turn.id}:1"
    stale_events = [
        event
        for event in events
        if (event.payload or {}).get("message_id") == stale_message_id
    ]
    assistant_parts = [
        message.content_parts for message in messages if message.role == "assistant"
    ]
    serialized_assistant_parts = json.dumps(assistant_parts, sort_keys=True)
    second_request_tools = (
        requested_tool_names[1] if len(requested_tool_names) > 1 else set()
    )

    assert {
        "model_calls": model_calls,
        "first_request_has_local_shell": "bash" in requested_tool_names[0],
        "first_request_has_remote_exec": "remote__exec" in requested_tool_names[0],
        "second_request_has_local_shell": "bash" in second_request_tools,
        "second_request_has_remote_exec": "remote__exec" in second_request_tools,
        "turn_status": completed_turn.status,
        "turn_final_text": completed_turn.final_text,
        "turn_error_code": completed_turn.error_code,
        "stale_event_types": [event.type for event in stale_events],
        "stale_text_persisted": "stale-local-response"
        in serialized_assistant_parts,
        "fresh_text_persisted": "fresh-remote-response"
        in serialized_assistant_parts,
        "action_names": {action.name for action in actions},
    } == {
        "model_calls": 2,
        "first_request_has_local_shell": True,
        "first_request_has_remote_exec": False,
        "second_request_has_local_shell": False,
        "second_request_has_remote_exec": True,
        "turn_status": AgentTurnStatus.COMPLETED,
        "turn_final_text": "fresh-remote-response",
        "turn_error_code": None,
        "stale_event_types": [],
        "stale_text_persisted": False,
        "fresh_text_persisted": True,
        "action_names": set(),
    }


@pytest.mark.asyncio
async def test_resume_completed_action_does_not_skip_current_pending_observation(
    db_session: AsyncSession,
    monkeypatch,
):
    model_calls = 0

    async def fake_completion(*args, **kwargs):
        del args, kwargs
        nonlocal model_calls
        model_calls += 1
        if model_calls == 1:
            return _completion(tool_name="plugins__list")
        if model_calls == 2:
            return _completion(
                tool_name="bash",
                arguments={
                    "command": f"{sys.executable} -c 'print(\"pending\")'",
                    "cwd": str(settings.bioinfoflow_home),
                },
            )
        return _completion()

    monkeypatch.setattr("app.services.agent_core.runtime.acompletion", fake_completion)
    await _workspace(db_session)
    await _seed_catalog_model(db_session, model_id="stale-resume-model")

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
        input_text="List plugins, then request approval for a command.",
    )

    waiting_turn = await service.runtime.run_turn(str(turn.id))
    actions = await AgentActionRepository(db_session).list_for_turn(str(turn.id))
    completed_action = next(
        action for action in actions if action.status == AgentActionStatus.COMPLETED
    )
    pending_action = next(
        action
        for action in actions
        if action.status == AgentActionStatus.WAITING_DECISION
    )
    pending_progress = dict(waiting_turn.loop_state["progress"]["pending_observation"])

    with pytest.raises(ConflictError, match="cannot resume from status"):
        await service.resume_action(
            action_id=str(completed_action.id),
            workspace_id=DEFAULT_WORKSPACE_ID,
            user_id="dev",
        )
    stale_resume_result = await service.runtime.resume_turn_after_action(
        str(completed_action.id)
    )
    fresh_turn = await AgentTurnRepository(db_session).get_fresh(str(turn.id))
    fresh_actions = await AgentActionRepository(db_session).list_for_turn(str(turn.id))
    fresh_pending = next(action for action in fresh_actions if action.id == pending_action.id)
    fresh_progress = (fresh_turn.loop_state or {}).get("progress") or {}

    assert {
        "resume_status": stale_resume_result.status,
        "turn_status": fresh_turn.status,
        "model_calls": model_calls,
        "pending_action_status": fresh_pending.status,
        "pending_action_requires_resume": fresh_pending.requires_resume,
        "pending_observation": fresh_progress.get("pending_observation"),
    } == {
        "resume_status": AgentTurnStatus.WAITING_APPROVAL,
        "turn_status": AgentTurnStatus.WAITING_APPROVAL,
        "model_calls": 2,
        "pending_action_status": AgentActionStatus.WAITING_DECISION,
        "pending_action_requires_resume": True,
        "pending_observation": pending_progress,
    }
