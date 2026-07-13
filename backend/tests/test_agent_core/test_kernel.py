from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import pytest

from app.models.llm import LlmModel, LlmProvider
from app.models.project import Project
from app.models.workspace import Workspace
from app.services.agent_core import AgentCoreService
from app.services.model_runtime.gateway import ModelGateway
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
        assert network_access == "unrestricted"
        return await self.completion(**request)


def _install_fake_completion(monkeypatch, completion) -> None:
    gateway = ModelGateway(backend=_FakeBackend(completion))
    monkeypatch.setattr(
        "app.services.agent_core.runtime.ModelGateway",
        lambda: gateway,
    )


async def _seed_catalog_model(db_session, *, model_id: str = "kernel-model") -> LlmModel:
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

    _install_fake_completion(monkeypatch, fake_completion)

    model = await _seed_catalog_model(db_session)
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
    turn = await service.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Summarize this run.",
    )
    turn = await service.runtime.run_turn(str(turn.id))

    assert turn.status == "completed"
    assert turn.final_text

    events = await service.list_events_for_turn(
        turn_id=str(turn.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )
    assert turn.model_profile_snapshot["resolved_model_selection"] == {
        "provider": "openai_compatible",
        "model": model.model_id,
    }
    assert turn.model_profile_snapshot["resolved_model_source"] == "catalog_default"
    assert [event.seq for event in events] == [1, 2, 3, 4, 5]
    assert [event.type for event in events] == [
        "turn.created",
        "turn.started",
        "model.selected",
        "assistant.text.completed",
        "turn.completed",
    ]


@pytest.mark.asyncio
async def test_agent_core_no_tool_runtime_persists_visible_failure(db_session, monkeypatch):
    async def failing_completion(*args, **kwargs):
        raise RuntimeError("Provider timed out")

    _install_fake_completion(monkeypatch, failing_completion)

    await _seed_catalog_model(db_session, model_id="failing-kernel-model")
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
    turn = await service.create_turn_record(
        session_id=str(session.id),
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        input_text="Summarize this run.",
    )
    turn = await service.runtime.run_turn(str(turn.id))

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
