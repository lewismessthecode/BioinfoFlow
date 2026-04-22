"""Tests for runtime/llm_client.py — DeterministicTestClient + LLMResponse."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.agent.runtime.llm_client import (
    DeterministicTestClient,
    LLMResponse,
    LLMProviderAttempt,
    _is_retryable_llm_exception,
)


@pytest.mark.asyncio
async def test_deterministic_first_call_requests_tool():
    client = DeterministicTestClient()
    response = await client.create(
        system="test", messages=[], tools=[{"name": "glob"}]
    )
    assert isinstance(response, LLMResponse)
    assert response.stop_reason == "tool_use"
    assert len(response.tool_calls) == 1
    assert response.tool_calls[0]["name"] == "glob"
    assert response.content == ""


@pytest.mark.asyncio
async def test_deterministic_second_call_returns_text():
    client = DeterministicTestClient()
    # First call
    await client.create(system="test", messages=[], tools=[])
    # Second call
    response = await client.create(system="test", messages=[], tools=[])
    assert response.stop_reason == "end_turn"
    assert "scanned" in response.content.lower()
    assert response.tool_calls == []


@pytest.mark.asyncio
async def test_deterministic_usage_tracking():
    client = DeterministicTestClient()
    response = await client.create(system="test", messages=[], tools=[])
    assert response.usage["input_tokens"] > 0
    assert response.usage["output_tokens"] > 0


@pytest.mark.asyncio
async def test_deterministic_custom_responses():
    custom = [
        LLMResponse(content="first", stop_reason="end_turn"),
        LLMResponse(content="second", stop_reason="end_turn"),
    ]
    client = DeterministicTestClient(responses=custom)
    r1 = await client.create(system="test", messages=[])
    assert r1.content == "first"
    r2 = await client.create(system="test", messages=[])
    assert r2.content == "second"
    # Third call cycles the last response
    r3 = await client.create(system="test", messages=[])
    assert r3.content == "second"


class TestLLMResponse:
    def test_defaults(self):
        response = LLMResponse(content="hi")
        assert response.stop_reason == "end_turn"
        assert response.tool_calls == []
        assert response.usage == {"input_tokens": 0, "output_tokens": 0}
        assert response.thinking is None

    def test_with_tool_calls(self):
        response = LLMResponse(
            content="",
            tool_calls=[{"id": "tc_1", "name": "glob", "input": {}}],
            stop_reason="tool_use",
        )
        assert response.stop_reason == "tool_use"
        assert len(response.tool_calls) == 1

    def test_with_thinking(self):
        response = LLMResponse(
            content="answer",
            stop_reason="end_turn",
            thinking="step by step reasoning",
        )
        assert response.thinking == "step by step reasoning"


def test_retryable_llm_exception_detects_vertex_and_midstream_failures():
    midstream_error = RuntimeError(
        "litellm.MidStreamFallbackError: Vertex_ai_betaException - 503 Service Unavailable"
    )
    service_unavailable = type("ServiceUnavailableError", (Exception,), {})(
        "high demand"
    )

    assert _is_retryable_llm_exception(midstream_error) is True
    assert _is_retryable_llm_exception(service_unavailable) is True


@pytest.mark.asyncio
async def test_llm_client_builds_fallback_attempts_from_user_and_env(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "env-openai-key")

    from app.services.agent.runtime.llm_client import LLMClient

    client = LLMClient()
    user_settings = SimpleNamespace(
        provider_credentials='{"gemini":{"api_key":"g-key"},"anthropic":{"api_key":"a-key"}}',
        selected_provider="gemini",
        selected_model="gemini-2.5-flash",
    )

    attempts = client._resolve_provider_attempts(user_settings)

    assert [attempt.provider for attempt in attempts[:3]] == [
        "gemini",
        "anthropic",
        "openai",
    ]
    assert attempts[0].model == "gemini-2.5-flash"
    assert isinstance(attempts[0], LLMProviderAttempt)
