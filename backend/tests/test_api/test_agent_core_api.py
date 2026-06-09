from __future__ import annotations

import asyncio

import pytest

from app.api.deps import get_current_user
from app.auth.session import AuthUser
from app.models.llm import LlmModel, LlmProvider
from app.workspace import DEFAULT_WORKSPACE_ID


def _auth_user(
    *,
    user_id: str = "user-1",
    workspace_id: str = DEFAULT_WORKSPACE_ID,
    role: str = "owner",
) -> AuthUser:
    return AuthUser(
        id=user_id,
        name=f"User {user_id}",
        email=f"{user_id}@bioinfoflow.test",
        role=role,
        workspace_id=workspace_id,
    )


async def _create_project(async_client) -> str:
    resp = await async_client.post(
        "/api/v1/projects",
        json={
            "name": "AgentCore API Project",
            "description": "Contract test project",
        },
    )
    assert resp.status_code == 201
    return resp.json()["data"]["id"]


async def _wait_for_turn(async_client, turn_id: str) -> dict:
    for _ in range(40):
        resp = await async_client.get(f"/api/v1/agent/turns/{turn_id}")
        assert resp.status_code == 200
        turn = resp.json()["data"]
        if turn["status"] in {"completed", "failed", "cancelled", "waiting_approval"}:
            return turn
        await asyncio.sleep(0.05)
    raise AssertionError("agent turn did not reach a terminal or waiting state")


def _event_types(events: list[dict]) -> list[str]:
    return [item["type"] for item in events]


async def _create_llm_model(async_client) -> dict:
    provider_response = await async_client.post(
        "/api/v1/llm/providers",
        json={
            "name": "Agent Test Gateway",
            "kind": "openai_compatible",
            "base_url": "https://models.internal.example/v1",
        },
    )
    assert provider_response.status_code == 201
    provider = provider_response.json()["data"]

    model_response = await async_client.post(
        "/api/v1/llm/models",
        json={
            "provider_id": provider["id"],
            "model_id": "agent-test-model",
            "display_name": "Agent Test Model",
            "supports_tools": True,
            "supports_streaming": True,
        },
    )
    assert model_response.status_code == 201
    return model_response.json()["data"]


async def _create_llm_profile(
    async_client,
    *,
    name: str,
    primary_model_id: str,
    prefer_streaming: bool | None = None,
    allow_thinking: bool | None = None,
    allow_tools: bool | None = None,
) -> dict:
    payload: dict[str, object] = {
        "name": name,
        "task_type": "agent_core",
        "primary_model_id": primary_model_id,
    }
    if prefer_streaming is not None:
        payload["prefer_streaming"] = prefer_streaming
    if allow_thinking is not None:
        payload["allow_thinking"] = allow_thinking
    if allow_tools is not None:
        payload["allow_tools"] = allow_tools
    response = await async_client.post("/api/v1/llm/model-profiles", json=payload)
    assert response.status_code == 201
    return response.json()["data"]


async def _create_scoped_llm_model(
    db_session,
    *,
    provider_user_id: str,
    model_name: str,
) -> LlmModel:
    provider = LlmProvider(
        name=f"{model_name} provider",
        kind="openai_compatible",
        base_url="https://models.internal.example/v1",
        scope="user",
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id=provider_user_id,
        enabled=True,
    )
    db_session.add(provider)
    await db_session.commit()
    await db_session.refresh(provider)
    model = LlmModel(
        provider_id=str(provider.id),
        model_id=model_name,
        display_name=model_name,
        supports_tools=True,
        supports_streaming=True,
    )
    db_session.add(model)
    await db_session.commit()
    await db_session.refresh(model)
    return model


