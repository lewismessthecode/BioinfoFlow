from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_list_providers_returns_registry_metadata(async_client):
    resp = await async_client.get("/api/v1/providers")

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert isinstance(body["data"], list)

    providers = {provider["id"]: provider for provider in body["data"]}
    assert "openai" in providers
    assert "anthropic" in providers

    openai = providers["openai"]
    assert openai["label"] == "OpenAI"
    assert openai["credential_type"] == "api_key_and_base_url"
    assert openai["credential_fields"] == ["api_key", "base_url"]
    assert openai["default_model"] == "gpt-5.4"
    assert any(model["id"] == "gpt-5.4" for model in openai["models"])

    anthropic = providers["anthropic"]
    assert anthropic["credential_fields"] == ["api_key"]
    assert anthropic["base_url"] is None
