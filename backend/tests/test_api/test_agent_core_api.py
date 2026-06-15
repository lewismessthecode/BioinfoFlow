from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app.api.deps import get_current_user
from app.auth.session import AuthUser
from app.config import settings
from app.path_layout import project_home
from app.models.llm import LlmModel, LlmProvider, LlmProviderCredential
from app.services.agent_core.runtime import AgentCoreRuntime
from app.services.llm.credentials import encrypt_secret, generate_credential_fingerprint
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

    model = await _create_llm_model(async_client)
    project_id = await _create_project(async_client)

    create_session = await async_client.post(
        "/api/v1/agent/sessions",
        json={
            "project_id": project_id,
            "title": "WGS triage",
            "permission_mode": "guarded_auto",
            "automation_mode": "assisted",
            "model_selection": {"model_id": model["id"]},
            "metadata": {"batch": "b001"},
        },
    )
    assert create_session.status_code == 201
    session = create_session.json()["data"]
    assert session["title"] == "WGS triage"
    assert session["metadata"] == {
        "batch": "b001",
        "model_selection": {"model_id": model["id"]},
    }
    assert session["model_selection"] == {"model_id": model["id"]}
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
    assert turn["model_selection"] == {"model_id": model["id"]}
    assert turn["model_profile_snapshot"]["resolved_model_selection"] == {
        "provider": "openai_compatible",
        "model": "agent-test-model",
    }
    assert turn["model_profile_snapshot"]["resolved_model_id"] == model["id"]
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
async def test_agent_core_anthropic_catalog_selection_preserves_native_api_base(
    async_client,
    monkeypatch,
):
    completion_kwargs: dict = {}

    async def fake_completion(*args, **kwargs):
        completion_kwargs.update(kwargs)

        class FakeMessage:
            content = "Anthropic model reply."

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
            "name": "Anthropic",
            "kind": "anthropic",
            "base_url": "https://api.anthropic.com",
            "metadata": {"providerTemplate": "anthropic"},
        },
    )
    assert provider_response.status_code == 201
    provider = provider_response.json()["data"]
    credential_response = await async_client.put(
        f"/api/v1/llm/providers/{provider['id']}/credential",
        json={"source": "stored", "secret": "sk-ant-test"},
    )
    assert credential_response.status_code == 200
    model_response = await async_client.post(
        "/api/v1/llm/models",
        json={
            "provider_id": provider["id"],
            "model_id": "claude-sonnet-4-6",
            "display_name": "Claude Sonnet 4.6",
            "supports_streaming": True,
        },
    )
    assert model_response.status_code == 201
    model = model_response.json()["data"]

    create_session = await async_client.post(
        "/api/v1/agent/sessions",
        json={
            "project_id": project_id,
            "title": "Anthropic-routed session",
            "model_selection": {"model_id": model["id"]},
        },
    )
    assert create_session.status_code == 201
    session = create_session.json()["data"]

    create_turn = await async_client.post(
        f"/api/v1/agent/sessions/{session['id']}/turns",
        json={"input_text": "Use Claude."},
    )
    assert create_turn.status_code == 202
    turn = await _wait_for_turn(async_client, create_turn.json()["data"]["id"])

    assert turn["status"] == "completed"
    assert completion_kwargs["model"] == "anthropic/claude-sonnet-4-6"
    # Host root must be preserved — no /v1 suffix appended for Anthropic.
    assert completion_kwargs["api_base"] == "https://api.anthropic.com"
    assert completion_kwargs["api_key"] == "sk-ant-test"


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
    assert completion_kwargs["model"] == "openai/agent-test-model"
    assert completion_kwargs["tools"]