@pytest.mark.asyncio
async def test_agent_core_session_turn_event_and_artifact_contract(async_client, monkeypatch):
    async def fake_completion(*args, **kwargs):
        class FakeUsage:
            def model_dump(self):
                return {"prompt_tokens": 6, "completion_tokens": 10, "total_tokens": 16}

        class FakeMessage:
            content = "Mocked model reply."

        class FakeChoice:
            message = FakeMessage()

        class FakeResponse:
            choices = [FakeChoice()]
            usage = FakeUsage()

        return FakeResponse()

    monkeypatch.setattr("app.services.agent_core.runtime.acompletion", fake_completion)

    project_id = await _create_project(async_client)

    create_session = await async_client.post(
        "/api/v1/agent/sessions",
        json={
            "project_id": project_id,
            "title": "WGS triage",
            "permission_mode": "guarded_auto",
            "automation_mode": "assisted",
            "model_selection": {
                "provider": "anthropic",
                "model": "claude-sonnet-4-6",
            },
            "metadata": {"batch": "b001"},
        },
    )
    assert create_session.status_code == 201
    session = create_session.json()["data"]
    assert session["title"] == "WGS triage"
    assert session["metadata"] == {
        "batch": "b001",
        "model_selection": {
            "provider": "anthropic",
            "model": "claude-sonnet-4-6",
        },
    }
    assert session["model_selection"] == {
        "provider": "anthropic",
        "model": "claude-sonnet-4-6",
    }
    assert session["permission_mode"] == "guarded_auto"

    list_sessions = await async_client.get("/api/v1/agent/sessions")
    assert list_sessions.status_code == 200
    assert list_sessions.json()["data"][0]["id"] == session["id"]

    create_turn = await async_client.post(
        f"/api/v1/agent/sessions/{session['id']}/turns",
        json={
            "input_text": "Check the FASTQ files before running alignment.",
            "input_parts": [{"type": "text", "text": "preflight"}],
        },
    )
    assert create_turn.status_code == 202
    turn = create_turn.json()["data"]
    assert turn["session_id"] == session["id"]
    assert turn["status"] == "queued"

    turn = await _wait_for_turn(async_client, turn["id"])
    assert turn["status"] == "completed"
    assert turn["final_text"] == "Mocked model reply."
    assert turn["model_selection"] == {
        "provider": "anthropic",
        "model": "claude-sonnet-4-6",
    }
    assert turn["model_profile_snapshot"]["resolved_model_selection"] == {
        "provider": "anthropic",
        "model": "claude-sonnet-4-6",
    }
    assert turn["model_profile_snapshot"]["resolved_model_source"] == "session"

    list_turns = await async_client.get(
        f"/api/v1/agent/sessions/{session['id']}/turns"
    )
    assert list_turns.status_code == 200
    assert [item["id"] for item in list_turns.json()["data"]] == [turn["id"]]

    events = await async_client.get(f"/api/v1/agent/turns/{turn['id']}/events")
    assert events.status_code == 200
    assert [item["type"] for item in events.json()["data"]] == [
        "turn.created",
        "turn.started",
        "model.selected",
        "assistant.text.completed",
        "turn.completed",
    ]

    stream_lines: list[str] = []
    async with async_client.stream(
        "GET",
        f"/api/v1/agent/sessions/{session['id']}/stream?follow=false",
    ) as stream:
        assert stream.status_code == 200
        async for line in stream.aiter_lines():
            stream_lines.append(line)
            if line == "event: ready":
                break
    assert "event: turn.created" in stream_lines
    assert "event: ready" in stream_lines

    artifacts = await async_client.get(
        f"/api/v1/agent/sessions/{session['id']}/artifacts"
    )
    assert artifacts.status_code == 200
    assert artifacts.json()["data"] == []

    cancel = await async_client.post(f"/api/v1/agent/turns/{turn['id']}/cancel")
    assert cancel.status_code == 200
    assert cancel.json()["data"]["status"] == "cancelled"


