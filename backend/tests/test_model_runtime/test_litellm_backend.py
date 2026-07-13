from __future__ import annotations

import traceback
from collections.abc import AsyncIterator
from typing import Any

import pytest

from app.services.model_runtime.backend.litellm import LiteLLMBackend
from app.services.model_runtime.contracts import ModelInvocation, ModelTarget
from app.services.model_runtime.errors import ModelError
from app.services.model_runtime.gateway import ModelGateway


@pytest.mark.asyncio
async def test_chat_backend_calls_injected_acompletion_once_with_retries_disabled():
    calls: list[dict[str, Any]] = []
    response = object()

    async def fake_acompletion(**kwargs: Any) -> object:
        calls.append(kwargs)
        return response

    backend = LiteLLMBackend(acompletion_fn=fake_acompletion)

    result = await backend.invoke(
        "chat_completions",
        {
            "model": "openai/gpt-test",
            "messages": [{"role": "user", "content": "ping"}],
            "api_key": "secret-value",
            "num_retries": 8,
        },
    )

    assert result is response
    assert calls == [
        {
            "model": "openai/gpt-test",
            "messages": [{"role": "user", "content": "ping"}],
            "api_key": "secret-value",
            "num_retries": 0,
        }
    ]


@pytest.mark.asyncio
async def test_gateway_dispatches_chat_through_registered_codec_and_backend():
    invocation = ModelInvocation(
        target=ModelTarget(
            endpoint_id="endpoint-1",
            provider_kind="openai",
            model_name="gpt-test",
            wire_protocol="chat_completions",
            base_url="https://models.example/v1",
            api_key="secret-value",
        ),
        instructions="Reply briefly.",
        input_items=(),
        tools=(),
        stream=False,
        max_output_tokens=128,
    )
    encoded_request = {"model": "openai/gpt-test", "messages": []}
    raw_response = object()
    event = object()

    class FakeCodec:
        wire_protocol = "chat_completions"

        def encode_request(self, received: ModelInvocation) -> dict[str, Any]:
            assert received is invocation
            return encoded_request

        async def decode_response(self, response: Any) -> AsyncIterator[object]:
            assert response is raw_response
            yield event

    class FakeBackend:
        def __init__(self) -> None:
            self.calls: list[tuple[str, dict[str, Any]]] = []

        async def invoke(self, wire_protocol: str, request: dict[str, Any]) -> Any:
            self.calls.append((wire_protocol, request))
            return raw_response

    backend = FakeBackend()
    gateway = ModelGateway(backend=backend, codecs=[FakeCodec()])

    events = [item async for item in gateway.invoke(invocation)]

    assert events == [event]
    assert backend.calls == [
        (
            "chat_completions",
            {
                **encoded_request,
                "api_base": "https://models.example/v1",
                "api_key": "secret-value",
            },
        )
    ]


@pytest.mark.asyncio
async def test_backend_redacts_credentials_from_normalized_errors_and_repr():
    secret = "sentinel-secret-never-expose"

    async def failing_acompletion(**kwargs: Any) -> object:
        raise RuntimeError(f"upstream rejected api_key={kwargs['api_key']}")

    backend = LiteLLMBackend(acompletion_fn=failing_acompletion)

    with pytest.raises(ModelError) as caught:
        await backend.invoke(
            "chat_completions",
            {
                "model": "openai/gpt-test",
                "messages": [],
                "api_key": secret,
            },
        )

    error = caught.value
    assert secret not in str(error)
    assert secret not in repr(error)
    assert secret not in repr(backend)
    assert secret not in str(error.to_public_dict())


@pytest.mark.asyncio
async def test_backend_suppresses_secret_bearing_provider_exception_chain(caplog):
    secret = "sentinel-secret-never-render"
    provider_error = RuntimeError(f"provider request used api_key={secret}")

    async def failing_acompletion(**kwargs: Any) -> object:
        del kwargs
        raise provider_error

    backend = LiteLLMBackend(acompletion_fn=failing_acompletion)

    with pytest.raises(ModelError) as caught:
        await backend.invoke(
            "chat_completions",
            {
                "model": "openai/gpt-test",
                "messages": [],
                "api_key": secret,
            },
        )

    error = caught.value
    rendered_traceback = "".join(traceback.format_exception(error))
    assert error.cause is provider_error
    assert secret not in rendered_traceback
    assert secret not in caplog.text


@pytest.mark.asyncio
async def test_stream_failure_after_event_is_safe_and_not_replayable(caplog):
    secret = "sentinel-stream-secret-never-render"
    provider_error = RuntimeError(f"stream failed with api_key={secret}")
    first_event = object()

    async def provider_stream() -> AsyncIterator[object]:
        yield first_event
        raise provider_error

    async def fake_acompletion(**kwargs: Any) -> object:
        del kwargs
        return provider_stream()

    class PassthroughCodec:
        wire_protocol = "chat_completions"

        def encode_request(self, invocation: ModelInvocation) -> dict[str, Any]:
            del invocation
            return {"model": "openai/gpt-test", "messages": [], "stream": True}

        async def decode_response(self, response: Any) -> AsyncIterator[object]:
            async for item in response:
                yield item

    invocation = ModelInvocation(
        target=ModelTarget(
            endpoint_id="endpoint-1",
            provider_kind="openai",
            model_name="gpt-test",
            wire_protocol="chat_completions",
            api_key=secret,
        ),
        instructions="",
        input_items=(),
        tools=(),
        stream=True,
        max_output_tokens=128,
    )
    gateway = ModelGateway(
        backend=LiteLLMBackend(acompletion_fn=fake_acompletion),
        codecs=[PassthroughCodec()],
    )
    events = gateway.invoke(invocation)

    assert await anext(events) is first_event
    with pytest.raises(ModelError) as caught:
        await anext(events)

    error = caught.value
    rendered_traceback = "".join(traceback.format_exception(error))
    assert error.cause is provider_error
    assert error.replay_safe is False
    assert secret not in rendered_traceback
    assert secret not in caplog.text


def test_gateway_rejects_duplicate_protocol_registration():
    class FakeCodec:
        wire_protocol = "chat_completions"

    with pytest.raises(ValueError, match="chat_completions"):
        ModelGateway(backend=object(), codecs=[FakeCodec(), FakeCodec()])
