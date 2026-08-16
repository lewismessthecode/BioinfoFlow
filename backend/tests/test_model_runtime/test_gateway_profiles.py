from collections.abc import AsyncIterator

import pytest

from app.services.llm.credentials import CredentialMaterial
from app.services.llm.target_resolution import resolve_model_target
from app.services.model_runtime.contracts import (
    ModelInvocation,
    ModelTarget,
    ReasoningRequest,
)
from app.services.model_runtime.gateway import ModelGateway


class CapturingBackend:
    def __init__(self) -> None:
        self.request = None

    async def invoke(self, wire_protocol, request, *, network_access):
        del wire_protocol, network_access
        self.request = request
        return EmptyStream()


class EmptyStream:
    def __aiter__(self) -> AsyncIterator[dict]:
        return self

    async def __anext__(self) -> dict:
        raise StopAsyncIteration

    async def aclose(self) -> None:
        return None


@pytest.mark.asyncio
async def test_gateway_applies_provider_profile_before_backend() -> None:
    backend = CapturingBackend()
    gateway = ModelGateway(backend=backend)
    invocation = ModelInvocation(
        target=ModelTarget(
            endpoint_id="provider-1",
            provider_kind="kimi_code",
            model_name="kimi-for-coding",
            routed_model_name="openai/kimi-for-coding",
            wire_protocol="chat_completions",
        ),
        instructions="",
        input_items=(),
        tools=(),
        stream=True,
        max_output_tokens=100,
        reasoning=ReasoningRequest(enabled=True, effort="high"),
    )

    async for _ in gateway.invoke(invocation):
        pass

    assert backend.request["extra_body"]["thinking"] == {"type": "enabled"}
    assert backend.request["max_completion_tokens"] == 100
    assert "thinking" not in backend.request
    assert "reasoning_effort" not in backend.request
    assert "max_tokens" not in backend.request


@pytest.mark.asyncio
async def test_deepseek_registry_endpoint_reaches_backend_as_explicit_api_base(
    monkeypatch,
) -> None:
    async def public_network_access(base_url, **kwargs):
        del kwargs
        assert base_url == "https://api.deepseek.com/v1"
        return "public_only"

    monkeypatch.setattr(
        "app.services.llm.target_resolution.resolve_provider_network_access",
        public_network_access,
    )
    target = await resolve_model_target(
        endpoint_id="provider-deepseek",
        provider_kind="deepseek",
        model_name="deepseek-chat",
        wire_protocol="chat_completions",
        base_url=None,
        provider_metadata=None,
        credential=CredentialMaterial(api_key="secret", source="stored"),
        private_endpoint_authorized=False,
        resolve_dns=True,
    )
    backend = CapturingBackend()

    async for _ in ModelGateway(backend=backend).invoke(
        ModelInvocation(
            target=target,
            instructions="",
            input_items=(),
            tools=(),
            stream=False,
            max_output_tokens=16,
            reasoning=ReasoningRequest(enabled=False),
        )
    ):
        pass

    assert backend.request["model"] == "deepseek/deepseek-chat"
    assert backend.request["api_base"] == "https://api.deepseek.com/v1"
    assert backend.request["api_key"] == "secret"