@pytest.mark.asyncio
async def test_agent_core_accepts_catalog_model_selection(async_client, monkeypatch):
    async def fake_completion(*args, **kwargs):
        class FakeMessage:
            content = "Catalog model reply."

        class FakeChoice:
            message = FakeMessage()

        class FakeResponse:
            choices = [FakeChoice()]
            usage = None

        return FakeResponse()

    monkeypatch.setattr("app.services.agent_core.runtime.acompletion", fake_completion)

    project_id = await _create_project(async_client)
    model = await _create_llm_model(async_client)
    create_session = await async_client.post(
        "/api/v1/agent/sessions",
        json={
            "project_id": project_id,
            "title": "Catalog-routed session",
            "model_selection": {"model_id": model["id"]},
        },
    )
    assert create_session.status_code == 201
    session = create_session.json()["data"]
    assert session["model_selection"]["model_id"] == model["id"]

    create_turn = await async_client.post(
        f"/api/v1/agent/sessions/{session['id']}/turns",
        json={
            "input_text": "Use the catalog model.",
            "model_selection": {"model_id": model["id"]},
        },
    )
    assert create_turn.status_code == 202
    turn = await _wait_for_turn(async_client, create_turn.json()["data"]["id"])

    assert turn["status"] == "completed"
    assert turn["final_text"] == "Catalog model reply."
    assert turn["model_selection"]["model_id"] == model["id"]
    assert turn["model_profile_snapshot"]["requested_model_selection"] == {
        "model_id": model["id"],
    }
    assert turn["model_profile_snapshot"]["resolved_model_id"] == model["id"]
    assert turn["model_profile_snapshot"]["resolved_model_selection"] == {
        "provider": "openai_compatible",
        "model": "agent-test-model",
    }


@pytest.mark.asyncio
async def test_agent_core_streams_text_and_reasoning_events(async_client, monkeypatch):
    completion_kwargs: list[dict] = []

    async def fake_completion(*args, **kwargs):
        completion_kwargs.append(kwargs)

        async def stream():
            yield {
                "choices": [
                    {
                        "delta": {
                            "reasoning_content": "Inspecting the workspace context.",
                        }
                    }
                ]
            }
            yield {"choices": [{"delta": {"content": "Streaming reply "}}]}
            yield {
                "choices": [{"delta": {"content": "completed."}}],
                "usage": {
                    "prompt_tokens": 7,
                    "completion_tokens": 4,
                    "total_tokens": 11,
                },
            }

        return stream()

    monkeypatch.setattr("app.services.agent_core.runtime.acompletion", fake_completion)

    project_id = await _create_project(async_client)
    provider_response = await async_client.post(
        "/api/v1/llm/providers",
        json={
            "name": "Streaming Test Gateway",
            "kind": "openai_compatible",
            "base_url": "https://models.internal.example/v1",
        },
    )
    assert provider_response.status_code == 201
    provider = provider_response.json()["data"]
    model_response = await async_client.post(
        "/api/v1/llm/models",
        json={
            "provider_id": provider["id"],
            "model_id": "streaming-reasoner",
            "display_name": "Streaming Reasoner",
            "supports_streaming": True,
            "supports_reasoning": True,
            "supports_tools": False,
        },
    )
    assert model_response.status_code == 201
    model = model_response.json()["data"]

    create_session = await async_client.post(
        "/api/v1/agent/sessions",
        json={
            "project_id": project_id,
            "title": "Streaming session",
            "model_selection": {"model_id": model["id"]},
        },
    )
    assert create_session.status_code == 201
    session = create_session.json()["data"]

    create_turn = await async_client.post(
        f"/api/v1/agent/sessions/{session['id']}/turns",
        json={"input_text": "Explain what you are doing."},
    )
    assert create_turn.status_code == 202
    turn = await _wait_for_turn(async_client, create_turn.json()["data"]["id"])

    assert turn["status"] == "completed"
    assert turn["final_text"] == "Streaming reply completed."
    assert completion_kwargs[0]["stream"] is True

    events_response = await async_client.get(f"/api/v1/agent/turns/{turn['id']}/events")
    assert events_response.status_code == 200
    events = events_response.json()["data"]
    assert _event_types(events) == [
        "turn.created",
        "turn.started",
        "model.selected",
        "assistant.thinking.delta",
        "assistant.thinking.completed",
        "assistant.text.delta",
        "assistant.text.delta",
        "assistant.text.completed",
        "turn.completed",
    ]
    assert events[3]["payload"]["delta"] == "Inspecting the workspace context."
    assert events[4]["payload"]["content"] == "Inspecting the workspace context."
    assert events[5]["payload"]["delta"] == "Streaming reply "
    assert events[7]["payload"]["text"] == "Streaming reply completed."


