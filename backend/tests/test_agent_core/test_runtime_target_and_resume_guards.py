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
from app.repositories.agent_core_repo import AgentActionRepository, AgentTurnRepository
from app.services.agent_core import AgentCoreService
from app.utils.exceptions import ConflictError
from app.workspace import DEFAULT_WORKSPACE_ID


async def _workspace(db_session: AsyncSession) -> Workspace:
    workspace = Workspace(id=DEFAULT_WORKSPACE_ID, name="Team", slug="team")
    db_session.add(workspace)
    await db_session.commit()
    return workspace


async def _seed_catalog_model(db_session: AsyncSession, *, model_id: str) -> LlmModel:
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
        await AgentCoreService(independent_db).update_session(
            session_id=str(session.id),
            workspace_id=DEFAULT_WORKSPACE_ID,
            user_id="dev",
            updates={
                "execution_target": {
                    "type": "remote_ssh",
                    "connection_id": "conn-1",
                }
            },
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
