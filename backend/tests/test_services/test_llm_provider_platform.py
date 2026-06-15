from __future__ import annotations

import httpx
import pytest

from app.models.llm import LlmModel, LlmProvider, LlmProviderCredential
from app.services.llm.bootstrap import sync_environment_llm_catalog


async def _noop_discovery(self, provider):
    return []


@pytest.mark.asyncio
async def test_simple_vllm_environment_profile_bootstraps_catalog(
    db_session,
    monkeypatch,
):
    monkeypatch.setenv("VLLM_BASE_URL", "http://vllm.internal.test:8000/v1")
    monkeypatch.setenv("VLLM_API_KEY", "vllm")
    monkeypatch.setenv("VLLM_MODEL", "deepseek_v4")
    monkeypatch.delenv("OPENAI_COMPATIBLE_PROVIDERS", raising=False)
    monkeypatch.setattr(
        "app.services.llm.bootstrap.LlmCatalogService.discover_models_unchecked",
        _noop_discovery,
    )

    result = await sync_environment_llm_catalog(db_session)

    assert result.created_or_updated >= 1

    providers = [
        provider
        for provider in (await db_session.execute(LlmProvider.__table__.select())).mappings()
        if provider["kind"] == "vllm"
    ]
    assert len(providers) == 1
    provider = providers[0]
    assert provider["name"] == "vLLM"
    assert provider["base_url"] == "http://vllm.internal.test:8000/v1"
    assert provider["scope"] == "global"
    assert provider["metadata"]["envManaged"] is True
    assert provider["metadata"]["providerTemplate"] == "vllm"

    credential = (
        await db_session.execute(LlmProviderCredential.__table__.select())
    ).mappings().one()
    assert credential["provider_id"] == provider["id"]
    assert credential["source"] == "env"
    assert credential["env_var_name"] == "VLLM_API_KEY"
    assert credential["masked_hint"] == "env:VLLM_API_KEY"

    model = (await db_session.execute(LlmModel.__table__.select())).mappings().one()
    assert model["provider_id"] == provider["id"]
    assert model["model_id"] == "deepseek_v4"
    assert model["display_name"] == "deepseek_v4"


@pytest.mark.asyncio
async def test_environment_bootstrap_does_not_overwrite_user_configured_provider(
    db_session,
    monkeypatch,
):
    user_provider = LlmProvider(
        name="vLLM",
        kind="vllm",
        base_url="http://ui.example.test/v1",
        scope="user",
        workspace_id="00000000-0000-0000-0000-000000000001",
        user_id="user-1",
        enabled=True,
        provider_metadata={"providerTemplate": "vllm"},
    )
    db_session.add(user_provider)
    await db_session.commit()

    monkeypatch.setenv("VLLM_BASE_URL", "http://env.example.test/v1")
    monkeypatch.setenv("VLLM_API_KEY", "env-key")
    monkeypatch.setenv("VLLM_MODEL", "env-model")
    monkeypatch.setattr(
        "app.services.llm.bootstrap.LlmCatalogService.discover_models_unchecked",
        _noop_discovery,
    )

    await sync_environment_llm_catalog(db_session)

    await db_session.refresh(user_provider)
    assert user_provider.base_url == "http://ui.example.test/v1"

    providers = (
        await db_session.execute(LlmProvider.__table__.select())
    ).mappings().all()
    assert any(
        provider["scope"] == "global"
        and provider["base_url"] == "http://env.example.test/v1"
        for provider in providers
    )


@pytest.mark.asyncio
async def test_environment_bootstrap_runs_live_discovery(db_session, monkeypatch):
    monkeypatch.setenv("VLLM_BASE_URL", "http://vllm.internal.test:8000/v1")
    monkeypatch.setenv("VLLM_API_KEY", "vllm")
    monkeypatch.delenv("VLLM_MODEL", raising=False)

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def get(self, url: str, headers=None, params=None):
            return httpx.Response(
                200,
                json={"data": [{"id": "bootstrap-model", "object": "model"}]},
                request=httpx.Request("GET", url),
            )

    monkeypatch.setattr(
        "app.services.llm.catalog.httpx.AsyncClient", FakeAsyncClient
    )

    await sync_environment_llm_catalog(db_session)

    models = (await db_session.execute(LlmModel.__table__.select())).mappings().all()
    assert any(model["model_id"] == "bootstrap-model" for model in models)


@pytest.mark.asyncio
async def test_environment_bootstrap_swallows_discovery_errors(db_session, monkeypatch):
    monkeypatch.setenv("VLLM_BASE_URL", "http://vllm.internal.test:8000/v1")
    monkeypatch.setenv("VLLM_API_KEY", "vllm")
    monkeypatch.setenv("VLLM_MODEL", "deepseek_v4")

    async def _boom(self, provider):
        raise httpx.ConnectError("no route to host")

    monkeypatch.setattr(
        "app.services.llm.bootstrap.LlmCatalogService.discover_models_unchecked",
        _boom,
    )

    # Discovery failure must not break startup bootstrap.
    await sync_environment_llm_catalog(db_session)

    model = (await db_session.execute(LlmModel.__table__.select())).mappings().one()
    assert model["model_id"] == "deepseek_v4"
