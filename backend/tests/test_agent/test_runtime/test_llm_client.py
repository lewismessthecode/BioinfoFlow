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
from app.services.agent.runtime.llm_providers import retry_llm_call


class RateLimitError(Exception):
    pass


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
async def test_retry_llm_call_does_not_retry_depleted_prepay_errors():
    attempts = 0

    async def fail_with_depleted_credits():
        nonlocal attempts
        attempts += 1
        raise RateLimitError("RESOURCE_EXHAUSTED: Your prepayment credits are depleted")

    with pytest.raises(RateLimitError):
        await retry_llm_call(fail_with_depleted_credits)

    assert attempts == 1


@pytest.mark.asyncio
async def test_llm_client_skips_depleted_provider_after_fallback(monkeypatch):
    from app.services.agent.runtime.llm_client import LLMClient
    import litellm

    calls: list[str] = []

    async def fake_completion(**kwargs):
        calls.append(kwargs["model"])
        if kwargs["model"].startswith("gemini/"):
            raise RateLimitError("RESOURCE_EXHAUSTED: Your prepayment credits are depleted")
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content="fallback answer",
                        reasoning_content=None,
                        tool_calls=None,
                    )
                )
            ],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=2),
        )

    monkeypatch.setattr(litellm, "acompletion", fake_completion)

    client = LLMClient()
    client._initialized = True
    client._provider = "gemini"
    client._model = "gemini-3.1-flash-lite-preview"
    client._litellm_model = "gemini/gemini-3.1-flash-lite-preview"
    client._attempts = [
        LLMProviderAttempt(
            provider="gemini",
            model="gemini-3.1-flash-lite-preview",
            litellm_model="gemini/gemini-3.1-flash-lite-preview",
            api_key="g-key",
        ),
        LLMProviderAttempt(
            provider="anthropic",
            model="claude-sonnet-4-6",
            litellm_model="anthropic/claude-sonnet-4-6",
            api_key="a-key",
        ),
    ]

    first = await client.create(system="test", messages=[])
    second = await client.create(system="test", messages=[])

    assert first.content == "fallback answer"
    assert second.content == "fallback answer"
    assert calls == [
        "gemini/gemini-3.1-flash-lite-preview",
        "anthropic/claude-sonnet-4-6",
        "anthropic/claude-sonnet-4-6",
    ]


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


@pytest.mark.asyncio
async def test_llm_client_builds_ollama_as_openai_compatible_endpoint(monkeypatch):
    from app.services.agent.runtime.llm_client import LLMClient

    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")

    client = LLMClient()
    user_settings = SimpleNamespace(
        provider_credentials='{"ollama":{"model":"deepseek-r1:latest"}}',
        selected_provider="ollama",
        selected_model="deepseek-r1:latest",
    )

    attempts = client._resolve_provider_attempts(user_settings)

    assert attempts[0].provider == "ollama"
    assert attempts[0].litellm_model == "openai/deepseek-r1:latest"
    assert attempts[0].api_key == "ollama"
    assert attempts[0].api_base == "http://127.0.0.1:11434/v1"
    assert attempts[0].supports_reasoning_effort is False


def test_llm_client_does_not_send_reasoning_effort_to_plain_compatible_endpoint():
    from app.services.agent.runtime.llm_client import LLMClient

    client = LLMClient()
    attempt = LLMProviderAttempt(
        provider="ollama",
        model="deepseek-r1:latest",
        litellm_model="openai/deepseek-r1:latest",
        api_key="ollama",
        api_base="http://127.0.0.1:11434/v1",
        supports_reasoning_effort=False,
    )

    kwargs = client._build_kwargs(
        attempt=attempt,
        system="test",
        messages=[],
        tools=None,
        max_tokens=8,
        stream=False,
    )

    assert "reasoning_effort" not in kwargs
