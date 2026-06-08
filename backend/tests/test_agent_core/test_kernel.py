from __future__ import annotations

import pytest

from app.models.project import Project
from app.models.workspace import Workspace
from app.services.agent_core import AgentCoreService
from app.workspace import DEFAULT_WORKSPACE_ID


@pytest.mark.asyncio
async def test_agent_core_no_tool_runtime_writes_ordered_events(db_session, monkeypatch):
    async def fake_completion(*args, **kwargs):
        class FakeUsage:
            def model_dump(self):
                return {"prompt_tokens": 8, "completion_tokens": 12, "total_tokens": 20}

        class FakeMessage:
            content = "Mocked model reply."

        class FakeChoice:
            message = FakeMessage()

        class FakeResponse:
            choices = [FakeChoice()]
            usage = FakeUsage()

        return FakeResponse()

    monkeypatch.setattr("app.services.agent_core.runtime.acompletion", fake_completion)

    workspace = Workspace(id=DEFAULT_WORKSPACE_ID, name="Team", slug="team")
    project = Project(
        name="Kernel Project",
        description="AgentCore kernel test",
        user_id="dev",
        created_by_user_id="dev",
        workspace_id=DEFAULT_WORKSPACE_ID,
    )
    db_session.add_all([workspace, project])
    await db_session.commit()
    await db_session.refresh(project)

    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=str(project.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        title="Kernel",
    )
    turn = await service.create_turn(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Summarize this run.",
    )

    assert turn.status == "completed"
    assert turn.final_text

    events = await service.list_events_for_turn(
        turn_id=str(turn.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )
    assert turn.model_profile_snapshot["resolved_model_selection"] == {
        "provider": "anthropic",
        "model": "claude-sonnet-4-6",
    }
    assert turn.model_profile_snapshot["resolved_model_source"] == "deployment_default"
    assert [event.seq for event in events] == [1, 2, 3, 4, 5, 6]
    assert [event.type for event in events] == [
        "turn.created",
        "turn.started",
        "model.selected",
        "assistant.thinking.summary",
        "assistant.text.completed",
        "turn.completed",
    ]


@pytest.mark.asyncio
async def test_agent_core_no_tool_runtime_persists_visible_failure(db_session, monkeypatch):
    async def failing_completion(*args, **kwargs):
        raise RuntimeError("Provider timed out")

    monkeypatch.setattr("app.services.agent_core.runtime.acompletion", failing_completion)

    workspace = Workspace(id=DEFAULT_WORKSPACE_ID, name="Team", slug="team")
    project = Project(
        name="Kernel Project",
        description="AgentCore kernel test",
        user_id="dev",
        created_by_user_id="dev",
        workspace_id=DEFAULT_WORKSPACE_ID,
    )
    db_session.add_all([workspace, project])
    await db_session.commit()
    await db_session.refresh(project)

    service = AgentCoreService(db_session)
    session = await service.create_session(
        project_id=str(project.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        title="Kernel",
    )
    turn = await service.create_turn(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Summarize this run.",
    )

    assert turn.status == "failed"
    assert turn.final_text is None
    assert turn.error_code == "model_request_failed"
    assert turn.error_message == "Provider timed out"

    events = await service.list_events_for_turn(
        turn_id=str(turn.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )
    assert events[-1].type == "turn.failed"
    assert events[-1].payload == {
        "error_message": "Provider timed out",
        "error_code": "model_request_failed",
    }
