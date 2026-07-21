from collections.abc import AsyncIterator

import pytest

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
