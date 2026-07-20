from __future__ import annotations

from typing import Any

import pytest

from app.services.llm.provider_templates import route_provider_model_name
from app.services.model_runtime.codecs.chat_completions import ChatCompletionsCodec
from app.services.model_runtime.codecs.responses import ResponsesCodec
from app.services.model_runtime.contracts import ModelInvocation, ModelTarget, TextPart
from app.services.model_runtime.gateway import ModelGateway


class CapturingBackend:
    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []

    async def invoke(
        self,
        wire_protocol: str,
        request: dict[str, Any],
        *,
        network_access: str = "unrestricted",
    ) -> dict[str, Any]:
        assert network_access == "unrestricted"
        self.requests.append(request)
        if wire_protocol == "responses":
            return {"id": "response-1", "status": "completed", "output": []}
        return {
            "id": "response-1",
            "choices": [
                {
                    "message": {"content": "ok"},
                    "finish_reason": "stop",
                }
            ],
        }


def _invocation(
    provider_kind: str,
    model_name: str,
    *,
    wire_protocol: str = "chat_completions",
) -> ModelInvocation:
    return ModelInvocation(
        target=ModelTarget(
            endpoint_id=f"{provider_kind}-endpoint",
            provider_kind=provider_kind,
            model_name=model_name,
            routed_model_name=route_provider_model_name(
                provider_kind,
                model_name,
                wire_protocol=wire_protocol,
            ),
            wire_protocol=wire_protocol,
        ),
        instructions="Reply with OK.",
        input_items=(TextPart(text="ping"),),
        tools=(),
        stream=False,
        max_output_tokens=16,
    )


def test_kimi_models_route_through_openai_compatibility_by_default() -> None:
    assert route_provider_model_name("kimi", "kimi-k2") == "openai/kimi-k2"
    assert route_provider_model_name("kimi_cn", "kimi-k2") == "openai/kimi-k2"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider_kind", "model_name", "expected_request_model"),
    [
        ("openai", "gpt-test", "gpt-test"),
        ("anthropic", "claude-test", "anthropic/claude-test"),
        ("deepseek", "deepseek-test", "deepseek/deepseek-test"),
        ("gemini", "gemini-test", "gemini/gemini-test"),
        ("grok", "grok-test", "xai/grok-test"),
        ("groq", "groq-test", "groq/groq-test"),
        ("ollama", "qwen3:8b", "ollama_chat/qwen3:8b"),
        ("openai_compatible", "gpt-test", "openai/gpt-test"),
        ("openrouter", "openrouter-test", "openrouter/openrouter-test"),
        ("vllm", "served-model", "openai/served-model"),
        ("kimi", "kimi-test", "openai/kimi-test"),
        ("kimi_cn", "kimi-test", "openai/kimi-test"),
        ("qwen", "qwen-test", "openai/qwen-test"),
        ("mistral", "mistral-test", "openai/mistral-test"),
        ("cohere", "command-test", "openai/command-test"),
        ("together", "llama-test", "openai/llama-test"),
        ("fireworks", "fireworks-test", "openai/fireworks-test"),
        ("perplexity", "sonar-test", "perplexity/sonar-test"),
        ("azure", "deployment-name", "azure/deployment-name"),
        ("azure", "azure/deployment-name", "azure/deployment-name"),
        ("minimax", "minimax-test", "minimax-test"),
    ],
)
async def test_registry_routing_flows_through_codec_and_gateway(
    provider_kind: str,
    model_name: str,
    expected_request_model: str,
) -> None:
    backend = CapturingBackend()
    gateway = ModelGateway(backend=backend, codecs=[ChatCompletionsCodec()])

    events = [event async for event in gateway.invoke(_invocation(provider_kind, model_name))]

    assert events
    assert backend.requests[0]["model"] == expected_request_model


@pytest.mark.asyncio
@pytest.mark.parametrize("provider_kind", ["openai", "openai_compatible"])
async def test_registry_preserves_responses_model_routing(
    provider_kind: str,
) -> None:
    backend = CapturingBackend()
    gateway = ModelGateway(backend=backend, codecs=[ResponsesCodec()])

    events = [
        event
        async for event in gateway.invoke(
            _invocation(provider_kind, "gpt-test", wire_protocol="responses")
        )
    ]

    assert events
    assert backend.requests[0]["model"] == "openai/gpt-test"


@pytest.mark.asyncio
async def test_unknown_provider_kind_fails_before_gateway_invocation() -> None:
    backend = CapturingBackend()
    gateway = ModelGateway(backend=backend, codecs=[ChatCompletionsCodec()])

    with pytest.raises(ValueError, match="Unsupported LLM provider kind"):
        await anext(gateway.invoke(_invocation("unknown_provider", "model")))

    assert backend.requests == []
