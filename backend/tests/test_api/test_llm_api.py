from __future__ import annotations

from contextlib import asynccontextmanager

import httpx
import pytest

from app.api.deps import get_current_user
from app.auth.session import AuthUser
from app.config import settings
from app.models.llm import (
    LlmModel,
    LlmModelProfile,
    LlmProvider,
    LlmProviderCredential,
)
from app.services.llm.credentials import encrypt_secret
from app.workspace import DEFAULT_WORKSPACE_ID


OTHER_WORKSPACE_ID = "00000000-0000-0000-0000-000000000002"
OTHER_PROVIDER_ID = "00000000-0000-0000-0000-00000000aa01"
OTHER_MODEL_ID = "00000000-0000-0000-0000-00000000bb01"
OTHER_PROFILE_ID = "00000000-0000-0000-0000-00000000cc01"


def _network_client_factory(client_type):
    @asynccontextmanager
    async def factory(**kwargs):
        client = client_type(timeout=kwargs.get("timeout"))
        async with client:
            yield client

    return factory


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


async def _create_provider(
    db_session,
    *,
    name: str,
    scope: str = "user",
    workspace_id: str | None = DEFAULT_WORKSPACE_ID,
    user_id: str | None = "user-1",
    enabled: bool = True,
    base_url: str = "http://localhost:11434/v1",
) -> LlmProvider:
    provider = LlmProvider(
        name=name,
        kind="openai_compatible",
        base_url=base_url,
        api_key_ref="env:TEST_KEY",
        scope=scope,
        workspace_id=workspace_id,
        user_id=user_id,
        enabled=enabled,
    )
    db_session.add(provider)
    await db_session.commit()
    await db_session.refresh(provider)
    return provider


async def _create_model(
    db_session,
    *,
    provider_id: str,
    model_id: str,
    display_name: str,
    metadata: dict | None = None,
) -> LlmModel:
    model = LlmModel(
        provider_id=provider_id,
        model_id=model_id,
        display_name=display_name,
        supports_tools=True,
        supports_streaming=True,
        model_metadata=metadata,
    )
    db_session.add(model)
    await db_session.commit()
    await db_session.refresh(model)
    return model


async def _create_profile(
    db_session,
    *,
    name: str,
    primary_model_id: str,
    fallback_model_ids: list[str] | None = None,
    scope: str = "user",
    workspace_id: str | None = DEFAULT_WORKSPACE_ID,
    user_id: str | None = "user-1",
) -> LlmModelProfile:
    profile = LlmModelProfile(
        name=name,
        task_type="agent_core",
        primary_model_id=primary_model_id,
        fallback_model_ids=fallback_model_ids,
        scope=scope,
        workspace_id=workspace_id,
        user_id=user_id,
        enabled=True,
    )
    db_session.add(profile)
    await db_session.commit()
    await db_session.refresh(profile)
    return profile


@pytest.mark.asyncio
async def test_llm_provider_templates_drive_frontend_configuration(async_client):
    response = await async_client.get("/api/v1/llm/provider-templates")

    assert response.status_code == 200
    templates = {item["id"]: item for item in response.json()["data"]}
    assert {
        "openai",
        "anthropic",
        "gemini",
        "grok",
        "groq",
        "deepseek",
        "openrouter",
        "kimi",
        "kimi-cn",
        "qwen",
        "mistral",
        "cohere",
        "together",
        "fireworks",
        "perplexity",
        "ollama",
        "vllm",
        "openai-compatible",
    }.issubset(templates)

    assert templates["openai"]["fields"] == [
        {
            "name": "api_key",
            "label": "API key",
            "secret": True,
            "required": True,
            "placeholder": "Paste API key",
        }
    ]
    assert templates["anthropic"]["fields"] == [
        {
            "name": "api_key",
            "label": "API key",
            "secret": True,
            "required": True,
            "placeholder": "Paste API key",
        }
    ]
    assert templates["kimi"]["fields"] == templates["openai"]["fields"]
    assert templates["kimi"]["default_base_url"] == "https://api.moonshot.ai/v1"
    assert templates["kimi"]["docs_url"] == "https://platform.kimi.ai/console/api-keys"
    assert templates["kimi-cn"]["fields"] == templates["openai"]["fields"]
    assert templates["kimi-cn"]["default_base_url"] == "https://api.moonshot.cn/v1"
    assert (
        templates["kimi-cn"]["docs_url"]
        == "https://platform.kimi.com/console/api-keys"
    )
    assert templates["qwen"]["fields"] == templates["openai"]["fields"]
    assert templates["cohere"]["default_base_url"] == (
        "https://api.cohere.ai/compatibility/v1"
    )
    assert templates["together"]["default_base_url"] == "https://api.together.ai/v1"
    assert templates["perplexity"]["discovery"] == "static"
    assert [model["id"] for model in templates["perplexity"]["models"]] == [
        "sonar",
        "sonar-pro",
        "sonar-reasoning-pro",
        "sonar-deep-research",
    ]
    vllm_fields = {field["name"]: field for field in templates["vllm"]["fields"]}
    assert vllm_fields["base_url"]["default"] == "http://localhost:8000/v1"
    assert vllm_fields["api_key"]["required"] is False
    assert vllm_fields["model_id"]["required"] is False
    assert templates["vllm"]["discovery"] == "openai_models"