@pytest.mark.asyncio
async def test_agent_core_emits_tool_call_lifecycle_events(async_client, monkeypatch):
    completion_calls: list[dict] = []

    async def fake_completion(*args, **kwargs):
        completion_calls.append(kwargs)

        async def tool_call_stream():
            yield {
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "id": "call_projects",
                                    "function": {
                                        "name": "projects__list",
                                        "arguments": '{"limit":',
                                    },
                                }
                            ]
                        }
                    }
                ]
            }
            yield {
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "function": {
                                        "arguments": " 1}",
                                    },
                                }
                            ]
                        }
                    }
                ]
            }

        async def final_text_stream():
            yield {"choices": [{"delta": {"content": "Projects checked."}}]}

        if len(completion_calls) == 1:
            return tool_call_stream()
        return final_text_stream()

    monkeypatch.setattr("app.services.agent_core.runtime.acompletion", fake_completion)

    project_id = await _create_project(async_client)
    model = await _create_llm_model(async_client)
    create_session = await async_client.post(
        "/api/v1/agent/sessions",
        json={
            "project_id": project_id,
            "title": "Tool stream session",
            "model_selection": {"model_id": model["id"]},
        },
    )
    assert create_session.status_code == 201
    session = create_session.json()["data"]

    create_turn = await async_client.post(
        f"/api/v1/agent/sessions/{session['id']}/turns",
        json={"input_text": "List my projects."},
    )
    assert create_turn.status_code == 202
    turn = await _wait_for_turn(async_client, create_turn.json()["data"]["id"])

    assert turn["status"] == "completed"
    assert turn["final_text"] == "Projects checked."
    assert completion_calls[0]["stream"] is True

    events_response = await async_client.get(f"/api/v1/agent/turns/{turn['id']}/events")
    assert events_response.status_code == 200
    events = events_response.json()["data"]
    event_types = _event_types(events)
    assert "assistant.tool_call.started" in event_types
    assert "assistant.tool_call.delta" in event_types
    assert "assistant.tool_call.completed" in event_types
    assert "action.requested" in event_types
    assert "action.started" in event_types
    assert "action.completed" in event_types
    tool_completed = next(
        item for item in events if item["type"] == "assistant.tool_call.completed"
    )
    assert tool_completed["payload"]["call_id"] == "call_projects"
    assert tool_completed["payload"]["name"] == "projects__list"
    assert tool_completed["payload"]["arguments"] == {"limit": 1}


@pytest.mark.asyncio
async def test_agent_core_ollama_catalog_selection_uses_root_api_base(
    async_client,
    monkeypatch,
):
    completion_kwargs: dict = {}

    async def fake_completion(*args, **kwargs):
        completion_kwargs.update(kwargs)

        class FakeMessage:
            content = "Ollama model reply."

        class FakeChoice:
            message = FakeMessage()

        class FakeResponse:
            choices = [FakeChoice()]
            usage = None

        return FakeResponse()

    monkeypatch.setattr("app.services.agent_core.runtime.acompletion", fake_completion)

    project_id = await _create_project(async_client)
    provider_response = await async_client.post(
        "/api/v1/llm/providers",
        json={
            "name": "Local Ollama",
            "kind": "ollama",
            "base_url": "http://localhost:11434",
        },
    )
    assert provider_response.status_code == 201
    provider = provider_response.json()["data"]
    credential_response = await async_client.put(
        f"/api/v1/llm/providers/{provider['id']}/credential",
        json={"source": "none"},
    )
    assert credential_response.status_code == 200
    model_response = await async_client.post(
        "/api/v1/llm/models",
        json={
            "provider_id": provider["id"],
            "model_id": "deepseek-r1:latest",
            "display_name": "DeepSeek R1",
            "supports_streaming": True,
            "supports_reasoning": True,
        },
    )
    assert model_response.status_code == 201
    model = model_response.json()["data"]

    create_session = await async_client.post(
        "/api/v1/agent/sessions",
        json={
            "project_id": project_id,
            "title": "Ollama-routed session",
            "model_selection": {"model_id": model["id"]},
        },
    )
    assert create_session.status_code == 201
    session = create_session.json()["data"]

    create_turn = await async_client.post(
        f"/api/v1/agent/sessions/{session['id']}/turns",
        json={"input_text": "Use local DeepSeek."},
    )
    assert create_turn.status_code == 202
    turn = await _wait_for_turn(async_client, create_turn.json()["data"]["id"])

    assert turn["status"] == "completed"
    assert completion_kwargs["model"] == "ollama_chat/deepseek-r1:latest"
    assert completion_kwargs["api_base"] == "http://127.0.0.1:11434"
    assert "api_key" not in completion_kwargs
    assert "tools" not in completion_kwargs


