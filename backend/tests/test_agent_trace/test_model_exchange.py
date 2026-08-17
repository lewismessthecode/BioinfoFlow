from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest

from app.services.model_runtime.contracts import (
    CompletionMetadata,
    ModelInvocation,
    ModelTarget,
)
from app.services.model_runtime.gateway import ModelGateway


class RecordingObserver:
    def __init__(self) -> None:
        self.requests: list[tuple[str, dict | list]] = []
        self.responses: list[tuple[str, dict | list]] = []

    async def request_prepared(self, exchange_id: str, payload: dict | list) -> None:
        self.requests.append((exchange_id, payload))

    async def response_received(self, exchange_id: str, payload: dict | list) -> None:
        self.responses.append((exchange_id, payload))


@pytest.mark.asyncio
async def test_gateway_observer_records_provider_payload_without_transport_secrets() -> (
    None
):
    raw_response = {"id": "resp-1", "output": [{"type": "message"}]}

    class FakeCodec:
        wire_protocol = "responses"

        def encode_request(self, invocation: ModelInvocation) -> dict[str, Any]:
            return {
                "model": invocation.target.model_name,
                "input": [{"role": "user", "content": "hello"}],
            }

        async def decode_response(self, response: Any) -> AsyncIterator[object]:
            assert response is raw_response
            yield CompletionMetadata(response_id="resp-1", finish_reason="completed")

    class FakeBackend:
        async def invoke(self, wire_protocol, request, *, network_access):
            assert wire_protocol == "responses"
            assert request["api_key"] == "secret-value"
            assert request["api_base"] == "https://models.example/v1"
            assert network_access == "unrestricted"
            return raw_response

    observer = RecordingObserver()
    gateway = ModelGateway(
        backend=FakeBackend(),
        codecs=[FakeCodec()],
        exchange_observer=observer,
    )
    invocation = ModelInvocation(
        target=ModelTarget(
            endpoint_id="endpoint-1",
            provider_kind="unknown-provider",
            model_name="gpt-5",
            routed_model_name="gpt-5",
            wire_protocol="responses",
            base_url="https://models.example/v1",
            api_key="secret-value",
        ),
        instructions="",
        input_items=(),
        tools=(),
        stream=False,
        max_output_tokens=128,
        exchange_id="trace-1",
    )

    events = [event async for event in gateway.invoke(invocation)]

    assert events[-1] == CompletionMetadata(
        response_id="resp-1", finish_reason="completed"
    )
    assert observer.requests == [
        (
            "trace-1",
            {
                "model": "gpt-5",
                "input": [{"role": "user", "content": "hello"}],
            },
        )
    ]
    assert observer.responses == [("trace-1", raw_response)]


@pytest.mark.asyncio
async def test_gateway_observer_failure_does_not_change_model_result(caplog) -> None:
    secret = "trace-storage-secret"
    raw_response = {"id": "resp-1"}

    class FakeCodec:
        wire_protocol = "responses"

        def encode_request(self, invocation: ModelInvocation) -> dict[str, Any]:
            return {"model": invocation.target.model_name, "input": []}

        async def decode_response(self, response: Any) -> AsyncIterator[object]:
            assert response is raw_response
            yield CompletionMetadata(response_id="resp-1", finish_reason="completed")

    class FakeBackend:
        async def invoke(self, wire_protocol, request, *, network_access):
            return raw_response

    class FailingObserver:
        def __init__(self) -> None:
            self.callbacks: list[str] = []

        async def request_prepared(self, exchange_id, payload) -> None:
            self.callbacks.append("request_prepared")
            raise RuntimeError(secret)

        async def response_received(self, exchange_id, payload) -> None:
            self.callbacks.append("response_received")
            raise RuntimeError(secret)

    observer = FailingObserver()
    gateway = ModelGateway(
        backend=FakeBackend(),
        codecs=[FakeCodec()],
        exchange_observer=observer,
    )
    invocation = ModelInvocation(
        target=ModelTarget(
            endpoint_id="endpoint-1",
            provider_kind="unknown-provider",
            model_name="gpt-5",
            routed_model_name="gpt-5",
            wire_protocol="responses",
        ),
        instructions="",
        input_items=(),
        tools=(),
        stream=False,
        max_output_tokens=128,
        exchange_id="trace-1",
    )

    events = [event async for event in gateway.invoke(invocation)]

    assert events[-1] == CompletionMetadata(
        response_id="resp-1", finish_reason="completed"
    )
    assert observer.callbacks == ["request_prepared", "response_received"]
    assert secret not in caplog.text