@pytest.mark.asyncio
async def test_llm_provider_setup_creates_vllm_provider_key_and_manual_model(
    async_client,
):
    response = await async_client.post(
        "/api/v1/llm/provider-setups",
        json={
            "template_id": "vllm",
            "name": "vLLM DeepSeek V4",
            "base_url": "http://10.49.35.231:8000/v1",
            "api_key": "vllm",
            "model_ids": ["deepseek_v4"],
            "scope": "user",
        },
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["provider"]["name"] == "vLLM DeepSeek V4"
    assert payload["provider"]["kind"] == "vllm"
    assert payload["provider"]["credential"]["configured"] is True
    assert payload["provider"]["credential"]["masked_hint"] == "vl...lm"
    assert payload["models"][0]["model_id"] == "deepseek_v4"

    configuration = await async_client.get("/api/v1/llm/configuration")
    assert configuration.status_code == 200
    configured = configuration.json()["data"]
    assert any(
        model["model_id"] == "deepseek_v4"
        and model["provider_id"] == payload["provider"]["id"]
        for model in configured["models"]
    )


@pytest.mark.asyncio
async def test_llm_provider_setup_creates_kimi_provider_from_key_only(
    async_client,
):
    response = await async_client.post(
        "/api/v1/llm/provider-setups",
        json={
            "template_id": "kimi",
            "api_key": "moonshot-key",
            "scope": "user",
        },
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    provider = payload["provider"]
    assert provider["name"] == "Kimi"
    assert provider["kind"] == "kimi"
    assert provider["wire_protocol"] == "chat_completions"
    assert provider["base_url"] == "https://api.moonshot.ai/v1"
    assert provider["allow_insecure_http"] is False
    assert provider["credential"]["configured"] is True
    assert payload["models"] == []

    configuration = await async_client.get("/api/v1/llm/configuration")
    assert configuration.status_code == 200
    configured = configuration.json()["data"]
    assert any(
        item["id"] == provider["id"]
        and item["credential"]["configured"] is True
        for item in configured["providers"]
    )


@pytest.mark.asyncio
async def test_llm_provider_setup_creates_kimi_china_provider_from_key_only(
    async_client,
):
    response = await async_client.post(
        "/api/v1/llm/provider-setups",
        json={
            "template_id": "kimi-cn",
            "api_key": "moonshot-cn-key",
            "scope": "user",
        },
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    provider = payload["provider"]
    assert provider["name"] == "Kimi China"
    assert provider["kind"] == "kimi_cn"
    assert provider["base_url"] == "https://api.moonshot.cn/v1"


@pytest.mark.asyncio
async def test_llm_configuration_reconciles_legacy_kimi_cn_provider(
    async_client,
    db_session,
):
    legacy_provider = LlmProvider(
        name="Kimi",
        kind="kimi",
        base_url="https://api.moonshot.cn/v1",
        scope="user",
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        enabled=True,
        provider_metadata={"providerTemplate": "kimi"},
    )
    db_session.add(legacy_provider)
    await db_session.commit()
    await db_session.refresh(legacy_provider)
    db_session.add(
        LlmProviderCredential(
            provider_id=str(legacy_provider.id),
            source="stored",
            encrypted_secret=encrypt_secret("moonshot-cn-key"),
            masked_hint="sk...cn",
            updated_by="dev",
        )
    )
    await db_session.commit()

    response = await async_client.get("/api/v1/llm/configuration")

    assert response.status_code == 200
    provider = next(
        item
        for item in response.json()["data"]["providers"]
        if item["id"] == str(legacy_provider.id)
    )
    assert provider["name"] == "Kimi China"
    assert provider["kind"] == "kimi_cn"
    assert provider["base_url"] == "https://api.moonshot.cn/v1"
    assert provider["metadata"]["providerTemplate"] == "kimi-cn"


@pytest.mark.asyncio
async def test_llm_configuration_reconciles_kimi_cn_provider_without_template_metadata(
    async_client,
    db_session,
):
    legacy_provider = LlmProvider(
        name="Kimi",
        kind="kimi",
        base_url="https://api.moonshot.cn/v1",
        scope="user",
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        enabled=True,
        provider_metadata=None,
    )
    db_session.add(legacy_provider)
    await db_session.commit()
    await db_session.refresh(legacy_provider)

    response = await async_client.get("/api/v1/llm/configuration")

    assert response.status_code == 200
    provider = next(
        item
        for item in response.json()["data"]["providers"]
        if item["id"] == str(legacy_provider.id)
    )
    assert provider["name"] == "Kimi China"
    assert provider["kind"] == "kimi_cn"
    assert provider["metadata"]["providerTemplate"] == "kimi-cn"


@pytest.mark.asyncio
async def test_llm_configuration_and_models_exclude_disabled_provider_models(
    async_client,
    db_session,
):
    enabled_provider = await _create_provider(
        db_session,
        name="Enabled provider",
        user_id="dev",
    )
    enabled_model = await _create_model(
        db_session,
        provider_id=str(enabled_provider.id),
        model_id="enabled-model",
        display_name="Enabled Model",
    )
    disabled_provider = await _create_provider(
        db_session,
        name="Disabled provider",
        user_id="dev",
        enabled=False,
    )
    await _create_model(
        db_session,
        provider_id=str(disabled_provider.id),
        model_id="disabled-model",
        display_name="Disabled Model",
    )

    configuration = await async_client.get("/api/v1/llm/configuration")
    models = await async_client.get("/api/v1/llm/models")

    assert configuration.status_code == 200
    configured = configuration.json()["data"]
    assert {item["id"] for item in configured["providers"]} >= {
        str(enabled_provider.id),
        str(disabled_provider.id),
    }
    assert configured["summary"]["model_count"] == 1
    assert [model["id"] for model in configured["models"]] == [
        str(enabled_model.id)
    ]

    assert models.status_code == 200
    assert [model["id"] for model in models.json()["data"]] == [
        str(enabled_model.id)
    ]


@pytest.mark.asyncio
async def test_llm_configuration_and_profiles_exclude_invalid_model_dependencies(
    async_client,
    db_session,
):
    enabled_provider = await _create_provider(
        db_session,
        name="Profile enabled provider",
        user_id="dev",
    )
    enabled_model = await _create_model(
        db_session,
        provider_id=str(enabled_provider.id),
        model_id="profile-enabled-model",
        display_name="Profile Enabled Model",
    )
    enabled_profile = await _create_profile(
        db_session,
        name="Enabled profile",
        primary_model_id=str(enabled_model.id),
        user_id="dev",
    )
    disabled_provider = await _create_provider(
        db_session,
        name="Profile disabled provider",
        user_id="dev",
        enabled=False,
    )
    disabled_model = await _create_model(
        db_session,
        provider_id=str(disabled_provider.id),
        model_id="profile-disabled-model",
        display_name="Profile Disabled Model",
    )
    await _create_profile(
        db_session,
        name="Disabled provider profile",
        primary_model_id=str(disabled_model.id),
        user_id="dev",
    )
    stale_model = await _create_model(
        db_session,
        provider_id=str(enabled_provider.id),
        model_id="profile-stale-model",
        display_name="Profile Stale Model",
        metadata={"catalog_status": "stale"},
    )
    await _create_profile(
        db_session,
        name="Stale model profile",
        primary_model_id=str(stale_model.id),
        user_id="dev",
    )

    configuration = await async_client.get("/api/v1/llm/configuration")
    profiles = await async_client.get("/api/v1/llm/model-profiles")

    assert configuration.status_code == 200
    assert profiles.status_code == 200
    assert [profile["id"] for profile in configuration.json()["data"]["profiles"]] == [
        str(enabled_profile.id)
    ]
    assert [profile["id"] for profile in profiles.json()["data"]] == [
        str(enabled_profile.id)
    ]


@pytest.mark.asyncio
async def test_discover_models_returns_provider_auth_error_without_500(
    async_client,
    monkeypatch,
):
    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def get(self, url: str, headers=None, params=None):
            del headers, params
            return httpx.Response(
                401,
                json={"error": {"message": "invalid api key"}},
                request=httpx.Request("GET", url),
            )

    monkeypatch.setattr(
        "app.services.llm.catalog.network_policy_http_client",
        _network_client_factory(FakeAsyncClient),
    )
    setup = await async_client.post(
        "/api/v1/llm/provider-setups",
        json={
            "template_id": "kimi",
            "api_key": "wrong-platform-key",
            "scope": "user",
        },
    )
    provider_id = setup.json()["data"]["provider"]["id"]

    response = await async_client.post(
        f"/api/v1/llm/providers/{provider_id}/discover-models"
    )

    assert response.status_code == 422
    payload = response.json()
    assert payload["error"]["code"] == "VALIDATION_ERROR"
    assert "401 Unauthorized" in payload["error"]["message"]
    assert "API key" in payload["error"]["message"]


@pytest.mark.asyncio
async def test_discover_models_returns_network_error_without_500(
    async_client,
    monkeypatch,
):
    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def get(self, url: str, headers=None, params=None):
            del headers, params
            raise httpx.ConnectError(
                "connection failed",
                request=httpx.Request("GET", url),
            )

    monkeypatch.setattr(
        "app.services.llm.catalog.network_policy_http_client",
        _network_client_factory(FakeAsyncClient),
    )
    setup = await async_client.post(
        "/api/v1/llm/provider-setups",
        json={
            "template_id": "openai-compatible",
            "base_url": "https://unreachable.example/v1",
            "api_key": "relay-key",
            "scope": "user",
        },
    )
    provider_id = setup.json()["data"]["provider"]["id"]

    response = await async_client.post(
        f"/api/v1/llm/providers/{provider_id}/discover-models"
    )

    assert response.status_code == 422
    payload = response.json()
    assert payload["error"]["code"] == "VALIDATION_ERROR"
    assert "Provider model discovery request failed" in payload["error"]["message"]


@pytest.mark.asyncio
async def test_discover_models_hides_stale_provider_models(
    async_client,
    db_session,
    monkeypatch,
):
    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def get(self, url: str, headers=None, params=None):
            del headers, params
            return httpx.Response(
                200,
                json={"data": [{"id": "kimi-current", "object": "model"}]},
                request=httpx.Request("GET", url),
            )

    monkeypatch.setattr(
        "app.services.llm.catalog.network_policy_http_client",
        _network_client_factory(FakeAsyncClient),
    )
    provider = LlmProvider(
        name="Kimi",
        kind="kimi",
        base_url="https://api.moonshot.ai/v1",
        scope="user",
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="dev",
        enabled=True,
        provider_metadata={"providerTemplate": "kimi"},
    )
    db_session.add(provider)
    await db_session.commit()
    await db_session.refresh(provider)
    db_session.add(
        LlmProviderCredential(
            provider_id=str(provider.id),
            source="stored",
            encrypted_secret=encrypt_secret("moonshot-ai-key"),
            masked_hint="sk...ai",
            updated_by="dev",
        )
    )
    stale_model = await _create_model(
        db_session,
        provider_id=str(provider.id),
        model_id="wrong-manual-model",
        display_name="Wrong Manual Model",
    )

    response = await async_client.post(
        f"/api/v1/llm/providers/{provider.id}/discover-models"
    )
    configuration = await async_client.get("/api/v1/llm/configuration")
    listed = await async_client.get(f"/api/v1/llm/models?provider_id={provider.id}")

    assert response.status_code == 200
    assert [model["model_id"] for model in response.json()["data"]] == [
        "kimi-current"
    ]
    assert configuration.status_code == 200
    assert [model["model_id"] for model in configuration.json()["data"]["models"]] == [
        "kimi-current"
    ]
    assert listed.status_code == 200
    assert [model["model_id"] for model in listed.json()["data"]] == ["kimi-current"]
    await db_session.refresh(stale_model)
    assert stale_model.model_metadata["catalog_status"] == "stale"


@pytest.mark.asyncio
async def test_llm_provider_setup_persists_explicit_responses_protocol(
    async_client,
):
    response = await async_client.post(
        "/api/v1/llm/provider-setups",
        json={
            "template_id": "openai-compatible",
            "name": "Responses relay",
            "base_url": "https://relay.example.com/v1",
            "wire_protocol": "responses",
            "api_key": "relay-key",
            "model_ids": ["gpt-5.4-mini"],
            "scope": "user",
        },
    )

    assert response.status_code == 200
    provider = response.json()["data"]["provider"]
    assert provider["wire_protocol"] == "responses"

    configuration = await async_client.get("/api/v1/llm/configuration")
    assert configuration.status_code == 200
    persisted = next(
        item
        for item in configuration.json()["data"]["providers"]
        if item["id"] == provider["id"]
    )
    assert persisted["wire_protocol"] == "responses"


@pytest.mark.asyncio
async def test_llm_provider_setup_can_switch_wire_protocol_in_both_directions(
    async_client,
):
    created = await async_client.post(
        "/api/v1/llm/provider-setups",
        json={
            "template_id": "openai-compatible",
            "name": "Switchable relay",
            "base_url": "https://relay.example.com/v1",
            "api_key": "relay-key",
            "model_ids": ["gpt-5.4-mini"],
            "scope": "user",
        },
    )
    assert created.status_code == 200
    provider = created.json()["data"]["provider"]
    assert provider["wire_protocol"] == "chat_completions"

    switched_to_responses = await async_client.post(
        "/api/v1/llm/provider-setups",
        json={
            "template_id": "openai-compatible",
            "provider_id": provider["id"],
            "wire_protocol": "responses",
            "scope": "user",
        },
    )
    assert switched_to_responses.status_code == 200
    assert (
        switched_to_responses.json()["data"]["provider"]["wire_protocol"]
        == "responses"
    )

    switched_to_chat = await async_client.post(
        "/api/v1/llm/provider-setups",
        json={
            "template_id": "openai-compatible",
            "provider_id": provider["id"],
            "wire_protocol": "chat_completions",
            "scope": "user",
        },
    )
    assert switched_to_chat.status_code == 200
    assert (
        switched_to_chat.json()["data"]["provider"]["wire_protocol"]
        == "chat_completions"
    )


@pytest.mark.asyncio
async def test_llm_provider_update_rejects_protocol_unsupported_by_current_kind(
    async_client,
):
    created = await async_client.post(
        "/api/v1/llm/providers",
        json={
            "name": "Anthropic endpoint",
            "kind": "anthropic",
        },
    )
    assert created.status_code == 201
    provider = created.json()["data"]
    assert provider["wire_protocol"] == "chat_completions"

    response = await async_client.patch(
        f"/api/v1/llm/providers/{provider['id']}",
        json={"wire_protocol": "responses"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_llm_provider_update_rejects_kind_unsupported_by_current_protocol(
    async_client,
):
    created = await async_client.post(
        "/api/v1/llm/providers",
        json={
            "name": "OpenAI Responses endpoint",
            "kind": "openai",
            "wire_protocol": "responses",
        },
    )
    assert created.status_code == 201
    provider = created.json()["data"]
    assert provider["wire_protocol"] == "responses"

    response = await async_client.patch(
        f"/api/v1/llm/providers/{provider['id']}",
        json={"kind": "anthropic"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_llm_provider_create_defaults_to_chat_completions_for_compatibility(
    async_client,
):
    response = await async_client.post(
        "/api/v1/llm/providers",
        json={
            "name": "Compatibility endpoint",
            "kind": "openai_compatible",
            "base_url": "https://relay.example.com/v1",
        },
    )

    assert response.status_code == 201
    assert response.json()["data"]["wire_protocol"] == "chat_completions"


@pytest.mark.asyncio
async def test_llm_provider_create_normalizes_anthropic_messages_endpoint(
    async_client,
):
    response = await async_client.post(
        "/api/v1/llm/providers",
        json={
            "name": "Anthropic gateway",
            "kind": "anthropic",
            "base_url": "https://anthropic-gateway.example/v1/messages",
        },
    )

    assert response.status_code == 201
    payload = response.json()["data"]
    assert payload["kind"] == "anthropic"
    assert payload["base_url"] == "https://anthropic-gateway.example"
    assert payload["allow_insecure_http"] is False


@pytest.mark.asyncio
async def test_llm_provider_update_normalizes_anthropic_v1_endpoint(
    async_client,
):
    created = await async_client.post(
        "/api/v1/llm/providers",
        json={
            "name": "Anthropic endpoint",
            "kind": "anthropic",
            "base_url": "https://api.anthropic.com",
        },
    )
    assert created.status_code == 201
    provider_id = created.json()["data"]["id"]

    response = await async_client.patch(
        f"/api/v1/llm/providers/{provider_id}",
        json={"base_url": "https://anthropic-gateway.example/v1"},
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["base_url"] == "https://anthropic-gateway.example"
    assert payload["allow_insecure_http"] is False


@pytest.mark.asyncio
async def test_llm_provider_create_accepts_registered_headless_litellm_kind(
    async_client,
):
    response = await async_client.post(
        "/api/v1/llm/providers",
        json={
            "name": "Azure OpenAI",
            "kind": "azure",
            "base_url": "https://example.openai.azure.com",
        },
    )

    assert response.status_code == 201
    assert response.json()["data"]["kind"] == "azure"
    assert response.json()["data"]["wire_protocol"] == "chat_completions"


@pytest.mark.asyncio
async def test_llm_provider_setup_update_preserves_omitted_wire_protocol(
    async_client,
):
    created = await async_client.post(
        "/api/v1/llm/provider-setups",
        json={
            "template_id": "openai-compatible",
            "name": "Persistent Responses relay",
            "base_url": "https://relay.example.com/v1",
            "wire_protocol": "responses",
            "api_key": "relay-key",
            "model_ids": ["gpt-5.4-mini"],
            "scope": "user",
        },
    )
    assert created.status_code == 200
    provider = created.json()["data"]["provider"]
    assert provider["wire_protocol"] == "responses"

    updated = await async_client.post(
        "/api/v1/llm/provider-setups",
        json={
            "template_id": "openai-compatible",
            "provider_id": provider["id"],
            "name": "Renamed Responses relay",
            "scope": "user",
        },
    )

    assert updated.status_code == 200
    updated_provider = updated.json()["data"]["provider"]
    assert updated_provider["name"] == "Renamed Responses relay"
    assert updated_provider["wire_protocol"] == "responses"


@pytest.mark.asyncio
async def test_llm_provider_setup_updates_legacy_null_metadata(
    async_client,
    db_session,
):
    provider = await _create_provider(
        db_session,
        name="Legacy OpenAI-compatible relay",
        user_id="dev",
    )
    assert provider.provider_metadata is None

    response = await async_client.post(
        "/api/v1/llm/provider-setups",
        json={
            "template_id": "openai-compatible",
            "provider_id": str(provider.id),
            "name": "Responses relay",
            "base_url": "http://public-relay.example:8079/v1",
            "wire_protocol": "responses",
            "api_key": "relay-key",
            "model_ids": ["gpt-5.4-mini"],
            "allow_insecure_http": True,
            "scope": "user",
        },
    )

    assert response.status_code == 200, response.text
    configured = response.json()["data"]
    assert configured["provider"]["base_url"] == "http://public-relay.example:8079/v1"
    await db_session.refresh(provider)
    assert provider.provider_metadata == {"providerTemplate": "openai-compatible"}
    assert configured["provider"]["wire_protocol"] == "responses"
    assert configured["models"][0]["model_id"] == "gpt-5.4-mini"


@pytest.mark.asyncio
async def test_llm_provider_setup_allows_explicit_public_insecure_http(
    async_client,
):
    response = await async_client.post(
        "/api/v1/llm/provider-setups",
        json={
            "template_id": "openai-compatible",
            "name": "Public HTTP Relay",
            "base_url": "http://public-relay.example:8079/v1",
            "api_key": "relay-key",
            "model_ids": ["gpt-5.6-sol"],
            "allow_insecure_http": True,
            "scope": "user",
        },
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["provider"]["allow_insecure_http"] is True
    assert payload["provider"]["base_url"] == "http://public-relay.example:8079/v1"
    assert payload["models"][0]["model_id"] == "gpt-5.6-sol"

    configuration = await async_client.get("/api/v1/llm/configuration")
    assert configuration.status_code == 200
    configured_provider = next(
        provider
        for provider in configuration.json()["data"]["providers"]
        if provider["id"] == payload["provider"]["id"]
    )
    assert configured_provider["allow_insecure_http"] is True


@pytest.mark.asyncio
async def test_llm_provider_update_requires_public_insecure_http_opt_in(
    async_client,
):
    setup = await async_client.post(
        "/api/v1/llm/provider-setups",
        json={
            "template_id": "openai-compatible",
            "name": "Secure relay",
            "base_url": "https://relay.example.com/v1",
            "model_ids": ["relay-model"],
            "scope": "user",
        },
    )
    assert setup.status_code == 200
    provider_id = setup.json()["data"]["provider"]["id"]

    rejected = await async_client.patch(
        f"/api/v1/llm/providers/{provider_id}",
        json={"base_url": "http://public-relay.example:8079/v1"},
    )
    assert rejected.status_code == 422

    allowed = await async_client.patch(
        f"/api/v1/llm/providers/{provider_id}",
        json={
            "base_url": "http://public-relay.example:8079/v1",
            "allow_insecure_http": True,
        },
    )
    assert allowed.status_code == 200
    assert allowed.json()["data"]["allow_insecure_http"] is True


@pytest.mark.asyncio
async def test_openai_compatible_provider_discovers_models_from_v1_models(
    async_client,
    monkeypatch,
):
    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def get(self, url: str, headers=None):
            assert url == "http://10.49.35.231:8000/v1/models"
            assert headers == {"Authorization": "Bearer vllm"}
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"id": "deepseek_v4", "object": "model"},
                        {"id": "bio-coder", "object": "model"},
                    ]
                },
                request=httpx.Request("GET", url),
            )

    monkeypatch.setattr(
        "app.services.llm.catalog.network_policy_http_client",
        _network_client_factory(FakeAsyncClient),
    )

    setup = await async_client.post(
        "/api/v1/llm/provider-setups",
        json={
            "template_id": "vllm",
            "name": "vLLM DeepSeek V4",
            "base_url": "http://10.49.35.231:8000/v1",
            "api_key": "vllm",
            "scope": "user",
        },
    )
    assert setup.status_code == 200
    provider = setup.json()["data"]["provider"]

    response = await async_client.post(
        f"/api/v1/llm/providers/{provider['id']}/discover-models",
    )

    assert response.status_code == 200
    model_ids = {model["model_id"] for model in response.json()["data"]}
    assert model_ids == {"deepseek_v4", "bio-coder"}


@pytest.mark.asyncio
async def test_anthropic_provider_discovers_models_from_v1_models(
    async_client,
    monkeypatch,
):
    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def get(self, url: str, headers=None, params=None):
            assert url == "https://api.anthropic.com/v1/models"
            assert headers == {
                "x-api-key": "sk-ant",
                "anthropic-version": "2023-06-01",
            }
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"id": "claude-sonnet-4-6", "display_name": "Claude Sonnet 4.6"},
                        {"id": "claude-haiku-4-5", "display_name": "Claude Haiku 4.5"},
                    ]
                },
                request=httpx.Request("GET", url),
            )

    monkeypatch.setattr(
        "app.services.llm.catalog.network_policy_http_client",
        _network_client_factory(FakeAsyncClient),
    )

    setup = await async_client.post(
        "/api/v1/llm/provider-setups",
        json={"template_id": "anthropic", "api_key": "sk-ant", "scope": "user"},
    )
    assert setup.status_code == 200
    provider = setup.json()["data"]["provider"]

    response = await async_client.post(
        f"/api/v1/llm/providers/{provider['id']}/discover-models",
    )

    assert response.status_code == 200
    model_ids = {model["model_id"] for model in response.json()["data"]}
    assert model_ids == {"claude-sonnet-4-6", "claude-haiku-4-5"}


@pytest.mark.asyncio
async def test_gemini_provider_discovers_models_and_skips_non_generative(
    async_client,
    monkeypatch,
):
    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def get(self, url: str, headers=None, params=None):
            assert url == "https://generativelanguage.googleapis.com/v1beta/models"
            assert headers == {"x-goog-api-key": "gemini-key"}
            assert params == {"pageSize": 1000}
            return httpx.Response(
                200,
                json={
                    "models": [
                        {
                            "name": "models/gemini-3-pro",
                            "displayName": "Gemini 3 Pro",
                            "supportedGenerationMethods": ["generateContent"],
                            "inputTokenLimit": 1000000,
                            "outputTokenLimit": 65536,
                        },
                        {
                            "name": "models/text-embedding-004",
                            "supportedGenerationMethods": ["embedContent"],
                        },
                    ]
                },
                request=httpx.Request("GET", url),
            )

    monkeypatch.setattr(
        "app.services.llm.catalog.network_policy_http_client",
        _network_client_factory(FakeAsyncClient),
    )

    setup = await async_client.post(
        "/api/v1/llm/provider-setups",
        json={"template_id": "gemini", "api_key": "gemini-key", "scope": "user"},
    )
    assert setup.status_code == 200
    provider = setup.json()["data"]["provider"]

    response = await async_client.post(
        f"/api/v1/llm/providers/{provider['id']}/discover-models",
    )

    assert response.status_code == 200
    models = response.json()["data"]
    model_ids = {model["model_id"] for model in models}
    assert model_ids == {"gemini-3-pro"}
    gemini_model = next(model for model in models if model["model_id"] == "gemini-3-pro")
    assert gemini_model["context_length"] == 1000000


@pytest.mark.asyncio
async def test_gemini_discovery_error_logs_do_not_expose_api_key(
    async_client,
    monkeypatch,
    caplog,
):
    secret = "sentinel-gemini-log-secret"

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def get(self, url: str, headers=None, params=None):
            assert headers == {"x-goog-api-key": secret}
            assert params == {"pageSize": 1000}
            return httpx.Response(
                403,
                json={"error": {"message": "invalid credential"}},
                request=httpx.Request("GET", url, params=params, headers=headers),
            )

    monkeypatch.setattr(
        "app.services.llm.catalog.network_policy_http_client",
        _network_client_factory(FakeAsyncClient),
    )

    setup = await async_client.post(
        "/api/v1/llm/provider-setups",
        json={"template_id": "gemini", "api_key": secret, "scope": "user"},
    )
    assert setup.status_code == 200
    provider = setup.json()["data"]["provider"]

    response = await async_client.post(
        f"/api/v1/llm/providers/{provider['id']}/discover-models",
    )

    assert response.status_code == 422
    payload = response.json()
    assert payload["error"]["code"] == "VALIDATION_ERROR"
    assert "403 Forbidden" in payload["error"]["message"]
    assert "API key" in payload["error"]["message"]
    assert secret not in response.text
    assert secret not in caplog.text


@pytest.mark.asyncio
async def test_llm_provider_model_and_profile_contract(async_client):
    create_provider = await async_client.post(
        "/api/v1/llm/providers",
        json={
            "name": "Local OpenAI Compatible",
            "kind": "openai_compatible",
            "base_url": "http://localhost:11434/v1",
            "api_key_ref": "env:LOCAL_MODEL_KEY",
            "metadata": {"purpose": "contract-test"},
        },
    )
    assert create_provider.status_code == 201
    provider = create_provider.json()["data"]
    assert provider["kind"] == "openai_compatible"
    assert provider["metadata"] == {"purpose": "contract-test"}

    list_providers = await async_client.get("/api/v1/llm/providers")
    assert list_providers.status_code == 200
    assert [item["id"] for item in list_providers.json()["data"]] == [provider["id"]]

    test_provider = await async_client.post(
        f"/api/v1/llm/providers/{provider['id']}/test"
    )
    assert test_provider.status_code == 200
    assert test_provider.json()["data"]["success"] is False
    assert test_provider.json()["data"]["error_code"] == "model_not_configured"
    assert test_provider.json()["data"]["error"] == (
        "No model is configured for this provider."
    )

    create_model = await async_client.post(
        "/api/v1/llm/models",
        json={
            "provider_id": provider["id"],
            "model_id": "local-bio-coder",
            "display_name": "Local Bio Coder",
            "context_length": 128000,
            "supports_tools": True,
            "supports_streaming": True,
            "supports_json_schema": True,
            "supports_reasoning": True,
        },
    )
    assert create_model.status_code == 201
    model = create_model.json()["data"]
    assert model["model_id"] == "local-bio-coder"
    assert model["supports_tools"] is True

    create_profile = await async_client.post(
        "/api/v1/llm/model-profiles",
        json={
            "name": "Bioinformatics agent default",
            "task_type": "agent_core",
            "primary_model_id": model["id"],
            "reasoning_budget": 4096,
            "max_tokens": 8192,
        },
    )
    assert create_profile.status_code == 201
    profile = create_profile.json()["data"]
    assert profile["task_type"] == "agent_core"
    assert profile["primary_model_id"] == model["id"]

    list_profiles = await async_client.get("/api/v1/llm/model-profiles")
    assert list_profiles.status_code == 200
    assert [item["id"] for item in list_profiles.json()["data"]] == [profile["id"]]


@pytest.mark.asyncio
async def test_llm_configuration_uses_write_only_provider_credentials(async_client):
    create_provider = await async_client.post(
        "/api/v1/llm/providers",
        json={
            "name": "Private OpenAI Gateway",
            "kind": "openai_compatible",
            "base_url": "https://models.internal.example/v1",
        },
    )
    assert create_provider.status_code == 201
    provider = create_provider.json()["data"]

    set_credential = await async_client.put(
        f"/api/v1/llm/providers/{provider['id']}/credential",
        json={
            "source": "stored",
            "secret": "sk-test-provider-secret-value",
        },
    )
    assert set_credential.status_code == 200
    credential = set_credential.json()["data"]
    assert credential["source"] == "stored"
    assert credential["configured"] is True
    assert credential["available"] is True
    assert credential["masked_hint"].endswith("alue")
    assert "secret" not in credential
    assert "encrypted_secret" not in credential

    create_model = await async_client.post(
        "/api/v1/llm/models",
        json={
            "provider_id": provider["id"],
            "model_id": "bio-agent-large",
            "display_name": "Bio Agent Large",
            "context_length": 128000,
            "supports_tools": True,
            "supports_streaming": True,
        },
    )
    assert create_model.status_code == 201
    model = create_model.json()["data"]

    create_profile = await async_client.post(
        "/api/v1/llm/model-profiles",
        json={
            "name": "Agent default",
            "task_type": "agent_core",
            "primary_model_id": model["id"],
            "max_tokens": 8192,
        },
    )
    assert create_profile.status_code == 201

    configuration = await async_client.get("/api/v1/llm/configuration")
    assert configuration.status_code == 200
    payload = configuration.json()["data"]
    assert payload["summary"]["provider_count"] == 1
    assert payload["summary"]["configured_provider_count"] == 1
    assert payload["summary"]["available_provider_count"] == 1
    assert payload["summary"]["model_count"] == 1
    assert payload["providers"][0]["credential"]["configured"] is True
    assert payload["providers"][0]["credential"]["available"] is True
    assert payload["providers"][0]["credential"]["masked_hint"].endswith("alue")
    assert payload["models"][0]["provider_id"] == provider["id"]
    assert payload["profiles"][0]["primary_model_id"] == model["id"]


@pytest.mark.asyncio
async def test_llm_provider_credential_accepts_env_reference(async_client, monkeypatch):
    monkeypatch.delenv("LOCAL_MODEL_API_KEY", raising=False)
    create_provider = await async_client.post(
        "/api/v1/llm/providers",
        json={
            "name": "Env Gateway",
            "kind": "openai_compatible",
            "base_url": "http://localhost:11434/v1",
        },
    )
    assert create_provider.status_code == 201
    provider = create_provider.json()["data"]

    response = await async_client.put(
        f"/api/v1/llm/providers/{provider['id']}/credential",
        json={
            "source": "env",
            "env_var_name": "LOCAL_MODEL_API_KEY",
        },
    )

    assert response.status_code == 200
    credential = response.json()["data"]
    assert credential == {
        "provider_id": provider["id"],
        "source": "env",
        "configured": False,
        "available": False,
        "env_var_name": "LOCAL_MODEL_API_KEY",
        "fingerprint": None,
        "masked_hint": "env:LOCAL_MODEL_API_KEY",
        "updated_at": credential["updated_at"],
    }


@pytest.mark.asyncio
async def test_llm_provider_env_credential_is_available_when_env_exists(
    async_client,
    monkeypatch,
):
    monkeypatch.setenv("LOCAL_MODEL_API_KEY", "local-secret")
    create_provider = await async_client.post(
        "/api/v1/llm/providers",
        json={
            "name": "Env Gateway Ready",
            "kind": "openai_compatible",
            "base_url": "http://localhost:11434/v1",
        },
    )
    assert create_provider.status_code == 201
    provider = create_provider.json()["data"]

    response = await async_client.put(
        f"/api/v1/llm/providers/{provider['id']}/credential",
        json={
            "source": "env",
            "env_var_name": "LOCAL_MODEL_API_KEY",
        },
    )

    assert response.status_code == 200
    assert response.json()["data"]["configured"] is True
    assert response.json()["data"]["available"] is True


@pytest.mark.asyncio
async def test_llm_provider_validation_errors_return_422(async_client):
    response = await async_client.post(
        "/api/v1/llm/providers",
        json={
            "name": "Bad provider",
            "kind": "openai_compatible",
            "base_url": "not-a-url",
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_ollama_provider_discovers_local_models(async_client, monkeypatch):
    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def get(self, url: str):
            assert url == "http://127.0.0.1:11434/api/tags"
            return httpx.Response(
                200,
                json={
                    "models": [
                        {
                            "name": "deepseek-r1:latest",
                            "model": "deepseek-r1:latest",
                            "details": {"parameter_size": "8.2B"},
                        }
                    ]
                },
                request=httpx.Request("GET", url),
            )

    monkeypatch.setattr(
        "app.services.llm.catalog.network_policy_http_client",
        _network_client_factory(FakeAsyncClient),
    )

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

    response = await async_client.post(
        f"/api/v1/llm/providers/{provider['id']}/discover-models",
    )

    assert response.status_code == 200
    models = response.json()["data"]
    assert len(models) == 1
    assert models[0]["provider_id"] == provider["id"]
    assert models[0]["model_id"] == "deepseek-r1:latest"
    assert models[0]["display_name"] == "DeepSeek R1"
    assert models[0]["supports_reasoning"] is True

    configuration = await async_client.get("/api/v1/llm/configuration")
    assert configuration.status_code == 200
    assert any(
        model["model_id"] == "deepseek-r1:latest"
        for model in configuration.json()["data"]["models"]
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "path", "json_body"),
    [
        ("post", "/api/v1/llm/providers", {"name": "p", "kind": "openai"}),
        ("patch", f"/api/v1/llm/providers/{OTHER_PROVIDER_ID}", {"name": "p"}),
        ("post", f"/api/v1/llm/providers/{OTHER_PROVIDER_ID}/test", None),
        (
            "post",
            "/api/v1/llm/models",
            {
                "provider_id": OTHER_PROVIDER_ID,
                "model_id": "gpt-test",
                "display_name": "GPT Test",
            },
        ),
        ("patch", f"/api/v1/llm/models/{OTHER_MODEL_ID}", {"display_name": "GPT Test"}),
        (
            "post",
            "/api/v1/llm/model-profiles",
            {
                "name": "Agent profile",
                "task_type": "agent_core",
                "primary_model_id": OTHER_MODEL_ID,
            },
        ),
        ("patch", f"/api/v1/llm/model-profiles/{OTHER_PROFILE_ID}", {"name": "Agent profile"}),
    ],
)
async def test_llm_mutations_require_authenticated_user(
    async_client,
    monkeypatch,
    method: str,
    path: str,
    json_body: dict | None,
):
    monkeypatch.setattr(settings, "auth_mode", "personal")
    monkeypatch.setattr(settings, "auth_enabled", True)

    response = await getattr(async_client, method)(path, json=json_body)

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_llm_provider_test_selects_model_and_rejects_foreign_model(
    async_client,
    monkeypatch,
) -> None:
    first_provider = await async_client.post(
        "/api/v1/llm/providers",
        json={
            "name": "Probe provider",
            "kind": "openai_compatible",
            "base_url": "https://probe.example/v1",
        },
    )
    second_provider = await async_client.post(
        "/api/v1/llm/providers",
        json={
            "name": "Other provider",
            "kind": "openai_compatible",
            "base_url": "https://other.example/v1",
        },
    )
    assert first_provider.status_code == 201
    assert second_provider.status_code == 201
    first_provider_id = first_provider.json()["data"]["id"]
    second_provider_id = second_provider.json()["data"]["id"]

    model_b = await async_client.post(
        "/api/v1/llm/models",
        json={
            "provider_id": first_provider_id,
            "model_id": "model-b",
            "display_name": "Zulu model",
        },
    )
    model_a = await async_client.post(
        "/api/v1/llm/models",
        json={
            "provider_id": first_provider_id,
            "model_id": "model-a",
            "display_name": "Alpha model",
        },
    )
    foreign_model = await async_client.post(
        "/api/v1/llm/models",
        json={
            "provider_id": second_provider_id,
            "model_id": "foreign-model",
            "display_name": "Foreign model",
        },
    )
    assert model_b.status_code == 201
    assert model_a.status_code == 201
    assert foreign_model.status_code == 201

    selected_models: list[str] = []

    class FakeProbeResult:
        success = True
        latency_ms = 7
        wire_protocol = "chat_completions"
        model_id = "model-a"
        error_code = None
        error_message = None
        retryable = False
        http_status = None
        provider_code = None

        def to_public_dict(self) -> dict:
            return {
                "success": self.success,
                "latency_ms": self.latency_ms,
                "wire_protocol": self.wire_protocol,
                "model_id": self.model_id,
                "error_code": self.error_code,
                "error_message": self.error_message,
                "retryable": self.retryable,
                "http_status": self.http_status,
                "provider_code": self.provider_code,
            }

    async def fake_probe(self, **kwargs):
        del self
        selected_models.append(kwargs["model_id"])
        return FakeProbeResult()

    monkeypatch.setattr("app.services.llm.catalog.LlmProviderProbe.probe", fake_probe)

    default_result = await async_client.post(
        f"/api/v1/llm/providers/{first_provider_id}/test",
        json={},
    )
    assert default_result.status_code == 200
    assert default_result.json()["data"]["model"] == "model-a"
    assert selected_models == ["model-a"]

    explicit_result = await async_client.post(
        f"/api/v1/llm/providers/{first_provider_id}/test",
        json={"model_id": model_b.json()["data"]["id"]},
    )
    assert explicit_result.status_code == 200
    assert selected_models == ["model-a", "model-b"]

    rejected = await async_client.post(
        f"/api/v1/llm/providers/{first_provider_id}/test",
        json={"model_id": foreign_model.json()["data"]["id"]},
    )
    assert rejected.status_code == 422
    assert "foreign-model" not in rejected.text


@pytest.mark.asyncio
async def test_llm_provider_test_skips_and_rejects_stale_models(
    async_client,
    db_session,
    monkeypatch,
) -> None:
    provider = await _create_provider(
        db_session,
        name="Probe stale provider",
        base_url="https://probe.example/v1",
        user_id="dev",
    )
    stale_model = await _create_model(
        db_session,
        provider_id=str(provider.id),
        model_id="stale-model",
        display_name="Alpha stale model",
        metadata={"catalog_status": "stale"},
    )
    await _create_model(
        db_session,
        provider_id=str(provider.id),
        model_id="active-model",
        display_name="Zulu active model",
    )
    selected_models: list[str] = []

    class FakeProbeResult:
        success = True
        latency_ms = 7
        wire_protocol = "chat_completions"
        model_id = "active-model"
        error_code = None
        error_message = None
        retryable = False
        http_status = None
        provider_code = None

        def to_public_dict(self) -> dict:
            return {
                "success": self.success,
                "latency_ms": self.latency_ms,
                "wire_protocol": self.wire_protocol,
                "model_id": self.model_id,
                "error_code": self.error_code,
                "error_message": self.error_message,
                "retryable": self.retryable,
                "http_status": self.http_status,
                "provider_code": self.provider_code,
            }

    async def fake_probe(self, **kwargs):
        del self
        selected_models.append(kwargs["model_id"])
        return FakeProbeResult()

    monkeypatch.setattr("app.services.llm.catalog.LlmProviderProbe.probe", fake_probe)

    default_result = await async_client.post(
        f"/api/v1/llm/providers/{provider.id}/test",
        json={},
    )
    rejected = await async_client.post(
        f"/api/v1/llm/providers/{provider.id}/test",
        json={"model_id": str(stale_model.id)},
    )

    assert default_result.status_code == 200
    assert default_result.json()["data"]["model"] == "active-model"
    assert selected_models == ["active-model"]
    assert rejected.status_code == 422
    assert "stale-model" not in rejected.text


@pytest.mark.asyncio
async def test_llm_provider_test_without_models_returns_safe_failure(
    async_client,
    db_session,
    monkeypatch,
) -> None:
    provider_response = await async_client.post(
        "/api/v1/llm/providers",
        json={
            "name": "Empty provider",
            "kind": "openai_compatible",
            "base_url": "https://empty.example/v1",
        },
    )
    provider_id = provider_response.json()["data"]["id"]

    async def forbidden_probe(*args, **kwargs):
        del args, kwargs
        raise AssertionError("probe must not run without a configured model")

    monkeypatch.setattr("app.services.llm.catalog.LlmProviderProbe.probe", forbidden_probe)

    response = await async_client.post(f"/api/v1/llm/providers/{provider_id}/test")

    assert response.status_code == 200
    assert response.json()["data"] == {
        "provider_id": provider_id,
        "success": False,
        "model": None,
        "wire_protocol": "chat_completions",
        "error_code": "model_not_configured",
        "error": "No model is configured for this provider.",
        "latency_ms": None,
        "retryable": False,
        "http_status": None,
        "provider_code": None,
    }
    provider_row = await db_session.get(LlmProvider, provider_id)
    assert provider_row is not None
    await db_session.refresh(provider_row)
    assert "_invocation_fingerprint" in (provider_row.test_status or {})
    assert "_invocation_fingerprint" not in response.text

    renamed = await async_client.patch(
        f"/api/v1/llm/providers/{provider_id}",
        json={"name": "Renamed empty provider"},
    )
    assert renamed.status_code == 200
    assert renamed.json()["data"]["test_status"]["error_code"] == (
        "model_not_configured"
    )

    changed = await async_client.patch(
        f"/api/v1/llm/providers/{provider_id}",
        json={"base_url": "https://changed-empty.example/v1"},
    )
    assert changed.status_code == 200
    assert changed.json()["data"]["test_status"] is None


@pytest.mark.asyncio
async def test_provider_test_status_preserves_equivalent_and_unrelated_edits(
    async_client,
    monkeypatch,
) -> None:
    provider_response = await async_client.post(
        "/api/v1/llm/providers",
        json={
            "name": "Stable probe provider",
            "kind": "openai_compatible",
            "base_url": "https://stable.example",
        },
    )
    provider_id = provider_response.json()["data"]["id"]
    model_response = await async_client.post(
        "/api/v1/llm/models",
        json={
            "provider_id": provider_id,
            "model_id": "stable-model",
            "display_name": "Stable model",
        },
    )
    assert model_response.status_code == 201

    class FakeProbeResult:
        def to_public_dict(self) -> dict:
            return {
                "success": True,
                "latency_ms": 4,
                "wire_protocol": "chat_completions",
                "model_id": "stable-model",
                "error_code": None,
                "error_message": None,
                "retryable": False,
                "http_status": None,
                "provider_code": None,
            }

    probe_base_urls: list[str | None] = []

    async def fake_probe(*args, **kwargs):
        del args
        probe_base_urls.append(kwargs.get("base_url"))
        return FakeProbeResult()

    monkeypatch.setattr("app.services.llm.catalog.LlmProviderProbe.probe", fake_probe)
    tested = await async_client.post(f"/api/v1/llm/providers/{provider_id}/test")
    assert tested.status_code == 200
    assert tested.json()["data"]["success"] is True
    assert probe_base_urls == ["https://stable.example/v1"]
    assert "_invocation_fingerprint" not in tested.text

    for update in (
        {"name": "Renamed stable provider"},
        {"allow_insecure_http": True},
        {"metadata": {"note": "unrelated"}},
        {"base_url": "https://stable.example/v1/"},
    ):
        response = await async_client.patch(
            f"/api/v1/llm/providers/{provider_id}",
            json=update,
        )
        assert response.status_code == 200
        assert response.json()["data"]["test_status"]["success"] is True
        assert "_invocation_fingerprint" not in response.text

    changed = await async_client.patch(
        f"/api/v1/llm/providers/{provider_id}",
        json={"base_url": "https://different.example/v1"},
    )
    assert changed.status_code == 200
    assert changed.json()["data"]["test_status"] is None


@pytest.mark.asyncio
async def test_provider_list_invalidates_test_status_after_env_rotation(
    async_client,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ROTATING_PROVIDER_KEY", "first-secret-value")
    provider_response = await async_client.post(
        "/api/v1/llm/providers",
        json={
            "name": "Rotating env provider",
            "kind": "openai_compatible",
            "base_url": "https://rotation.example/v1",
        },
    )
    provider_id = provider_response.json()["data"]["id"]
    model_response = await async_client.post(
        "/api/v1/llm/models",
        json={
            "provider_id": provider_id,
            "model_id": "rotation-model",
            "display_name": "Rotation model",
        },
    )
    assert model_response.status_code == 201
    credential = await async_client.put(
        f"/api/v1/llm/providers/{provider_id}/credential",
        json={"source": "env", "env_var_name": "ROTATING_PROVIDER_KEY"},
    )
    assert credential.status_code == 200

    class FakeProbeResult:
        def to_public_dict(self) -> dict:
            return {
                "success": True,
                "latency_ms": 5,
                "wire_protocol": "chat_completions",
                "model_id": "rotation-model",
                "error_code": None,
                "error_message": None,
                "retryable": False,
                "http_status": None,
                "provider_code": None,
            }

    async def fake_probe(*args, **kwargs):
        del args, kwargs
        return FakeProbeResult()

    monkeypatch.setattr("app.services.llm.catalog.LlmProviderProbe.probe", fake_probe)
    tested = await async_client.post(f"/api/v1/llm/providers/{provider_id}/test")
    assert tested.status_code == 200
    assert tested.json()["data"]["success"] is True

    monkeypatch.setenv("ROTATING_PROVIDER_KEY", "second-secret-value")
    providers = await async_client.get("/api/v1/llm/providers")

    assert providers.status_code == 200
    provider = next(item for item in providers.json()["data"] if item["id"] == provider_id)
    assert provider["test_status"] is None
    assert "first-secret-value" not in providers.text
    assert "second-secret-value" not in providers.text
    assert "_invocation_fingerprint" not in providers.text


@pytest.mark.asyncio
async def test_provider_setup_with_manual_model_and_discover_false_never_discovers(
    async_client,
    monkeypatch,
) -> None:
    async def forbidden_discovery(*args, **kwargs):
        del args, kwargs
        raise AssertionError("save must not trigger discovery")

    monkeypatch.setattr(
        "app.services.llm.catalog.LlmCatalogService.discover_models",
        forbidden_discovery,
    )

    response = await async_client.post(
        "/api/v1/llm/provider-setups",
        json={
            "template_id": "openai-compatible",
            "name": "Manual relay",
            "base_url": "https://manual.example/v1",
            "api_key": "manual-secret",
            "model_ids": ["manual-model"],
            "discover": False,
        },
    )

    assert response.status_code == 200
    assert response.json()["data"]["discovered"] is False
    assert [model["model_id"] for model in response.json()["data"]["models"]] == [
        "manual-model"
    ]


@pytest.mark.asyncio
async def test_create_provider_derives_tenant_fields_from_session(
    async_client,
    app,
    db_session,
):
    app.dependency_overrides[get_current_user] = lambda: _auth_user(
        user_id="user-1",
        workspace_id=DEFAULT_WORKSPACE_ID,
        role="owner",
    )
    try:
        response = await async_client.post(
            "/api/v1/llm/providers",
            json={
                "name": "Tenant forced provider",
                "kind": "openai_compatible",
                "scope": "user",
                "workspace_id": OTHER_WORKSPACE_ID,
                "user_id": "other-user",
            },
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 201
    provider = response.json()["data"]
    assert provider["workspace_id"] == DEFAULT_WORKSPACE_ID
    assert provider["user_id"] == "user-1"

    persisted = await db_session.get(LlmProvider, provider["id"])
    assert persisted is not None
    assert str(persisted.workspace_id) == DEFAULT_WORKSPACE_ID
    assert persisted.user_id == "user-1"


@pytest.mark.asyncio
async def test_create_model_profile_derives_tenant_fields_from_session(
    async_client,
    app,
    db_session,
):
    provider = await _create_provider(db_session, name="Profile tenant provider")
    model = await _create_model(
        db_session,
        provider_id=str(provider.id),
        model_id="tenant-model",
        display_name="Tenant Model",
    )
    app.dependency_overrides[get_current_user] = lambda: _auth_user(
        user_id="user-1",
        workspace_id=DEFAULT_WORKSPACE_ID,
        role="owner",
    )
    try:
        response = await async_client.post(
            "/api/v1/llm/model-profiles",
            json={
                "name": "Tenant forced profile",
                "task_type": "agent_core",
                "primary_model_id": str(model.id),
                "scope": "user",
                "workspace_id": OTHER_WORKSPACE_ID,
                "user_id": "other-user",
            },
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 201
    profile = response.json()["data"]
    assert profile["workspace_id"] == DEFAULT_WORKSPACE_ID
    assert profile["user_id"] == "user-1"

    persisted = await db_session.get(LlmModelProfile, profile["id"])
    assert persisted is not None
    assert str(persisted.workspace_id) == DEFAULT_WORKSPACE_ID
    assert persisted.user_id == "user-1"


@pytest.mark.asyncio
async def test_team_member_cannot_write_workspace_or_global_llm_scope(
    async_client,
    app,
    monkeypatch,
):
    monkeypatch.setattr(settings, "auth_mode", "team")
    monkeypatch.setattr(settings, "auth_enabled", True)
    app.dependency_overrides[get_current_user] = lambda: _auth_user(
        user_id="member-1",
        role="member",
    )
    try:
        workspace_response = await async_client.post(
            "/api/v1/llm/providers",
            json={
                "name": "Workspace provider",
                "kind": "openai_compatible",
                "scope": "workspace",
            },
        )
        global_response = await async_client.post(
            "/api/v1/llm/providers",
            json={
                "name": "Global provider",
                "kind": "openai_compatible",
                "scope": "global",
            },
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert workspace_response.status_code == 403
    assert global_response.status_code == 403


@pytest.mark.asyncio
async def test_team_member_cannot_bind_provider_to_server_environment(
    async_client,
    app,
    monkeypatch,
):
    monkeypatch.setattr(settings, "auth_mode", "team")
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setenv("DATABASE_URL", "server-secret-value")
    app.dependency_overrides[get_current_user] = lambda: _auth_user(
        user_id="member-1",
        role="member",
    )
    try:
        created = await async_client.post(
            "/api/v1/llm/providers",
            json={
                "name": "Member provider",
                "kind": "openai_compatible",
                "base_url": "https://1.1.1.1/v1",
            },
        )
        assert created.status_code == 201

        response = await async_client.put(
            f"/api/v1/llm/providers/{created.json()['data']['id']}/credential",
            json={"source": "env", "env_var_name": "DATABASE_URL"},
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 403
    assert "DATABASE_URL" not in response.text
    assert "server-secret-value" not in response.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "base_url",
    [
        "http://127.0.0.1:8000/v1",
        "https://10.49.35.231:8000/v1",
        "https://metadata.internal/v1",
    ],
)
async def test_team_member_cannot_configure_internal_provider_endpoint(
    async_client,
    app,
    monkeypatch,
    base_url,
):
    monkeypatch.setattr(settings, "auth_mode", "team")
    monkeypatch.setattr(settings, "auth_enabled", True)
    app.dependency_overrides[get_current_user] = lambda: _auth_user(
        user_id="member-1",
        role="member",
    )
    try:
        response = await async_client.post(
            "/api/v1/llm/providers",
            json={
                "name": "Internal target",
                "kind": "openai_compatible",
                "base_url": base_url,
                "allow_insecure_http": True,
            },
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_team_member_can_save_public_hostname_when_dns_is_unavailable(
    async_client,
    app,
    monkeypatch,
):
    monkeypatch.setattr(settings, "auth_mode", "team")
    monkeypatch.setattr(settings, "auth_enabled", True)

    def dns_unavailable(*args, **kwargs):
        del args, kwargs
        raise OSError("DNS unavailable")

    monkeypatch.setattr("socket.getaddrinfo", dns_unavailable)
    app.dependency_overrides[get_current_user] = lambda: _auth_user(
        user_id="member-1",
        role="member",
    )
    try:
        response = await async_client.post(
            "/api/v1/llm/providers",
            json={
                "name": "Offline-configured relay",
                "kind": "openai_compatible",
                "base_url": "https://relay.example.com/v1",
            },
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 201


@pytest.mark.asyncio
async def test_team_member_cannot_update_provider_to_internal_endpoint(
    async_client,
    app,
    monkeypatch,
):
    monkeypatch.setattr(settings, "auth_mode", "team")
    monkeypatch.setattr(settings, "auth_enabled", True)
    app.dependency_overrides[get_current_user] = lambda: _auth_user(
        user_id="member-1",
        role="member",
    )
    try:
        created = await async_client.post(
            "/api/v1/llm/providers",
            json={
                "name": "Member public relay",
                "kind": "openai_compatible",
                "base_url": "https://1.1.1.1/v1",
            },
        )
        assert created.status_code == 201

        response = await async_client.patch(
            f"/api/v1/llm/providers/{created.json()['data']['id']}",
            json={"base_url": "https://127.0.0.1:8443/v1"},
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_team_admin_can_configure_internal_provider_and_env_credential(
    async_client,
    app,
    monkeypatch,
):
    monkeypatch.setattr(settings, "auth_mode", "team")
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setenv("INTERNAL_RELAY_API_KEY", "admin-managed-secret")
    app.dependency_overrides[get_current_user] = lambda: _auth_user(
        user_id="admin-1",
        role="admin",
    )
    try:
        created = await async_client.post(
            "/api/v1/llm/providers",
            json={
                "name": "Admin internal relay",
                "kind": "openai_compatible",
                "base_url": "http://relay.internal:8000/v1",
            },
        )
        assert created.status_code == 201

        credential = await async_client.put(
            f"/api/v1/llm/providers/{created.json()['data']['id']}/credential",
            json={
                "source": "env",
                "env_var_name": "INTERNAL_RELAY_API_KEY",
            },
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert credential.status_code == 200
    assert credential.json()["data"]["configured"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["test", "discover-models"])
async def test_team_member_provider_network_operation_rechecks_resolved_target(
    async_client,
    app,
    db_session,
    monkeypatch,
    operation,
):
    monkeypatch.setattr(settings, "auth_mode", "team")
    monkeypatch.setattr(settings, "auth_enabled", True)
    provider = LlmProvider(
        name="Legacy rebinding provider",
        kind="openai_compatible",
        base_url="https://relay.example.com/v1",
        scope="user",
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="member-1",
        enabled=True,
        provider_metadata={"providerTemplate": "openai-compatible"},
    )
    db_session.add(provider)
    await db_session.commit()
    await db_session.refresh(provider)
    await _create_model(
        db_session,
        provider_id=str(provider.id),
        model_id="relay-model",
        display_name="Relay Model",
    )

    network_called = False

    async def forbidden_probe(*args, **kwargs):
        nonlocal network_called
        del args, kwargs
        network_called = True
        raise AssertionError("provider probe must not reach an internal address")

    class ForbiddenAsyncClient:
        def __init__(self, *args, **kwargs):
            nonlocal network_called
            del args, kwargs
            network_called = True
            raise AssertionError("model discovery must not reach an internal address")

    monkeypatch.setattr(
        "app.services.llm.catalog.LlmProviderProbe.probe",
        forbidden_probe,
    )
    monkeypatch.setattr(
        "app.services.llm.catalog.network_policy_http_client",
        _network_client_factory(ForbiddenAsyncClient),
    )
    monkeypatch.setattr(
        "socket.getaddrinfo",
        lambda *args, **kwargs: [
            (2, 1, 6, "", ("127.0.0.1", 0)),
        ],
    )
    app.dependency_overrides[get_current_user] = lambda: _auth_user(
        user_id="member-1",
        role="member",
    )
    try:
        response = await async_client.post(
            f"/api/v1/llm/providers/{provider.id}/{operation}",
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 403
    assert network_called is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("user_id", "role", "scope"),
    [
        ("member-1", "member", "user"),
        ("admin-1", "admin", "workspace"),
    ],
)
async def test_public_provider_probe_and_discovery_receive_public_only_network_policy(
    async_client,
    app,
    db_session,
    monkeypatch,
    user_id,
    role,
    scope,
):
    monkeypatch.setattr(settings, "auth_mode", "team")
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(
        settings,
        "bioinfoflow_credential_key",
        "toeJrhzrLxTdxucwNbNOwVZJZL-EBwrBByLlWJXzTEw=",
    )
    monkeypatch.setattr(
        "socket.getaddrinfo",
        lambda *args, **kwargs: [(2, 1, 6, "", ("1.1.1.1", 443))],
    )
    provider = LlmProvider(
        name=f"{scope} public network provider",
        kind="openai_compatible",
        base_url="https://relay.example.com/v1",
        scope=scope,
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id=(user_id if scope == "user" else None),
        enabled=True,
        provider_metadata={"providerTemplate": "openai-compatible"},
    )
    db_session.add(provider)
    await db_session.commit()
    await db_session.refresh(provider)
    model = await _create_model(
        db_session,
        provider_id=str(provider.id),
        model_id="relay-model",
        display_name="Relay Model",
    )
    probe_policies: list[str] = []
    discovery_policies: list[str] = []

    class FakeProbeResult:
        def to_public_dict(self):
            return {
                "success": True,
                "latency_ms": 1,
                "wire_protocol": "chat_completions",
                "model_id": "relay-model",
                "error_code": None,
                "error_message": None,
                "retryable": False,
                "http_status": None,
                "provider_code": None,
            }

    async def fake_probe(*args, **kwargs):
        del args
        probe_policies.append(kwargs["network_access"])
        return FakeProbeResult()

    async def fake_discovery(self, selected_provider, *, timeout=10.0, network_access):
        del self, selected_provider, timeout
        discovery_policies.append(network_access)
        return []

    monkeypatch.setattr(
        "app.services.llm.catalog.LlmProviderProbe.probe",
        fake_probe,
    )
    monkeypatch.setattr(
        "app.services.llm.catalog.LlmCatalogService.discover_models_unchecked",
        fake_discovery,
    )
    app.dependency_overrides[get_current_user] = lambda: _auth_user(
        user_id=user_id,
        role=role,
    )
    try:
        tested = await async_client.post(
            f"/api/v1/llm/providers/{provider.id}/test",
            json={"model_id": str(model.id)},
        )
        discovered = await async_client.post(
            f"/api/v1/llm/providers/{provider.id}/discover-models",
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert tested.status_code == 200, tested.text
    assert discovered.status_code == 200, discovered.text
    assert probe_policies == ["public_only"]
    assert discovery_policies == ["public_only"]


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["test", "discover-models"])
async def test_team_member_cannot_use_legacy_server_environment_credential(
    async_client,
    app,
    db_session,
    monkeypatch,
    operation,
):
    monkeypatch.setattr(settings, "auth_mode", "team")
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setenv("DATABASE_URL", "legacy-server-secret")
    provider = LlmProvider(
        name="Legacy env provider",
        kind="openai_compatible",
        base_url="https://1.1.1.1/v1",
        scope="user",
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="member-1",
        enabled=True,
        provider_metadata={"providerTemplate": "openai-compatible"},
    )
    db_session.add(provider)
    await db_session.flush()
    db_session.add(
        LlmProviderCredential(
            provider_id=str(provider.id),
            source="env",
            env_var_name="DATABASE_URL",
            masked_hint="env:DATABASE_URL",
            updated_by="member-1",
        )
    )
    await db_session.commit()
    await db_session.refresh(provider)
    await _create_model(
        db_session,
        provider_id=str(provider.id),
        model_id="legacy-model",
        display_name="Legacy Model",
    )

    network_called = False

    async def forbidden_probe(*args, **kwargs):
        nonlocal network_called
        del args, kwargs
        network_called = True
        raise AssertionError("provider probe must not use a server env credential")

    class ForbiddenAsyncClient:
        def __init__(self, *args, **kwargs):
            nonlocal network_called
            del args, kwargs
            network_called = True
            raise AssertionError("model discovery must not use a server env credential")

    monkeypatch.setattr(
        "app.services.llm.catalog.LlmProviderProbe.probe",
        forbidden_probe,
    )
    monkeypatch.setattr(
        "app.services.llm.catalog.network_policy_http_client",
        _network_client_factory(ForbiddenAsyncClient),
    )
    monkeypatch.setattr(
        "socket.getaddrinfo",
        lambda *args, **kwargs: [(2, 1, 6, "", ("1.1.1.1", 0))],
    )
    app.dependency_overrides[get_current_user] = lambda: _auth_user(
        user_id="member-1",
        role="member",
    )
    try:
        response = await async_client.post(
            f"/api/v1/llm/providers/{provider.id}/{operation}",
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 403
    assert network_called is False
    assert "DATABASE_URL" not in response.text
    assert "legacy-server-secret" not in response.text


@pytest.mark.asyncio
async def test_user_cannot_update_or_test_another_users_provider(
    async_client,
    app,
    db_session,
):
    other_provider = await _create_provider(
        db_session,
        name="Other user provider",
        user_id="other-user",
    )
    app.dependency_overrides[get_current_user] = lambda: _auth_user(
        user_id="user-1",
        role="owner",
    )
    try:
        update_response = await async_client.patch(
            f"/api/v1/llm/providers/{other_provider.id}",
            json={"name": "Compromised"},
        )
        test_response = await async_client.post(
            f"/api/v1/llm/providers/{other_provider.id}/test",
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert update_response.status_code == 403
    assert test_response.status_code == 403


@pytest.mark.asyncio
async def test_models_are_limited_to_visible_providers(async_client, app, db_session):
    own_provider = await _create_provider(db_session, name="Own provider")
    own_model = await _create_model(
        db_session,
        provider_id=str(own_provider.id),
        model_id="own-model",
        display_name="Own Model",
    )
    other_provider = await _create_provider(
        db_session,
        name="Other provider",
        user_id="other-user",
    )
    other_model = await _create_model(
        db_session,
        provider_id=str(other_provider.id),
        model_id="other-model",
        display_name="Other Model",
    )

    app.dependency_overrides[get_current_user] = lambda: _auth_user(
        user_id="user-1",
        role="owner",
    )
    try:
        list_response = await async_client.get("/api/v1/llm/models")
        filtered_response = await async_client.get(
            "/api/v1/llm/models",
            params={"provider_id": str(other_provider.id)},
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert list_response.status_code == 200
    model_ids = [item["id"] for item in list_response.json()["data"]]
    assert str(own_model.id) in model_ids
    assert str(other_model.id) not in model_ids
    assert filtered_response.status_code == 403


@pytest.mark.asyncio
async def test_model_and_profile_writes_reject_invisible_dependencies(
    async_client,
    app,
    db_session,
):
    own_provider = await _create_provider(db_session, name="Own dependency provider")
    own_model = await _create_model(
        db_session,
        provider_id=str(own_provider.id),
        model_id="own-dependency-model",
        display_name="Own Dependency Model",
    )
    profile = await _create_profile(
        db_session,
        name="Own profile",
        primary_model_id=str(own_model.id),
    )
    other_provider = await _create_provider(
        db_session,
        name="Other dependency provider",
        user_id="other-user",
    )
    other_model = await _create_model(
        db_session,
        provider_id=str(other_provider.id),
        model_id="other-dependency-model",
        display_name="Other Dependency Model",
    )

    app.dependency_overrides[get_current_user] = lambda: _auth_user(
        user_id="user-1",
        role="owner",
    )
    try:
        create_model_response = await async_client.post(
            "/api/v1/llm/models",
            json={
                "provider_id": str(other_provider.id),
                "model_id": "bad-model",
                "display_name": "Bad Model",
            },
        )
        create_profile_response = await async_client.post(
            "/api/v1/llm/model-profiles",
            json={
                "name": "Bad profile",
                "task_type": "agent_core",
                "primary_model_id": str(other_model.id),
            },
        )
        update_profile_response = await async_client.patch(
            f"/api/v1/llm/model-profiles/{profile.id}",
            json={"primary_model_id": str(other_model.id)},
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert create_model_response.status_code == 403
    assert create_profile_response.status_code == 403
    assert update_profile_response.status_code == 403