@pytest.mark.asyncio
async def test_agent_core_profile_strategy_can_disable_streaming_thinking_and_tools(
    async_client,
    monkeypatch,
):
    completion_kwargs: dict = {}

    async def fake_completion(*args, **kwargs):
        completion_kwargs.update(kwargs)

        class FakeMessage:
            content = "Profile strategy reply."

        class FakeChoice:
            message = FakeMessage()

        class FakeResponse:
            choices = [FakeChoice()]
            usage = None

        return FakeResponse()

    monkeypatch.setattr("app.services.agent_core.runtime.acompletion", fake_completion)

    project_id = await _create_project(async_client)
    provider_response = await async_client.post(
        "/api/v1/llm/providers",
        json={
            "name": "Profile Test Gateway",
            "kind": "openai_compatible",
            "base_url": "https://models.internal.example/v1",
        },
    )
    assert provider_response.status_code == 201
    provider = provider_response.json()["data"]
    model_response = await async_client.post(
        "/api/v1/llm/models",
        json={
            "provider_id": provider["id"],
            "model_id": "profile-strategy-model",
            "display_name": "Profile Strategy Model",
            "supports_streaming": True,
            "supports_reasoning": True,
            "supports_tools": True,
        },
    )
    assert model_response.status_code == 201
    model = model_response.json()["data"]
    profile = await _create_llm_profile(
        async_client,
        name="No-stream strategy",
        primary_model_id=model["id"],
        prefer_streaming=False,
        allow_thinking=False,
        allow_tools=False,
    )

    create_session = await async_client.post(
        "/api/v1/agent/sessions",
        json={
            "project_id": project_id,
            "title": "Profile strategy session",
            "model_selection": {"profile_id": profile["id"]},
        },
    )
    assert create_session.status_code == 201
    session = create_session.json()["data"]

    create_turn = await async_client.post(
        f"/api/v1/agent/sessions/{session['id']}/turns",
        json={"input_text": "Apply the profile strategy."},
    )
    assert create_turn.status_code == 202
    turn = await _wait_for_turn(async_client, create_turn.json()["data"]["id"])

    assert turn["status"] == "completed"
    assert turn["final_text"] == "Profile strategy reply."
    assert "stream" not in completion_kwargs or completion_kwargs["stream"] is False
    assert "tools" not in completion_kwargs
    assert turn["model_profile_snapshot"]["resolved_profile_id"] == profile["id"]
    strategy = turn["model_profile_snapshot"]["resolved_runtime_strategy"]
    assert strategy["allow_thinking"] is False
    assert strategy["allow_tools"] is False
    assert strategy["use_streaming"] is False

    events_response = await async_client.get(f"/api/v1/agent/turns/{turn['id']}/events")
    assert events_response.status_code == 200
    event_types = _event_types(events_response.json()["data"])
    assert "assistant.text.delta" not in event_types
    assert "assistant.thinking.delta" not in event_types


@pytest.mark.asyncio
async def test_agent_core_tool_capable_catalog_model_receives_tools(
    async_client,
    monkeypatch,
):
    completion_kwargs: dict = {}

    async def fake_completion(*args, **kwargs):
        completion_kwargs.update(kwargs)

        class FakeMessage:
            content = "Tool-capable model reply."

        class FakeChoice:
            message = FakeMessage()

        class FakeResponse:
            choices = [FakeChoice()]
            usage = None

        return FakeResponse()

    monkeypatch.setattr("app.services.agent_core.runtime.acompletion", fake_completion)

    project_id = await _create_project(async_client)
    model = await _create_llm_model(async_client)
    create_session = await async_client.post(
        "/api/v1/agent/sessions",
        json={
            "project_id": project_id,
            "title": "Tool-capable catalog session",
            "model_selection": {"model_id": model["id"]},
        },
    )
    assert create_session.status_code == 201
    session = create_session.json()["data"]

    create_turn = await async_client.post(
        f"/api/v1/agent/sessions/{session['id']}/turns",
        json={"input_text": "Use tools if needed."},
    )
    assert create_turn.status_code == 202
    turn = await _wait_for_turn(async_client, create_turn.json()["data"]["id"])

    assert turn["status"] == "completed"
    assert completion_kwargs["model"] == "agent-test-model"
    assert completion_kwargs["tools"]