@pytest.mark.asyncio
async def test_catalog_default_prefers_env_managed_vllm_over_other_env_provider(
    db_session,
):
    # Within one scope the env-managed vLLM endpoint a deployment configures on
    # purpose must win over an incidentally-available env provider, even when the
    # other provider is more recently updated (so it sorts first by recency).
    base = datetime(2026, 6, 15, tzinfo=timezone.utc)
    vllm_provider = LlmProvider(
        name="Env vLLM",
        kind="vllm",
        base_url="http://vllm.internal.test:8000/v1",
        scope="global",
        workspace_id=None,
        user_id=None,
        enabled=True,
        provider_metadata={"envManaged": True, "providerTemplate": "vllm"},
        updated_at=base,
    )
    other_provider = LlmProvider(
        name="Env OpenRouter",
        kind="openrouter",
        base_url="https://openrouter.ai/api/v1",
        scope="global",
        workspace_id=None,
        user_id=None,
        enabled=True,
        provider_metadata={"envManaged": True, "providerTemplate": "openrouter"},
        updated_at=base + timedelta(hours=1),
    )
    db_session.add_all([vllm_provider, other_provider])
    await db_session.commit()
    await db_session.refresh(vllm_provider)
    await db_session.refresh(other_provider)
    db_session.add_all(
        [
            LlmProviderCredential(
                provider_id=str(vllm_provider.id),
                source="stored",
                encrypted_secret=encrypt_secret("vllm-key"),
                fingerprint=generate_credential_fingerprint(),
                masked_hint="vllm",
            ),
            LlmProviderCredential(
                provider_id=str(other_provider.id),
                source="stored",
                encrypted_secret=encrypt_secret("or-key"),
                fingerprint=generate_credential_fingerprint(),
                masked_hint="or",
            ),
            LlmModel(
                provider_id=str(vllm_provider.id),
                model_id="deepseek_v4",
                display_name="DeepSeek V4",
                supports_tools=True,
                supports_streaming=True,
            ),
            LlmModel(
                provider_id=str(other_provider.id),
                model_id="openrouter/auto",
                display_name="OpenRouter Auto",
                supports_tools=True,
                supports_streaming=True,
            ),
        ]
    )
    await db_session.commit()

    runtime = AgentCoreRuntime(db_session)
    resolved = await runtime._catalog_default_selection(
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
    )

    assert resolved is not None
    assert resolved["provider"] == "vllm"
    assert resolved["model"] == "deepseek_v4"
    assert resolved["source"] == "catalog_default"


@pytest.mark.asyncio
async def test_agent_core_prefers_user_catalog_model_over_environment_global_default(
    async_client,
    db_session,
    monkeypatch,
):
    completion_kwargs: dict = {}

    async def fake_completion(*args, **kwargs):
        completion_kwargs.update(kwargs)

        class FakeMessage:
            content = "UI-configured model reply."

        class FakeChoice:
            message = FakeMessage()

        class FakeResponse:
            choices = [FakeChoice()]
            usage = None

        return FakeResponse()

    monkeypatch.setattr("app.services.agent_core.runtime.acompletion", fake_completion)

    global_provider = LlmProvider(
        name="Env vLLM",
        kind="vllm",
        base_url="http://env.example.test/v1",
        scope="global",
        workspace_id=None,
        user_id=None,
        enabled=True,
        provider_metadata={"envManaged": True, "providerTemplate": "vllm"},
    )
    user_provider = LlmProvider(
        name="UI vLLM",
        kind="vllm",
        base_url="http://ui.example.test/v1",
        scope="user",
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        enabled=True,
        provider_metadata={"providerTemplate": "vllm"},
    )
    db_session.add_all([global_provider, user_provider])
    await db_session.commit()
    await db_session.refresh(global_provider)
    await db_session.refresh(user_provider)
    db_session.add_all(
        [
            LlmProviderCredential(
                provider_id=str(global_provider.id),
                source="stored",
                encrypted_secret=encrypt_secret("env-key"),
                fingerprint=generate_credential_fingerprint(),
                masked_hint="env-key",
            ),
            LlmProviderCredential(
                provider_id=str(user_provider.id),
                source="stored",
                encrypted_secret=encrypt_secret("ui-key"),
                fingerprint=generate_credential_fingerprint(),
                masked_hint="ui-key",
            ),
            LlmModel(
                provider_id=str(global_provider.id),
                model_id="env-model",
                display_name="Env Model",
                supports_tools=True,
                supports_streaming=True,
            ),
            LlmModel(
                provider_id=str(user_provider.id),
                model_id="ui-model",
                display_name="UI Model",
                supports_tools=True,
                supports_streaming=True,
            ),
        ]
    )
    await db_session.commit()

    project_id = await _create_project(async_client)
    create_session = await async_client.post(
        "/api/v1/agent/sessions",
        json={
            "project_id": project_id,
            "title": "UI model precedence",
        },
    )
    assert create_session.status_code == 201
    session = create_session.json()["data"]

    create_turn = await async_client.post(
        f"/api/v1/agent/sessions/{session['id']}/turns",
        json={"input_text": "Use the UI configured model."},
    )
    assert create_turn.status_code == 202
    turn = await _wait_for_turn(async_client, create_turn.json()["data"]["id"])

    assert turn["status"] == "completed"
    assert completion_kwargs["model"] == "openai/ui-model"
    assert completion_kwargs["api_base"] == "http://ui.example.test/v1"
    assert completion_kwargs["api_key"] == "ui-key"
    assert turn["model_profile_snapshot"]["resolved_model_source"] == "catalog_default"


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
async def test_agent_fs_tree_and_file_are_confined_to_allowed_roots(async_client):
    tree = await async_client.get("/api/v1/agent/fs/tree")
    assert tree.status_code == 200
    entries = tree.json()["data"]["entries"]
    assert isinstance(entries, list)
    files = [e for e in entries if e["type"] == "file"]
    # Fetch one in-root file and confirm its contents come back.
    if files:
        target = files[0]["path"]
        file_resp = await async_client.get(f"/api/v1/agent/fs/file?path={target}")
        assert file_resp.status_code == 200
        assert "content" in file_resp.json()["data"]

    # A path outside the allowed roots is rejected, not served.
    blocked = await async_client.get("/api/v1/agent/fs/tree?path=/etc")
    assert blocked.status_code == 403
    blocked_file = await async_client.get("/api/v1/agent/fs/file?path=/etc/passwd")
    assert blocked_file.status_code == 403


