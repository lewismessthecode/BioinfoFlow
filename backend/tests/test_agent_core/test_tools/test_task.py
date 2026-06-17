from __future__ import annotations

import pytest

from app.models.llm import LlmModel, LlmProvider
from app.models.workspace import Workspace
from app.services.agent_core import AgentCoreService
from app.services.agent_core.tools.specs import AgentToolContext
from app.services.agent_core.tools.subagents import TaskTool
from app.workspace import DEFAULT_WORKSPACE_ID


async def _seed_catalog_model(db_session) -> None:
    provider = LlmProvider(
        name="task provider",
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
        model_id="task-model",
        display_name="task-model",
        supports_tools=True,
        supports_streaming=True,
    )
    db_session.add(model)
    await db_session.commit()


@pytest.mark.asyncio
async def test_task_tool_runs_read_only_worker_subrun(db_session, monkeypatch):
    async def fake_completion(*args, **kwargs):
        class FakeMessage:
            content = "Worker findings for the parent agent."
            tool_calls = None

        class FakeChoice:
            message = FakeMessage()

        class FakeResponse:
            choices = [FakeChoice()]
            usage = None

        return FakeResponse()

    monkeypatch.setattr("app.services.agent_core.runtime.acompletion", fake_completion)
    workspace = Workspace(id=DEFAULT_WORKSPACE_ID, name="Team", slug="team")
    db_session.add(workspace)
    await db_session.commit()
    await _seed_catalog_model(db_session)

    core = AgentCoreService(db_session)
    parent_session = await core.create_session(
        project_id=None, workspace_id=DEFAULT_WORKSPACE_ID, user_id="dev"
    )
    parent_turn = await core.create_turn_record(
        session_id=str(parent_session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Parent turn.",
    )

    result = await TaskTool().run(
        {"objective": "Summarize the repo layout", "description": "Focus on the backend."},
        AgentToolContext(
            db=db_session,
            workspace_id=DEFAULT_WORKSPACE_ID,
            user_id="dev",
            session_id=str(parent_session.id),
            turn_id=str(parent_turn.id),
        ),
    )

    assert result["status"] == "completed"
    assert result["final_text"] == "Worker findings for the parent agent."
    assert result["child_session_id"] and result["child_turn_id"]

    child_session = await core.session_repo.get(result["child_session_id"])
    assert child_session is not None
    assert child_session.role_profile == "worker"
    assert child_session.lineage == {
        "parent_session_id": str(parent_session.id),
        "parent_turn_id": str(parent_turn.id),
    }