@pytest.mark.asyncio
async def test_agent_core_rejects_invisible_catalog_model_selection(
    async_client,
    app,
    db_session,
    monkeypatch,
):
    completion = False

    async def fake_completion(*args, **kwargs):
        nonlocal completion
        completion = True
        raise AssertionError("invisible catalog model should not be called")

    monkeypatch.setattr("app.services.agent_core.runtime.acompletion", fake_completion)
    invisible_model = await _create_scoped_llm_model(
        db_session,
        provider_user_id="other-user",
        model_name="other-user-model",
    )

    app.dependency_overrides[get_current_user] = lambda: _auth_user(user_id="user-1")
    try:
        project_id = await _create_project(async_client)
        create_session = await async_client.post(
            "/api/v1/agent/sessions",
            json={
                "project_id": project_id,
                "title": "Cross-scope model attempt",
                "model_selection": {"model_id": str(invisible_model.id)},
            },
        )
        assert create_session.status_code == 201
        session = create_session.json()["data"]

        create_turn = await async_client.post(
            f"/api/v1/agent/sessions/{session['id']}/turns",
            json={"input_text": "Use the invisible catalog model."},
        )
        assert create_turn.status_code == 202
        turn = await _wait_for_turn(async_client, create_turn.json()["data"]["id"])
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert completion is False
    assert turn["status"] == "failed"
    assert turn["error_code"] == "model_selection_missing"


@pytest.mark.asyncio
async def test_legacy_agent_message_endpoint_is_removed(async_client):
    project_id = await _create_project(async_client)

    resp = await async_client.post(
        "/api/v1/agent/message",
        json={"project_id": project_id, "content": "old endpoint"},
    )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_agent_core_memory_contract(async_client):
    project_id = await _create_project(async_client)

    proposal = await async_client.post(
        "/api/v1/agent/memories/proposals",
        json={
            "project_id": project_id,
            "scope": "project",
            "type": "project_convention",
            "content": {"reference_genome": "hg38"},
            "source": {"kind": "user_confirmed"},
            "confidence": 95,
        },
    )
    assert proposal.status_code == 201
    memory = proposal.json()["data"]
    assert memory["status"] == "proposed"
    assert memory["content"] == {"reference_genome": "hg38"}

    listed = await async_client.get(
        f"/api/v1/agent/memories?project_id={project_id}&status=proposed"
    )
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()["data"]] == [memory["id"]]

    accepted = await async_client.post(
        f"/api/v1/agent/memories/{memory['id']}/accept",
        json={"note": "confirmed"},
    )
    assert accepted.status_code == 200
    assert accepted.json()["data"]["status"] == "accepted"

    rejected_proposal = await async_client.post(
        "/api/v1/agent/memories/proposals",
        json={
            "project_id": project_id,
            "scope": "workflow",
            "type": "run_lesson",
            "content": {"obsolete": True},
        },
    )
    rejected_memory = rejected_proposal.json()["data"]
    rejected = await async_client.post(
        f"/api/v1/agent/memories/{rejected_memory['id']}/reject",
        json={"note": "not reusable"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["data"]["status"] == "rejected"

    disabled_proposal = await async_client.post(
        "/api/v1/agent/memories/proposals",
        json={
            "project_id": project_id,
            "scope": "dataset",
            "type": "analysis_template",
            "content": {"template": "old-report"},
        },
    )
    disabled_memory = disabled_proposal.json()["data"]
    disabled = await async_client.post(
        f"/api/v1/agent/memories/{disabled_memory['id']}/disable",
        json={"note": "superseded"},
    )
    assert disabled.status_code == 200
    assert disabled.json()["data"]["status"] == "disabled"
