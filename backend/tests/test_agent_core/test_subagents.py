from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import pytest

from app.models.llm import LlmModel, LlmProvider
from app.models.workspace import Workspace
from app.repositories.agent_user_settings_repo import AgentUserSettingsRepository
from app.services.agent_core import AgentCoreService
from app.services.agent_core.subagents import ReadOnlySubagentRunner
from app.services.agent_core.tools import build_default_tool_registry
from app.services.agent_core.tools.specs import AgentToolContext
from app.services.agent_core.tools.subagents import SubagentAnalyzeTool
from app.services.agent_core.tools.toolsets import ToolsetExposure
from app.services.model_runtime.gateway import ModelGateway
from app.utils.exceptions import PermissionDeniedError
from app.workspace import DEFAULT_WORKSPACE_ID


class _FakeBackend:
    def __init__(self, completion: Callable[..., Awaitable[Any]]) -> None:
        self.completion = completion

    async def invoke(
        self,
        wire_protocol: str,
        request: dict[str, Any],
        *,
        network_access: str = "unrestricted",
    ) -> Any:
        assert wire_protocol == "chat_completions"
        assert network_access == "public_only"
        return await self.completion(**request)


def _install_fake_completion(monkeypatch, completion) -> None:
    gateway = ModelGateway(backend=_FakeBackend(completion))
    monkeypatch.setattr(
        "app.services.agent_core.runtime.ModelGateway",
        lambda: gateway,
    )


async def _workspace(db_session) -> Workspace:
    workspace = Workspace(id=DEFAULT_WORKSPACE_ID, name="Team", slug="team")
    db_session.add(workspace)
    await db_session.commit()
    return workspace


async def _seed_catalog_model(db_session, *, model_id: str = "subagent-model") -> LlmModel:
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
async def test_read_only_subagent_accepts_read_only_tools():
    result = await ReadOnlySubagentRunner(build_default_tool_registry()).analyze(
        task="Summarize available project context.",
        context={"project_id": "project-1"},
        allowed_tools=["projects.list", "skills.list"],
    )

    assert result["mode"] == "read_only"
    assert result["task"] == "Summarize available project context."
    assert result["allowed_tools"] == ["projects.list", "skills.list"]
    assert result["write_handoff_required"] is True


@pytest.mark.asyncio
async def test_read_only_subagent_rejects_write_capable_tools():
    with pytest.raises(PermissionDeniedError, match="write-capable"):
        await ReadOnlySubagentRunner(build_default_tool_registry()).analyze(
            task="Remember the reference genome.",
            context={"project_id": "project-1"},
            allowed_tools=["memory.propose"],
        )


@pytest.mark.asyncio
async def test_read_only_subagent_can_run_delegated_child_turn(db_session, monkeypatch):
    async def fake_completion(*args, **kwargs):
        class FakeMessage:
            content = "Delegated answer from child turn."
            tool_calls = None

        class FakeChoice:
            message = FakeMessage()

        class FakeResponse:
            choices = [FakeChoice()]
            usage = None

        return FakeResponse()

    _install_fake_completion(monkeypatch, fake_completion)
    await _workspace(db_session)
    await _seed_catalog_model(db_session)

    service = AgentCoreService(db_session)
    parent_session = await service.create_session(
        project_id=None,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )
    parent_session = await service.session_repo.update_all(
        parent_session,
        prompt_snapshot={"id": "frozen-parent", "content": "Frozen parent prompt"},
    )
    parent_turn = await service.create_turn_record(
        session_id=str(parent_session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Parent turn.",
    )

    result = await ReadOnlySubagentRunner(
        build_default_tool_registry(),
        db=db_session,
    ).analyze(
        task="Summarize child context.",
        context={
            "workspace_id": DEFAULT_WORKSPACE_ID,
            "user_id": "dev",
            "session_id": str(parent_session.id),
            "turn_id": str(parent_turn.id),
            "project_id": None,
        },
        allowed_tools=["projects.list", "skills.list"],
    )

    assert result["mode"] == "delegated_read_only"
    assert result["status"] == "completed"
    assert result["final_text"] == "Delegated answer from child turn."
    assert result["child_session_id"]
    assert result["child_turn_id"]

    child_session = await service.session_repo.get(result["child_session_id"])
    assert child_session is not None
    assert child_session.lineage == {
        "parent_session_id": str(parent_session.id),
        "parent_turn_id": str(parent_turn.id),
    }
    assert child_session.toolset_policy == {
        "name": "default",
        "allowed_tools": ["projects.list", "skills.list"],
    }
    assert child_session.prompt_snapshot == parent_session.prompt_snapshot
    assert ToolsetExposure(build_default_tool_registry()).exposed_names(
        policy=child_session.toolset_policy,
        role="worker",
    ) == {"projects.list", "skills.list"}


@pytest.mark.asyncio
async def test_subagent_analyze_tool_inherits_frozen_parent_prompt_snapshot(
    db_session, monkeypatch
):
    async def fake_completion(*args, **kwargs):
        class FakeMessage:
            content = "Tool child answer."
            tool_calls = None

        class FakeChoice:
            message = FakeMessage()

        class FakeResponse:
            choices = [FakeChoice()]
            usage = None

        return FakeResponse()

    _install_fake_completion(monkeypatch, fake_completion)
    await _workspace(db_session)
    await _seed_catalog_model(db_session, model_id="subagent-tool-model")

    service = AgentCoreService(db_session)
    parent_session = await service.create_session(
        project_id=None,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )
    frozen_snapshot = {
        "id": "frozen-parent",
        "content": "Frozen parent prompt for subagent.analyze",
    }
    parent_session = await service.session_repo.update_all(
        parent_session,
        prompt_snapshot=frozen_snapshot,
    )
    await AgentUserSettingsRepository(db_session).upsert(
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        custom_instructions="Current settings must not replace the frozen prompt.",
    )
    parent_turn = await service.create_turn_record(
        session_id=str(parent_session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Parent turn.",
    )

    result = await SubagentAnalyzeTool().run(
        {"task": "Inspect the backend", "allowed_tools": []},
        AgentToolContext(
            db=db_session,
            workspace_id=DEFAULT_WORKSPACE_ID,
            user_id="dev",
            session_id=str(parent_session.id),
            turn_id=str(parent_turn.id),
        ),
    )

    child_session = await service.session_repo.get(result["child_session_id"])
    assert child_session is not None
    assert child_session.prompt_snapshot == frozen_snapshot