@pytest.mark.asyncio
async def test_agent_fs_tree_defaults_to_project_home(async_client):
    project_id = await _create_project(async_client)
    project_root = project_home(project_id)
    marker = project_root / "project-note.txt"
    marker.write_text("project scoped", encoding="utf-8")

    response = await async_client.get(
        f"/api/v1/agent/fs/tree?project_id={project_id}"
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["path"] == str(project_root)
    assert "project-note.txt" in {entry["name"] for entry in data["entries"]}


@pytest.mark.asyncio
async def test_agent_fs_file_rejects_sensitive_files(async_client, tmp_path, monkeypatch):
    repo_root = tmp_path / "repo"
    data_root = tmp_path / "data"
    repo_root.mkdir()
    data_root.mkdir()
    public_file = repo_root / "notes.txt"
    public_file.write_text("safe note", encoding="utf-8")
    secret_file = repo_root / ".env"
    secret_file.write_text("OPENAI_API_KEY=secret", encoding="utf-8")
    nested_secret = data_root / "auth" / "better-auth.db"
    nested_secret.parent.mkdir()
    nested_secret.write_text("auth db bytes", encoding="utf-8")

    monkeypatch.setattr(settings, "repo_root", str(repo_root))
    monkeypatch.setattr(settings, "bioinfoflow_home", str(data_root))

    public_resp = await async_client.get(
        f"/api/v1/agent/fs/file?path={public_file}"
    )
    assert public_resp.status_code == 200

    secret_resp = await async_client.get(
        f"/api/v1/agent/fs/file?path={secret_file}"
    )
    assert secret_resp.status_code == 403
    data_secret_resp = await async_client.get(
        f"/api/v1/agent/fs/file?path={nested_secret}"
    )
    assert data_secret_resp.status_code == 403


@pytest.mark.asyncio
async def test_agent_toolsets_include_plan_mode(async_client):
    response = await async_client.get("/api/v1/agent/toolsets")

    assert response.status_code == 200
    toolsets = {item["name"]: item["tools"] for item in response.json()["data"]["toolsets"]}
    assert "plan" in toolsets
    assert "exit_plan_mode" in toolsets["plan"]
    assert "bash" not in toolsets["plan"]


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
