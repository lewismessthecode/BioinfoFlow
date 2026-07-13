from __future__ import annotations

import asyncio
import traceback
import socket
from collections.abc import AsyncIterator
from typing import Any

import aiohttp
import httpx
import litellm
import pytest
from yarl import URL

from app.services.model_runtime.backend.litellm import LiteLLMBackend
from app.services.model_runtime.backend.litellm_network import (
    PublicNetworkHTTPHandler,
    PublicNetworkResolver,
    ensure_public_request_url,
    public_network_middleware,
)
from app.services.model_runtime.contracts import (
    ModelInvocation,
    ModelTarget,
    ResponseStarted,
)
from app.services.model_runtime.errors import ModelError
from app.services.model_runtime.gateway import ModelGateway
from app.utils.exceptions import PermissionDeniedError


def _response(
    status_code: int,
    *,
    code: str,
    request_id: str,
    retry_after: str | None = None,
) -> httpx.Response:
    headers = {"x-request-id": request_id}
    if retry_after is not None:
        headers["retry-after"] = retry_after
    return httpx.Response(
        status_code,
        headers=headers,
        json={"error": {"code": code, "message": "raw provider detail"}},
        request=httpx.Request("POST", "https://provider.example/v1/chat/completions"),
    )


async def _normalized_error(provider_error: Exception) -> ModelError:
    async def failing_acompletion(**kwargs: Any) -> object:
        del kwargs
        raise provider_error

    with pytest.raises(ModelError) as caught:
        await LiteLLMBackend(acompletion_fn=failing_acompletion).invoke(
            "chat_completions",
            {"model": "openai/gpt-test", "messages": [], "api_key": "secret-key"},
        )
    return caught.value


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
async def test_responses_backend_calls_injected_aresponses_once_with_retries_disabled():
    calls: list[dict[str, Any]] = []
    response = object()

    async def fail_acompletion(**kwargs: Any) -> object:
        raise AssertionError(f"Chat backend must not be called: {kwargs}")

    async def fake_aresponses(**kwargs: Any) -> object:
        calls.append(kwargs)
        return response

    backend = LiteLLMBackend(
        acompletion_fn=fail_acompletion,
        aresponses_fn=fake_aresponses,
    )

    result = await backend.invoke(
        "responses",
        {
            "model": "openai/gpt-test",
            "input": [{"role": "user", "content": "ping"}],
            "store": False,
            "num_retries": 9,
        },
    )

    assert result is response
    assert calls == [
        {
            "model": "openai/gpt-test",
            "input": [{"role": "user", "content": "ping"}],
            "store": False,
            "num_retries": 0,
        }
    ]


@pytest.mark.asyncio
async def test_public_only_backend_injects_request_scoped_policy_client():
    calls: list[dict[str, Any]] = []

    async def fake_acompletion(**kwargs: Any) -> object:
        calls.append(kwargs)
        return object()

    await LiteLLMBackend(acompletion_fn=fake_acompletion).invoke(
        "chat_completions",
        {"model": "openai/gpt-test", "messages": []},
        network_access="public_only",
    )

    assert len(calls) == 1
    assert calls[0]["client"].network_access == "public_only"
    assert calls[0]["client"].closed is True


@pytest.mark.asyncio
async def test_public_network_resolver_rejects_any_private_dns_answer(monkeypatch):
    monkeypatch.setattr(
        "socket.getaddrinfo",
        lambda *args, **kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("1.1.1.1", 443)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443)),
        ],
    )

    with pytest.raises(PermissionDeniedError, match="public address"):
        await PublicNetworkResolver().resolve("relay.example.com", 443)


@pytest.mark.asyncio
async def test_public_network_resolver_returns_the_exact_validated_connect_address(
    monkeypatch,
):
    calls = 0

    def resolve_once(*args, **kwargs):
        nonlocal calls
        del args, kwargs
        calls += 1
        if calls > 1:
            return [
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))
            ]
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("1.1.1.1", 443))]

    monkeypatch.setattr("socket.getaddrinfo", resolve_once)

    resolved = await PublicNetworkResolver().resolve("relay.example.com", 443)

    assert calls == 1
    assert [item["host"] for item in resolved] == ["1.1.1.1"]


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/admin",
        "http://169.254.169.254/latest/meta-data",
        "https://service.internal/v1/responses",
    ],
)
def test_public_network_request_guard_rejects_private_redirect_destination(url):
    with pytest.raises(PermissionDeniedError, match="public address"):
        ensure_public_request_url(URL(url))


@pytest.mark.asyncio
async def test_public_network_http_handler_blocks_private_literal_before_connect():
    client = PublicNetworkHTTPHandler()
    try:
        with pytest.raises(PermissionDeniedError, match="public address"):
            await client.get("http://127.0.0.1/private")
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_public_only_stream_keeps_policy_client_until_stream_closes():
    captured: list[PublicNetworkHTTPHandler] = []

    async def provider_stream() -> AsyncIterator[object]:
        yield object()

    async def fake_acompletion(**kwargs: Any) -> object:
        captured.append(kwargs["client"])
        return provider_stream()

    response = await LiteLLMBackend(acompletion_fn=fake_acompletion).invoke(
        "chat_completions",
        {"model": "openai/gpt-test", "messages": []},
        network_access="public_only",
    )

    assert captured[0].closed is False
    await anext(response)
    with pytest.raises(StopAsyncIteration):
        await anext(response)
    assert captured[0].closed is True


@pytest.mark.asyncio
async def test_public_network_middleware_rechecks_redirect_destination():
    requests = 0

    async def handle(
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        nonlocal requests
        await reader.readuntil(b"\r\n\r\n")
        requests += 1
        writer.write(
            b"HTTP/1.1 302 Found\r\n"
            b"Location: http://127.0.0.1/private\r\n"
            b"Content-Length: 0\r\n"
            b"Connection: close\r\n\r\n"
        )
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]

    class TestResolver(aiohttp.abc.AbstractResolver):
        async def resolve(self, host, port=0, family=socket.AF_INET):
            return [
                aiohttp.abc.ResolveResult(
                    hostname=host,
                    host="127.0.0.1",
                    port=port,
                    family=family,
                    proto=socket.IPPROTO_TCP,
                    flags=0,
                )
            ]

        async def close(self):
            return None

    connector = aiohttp.TCPConnector(
        resolver=TestResolver(),
        use_dns_cache=False,
    )
    try:
        async with aiohttp.ClientSession(
            connector=connector,
            middlewares=(public_network_middleware,),
        ) as client:
            with pytest.raises(PermissionDeniedError, match="public address"):
                await client.get(f"http://relay.example.com:{port}/start")
    finally:
        server.close()
        await server.wait_closed()

    assert requests == 1


def test_default_gateway_registers_chat_and_responses_codecs() -> None:
    assert repr(ModelGateway()) == "ModelGateway(protocols=[chat_completions, responses])"


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
            self.calls: list[tuple[str, dict[str, Any], str]] = []

        async def invoke(
            self,
            wire_protocol: str,
            request: dict[str, Any],
            *,
            network_access: str = "unrestricted",
        ) -> Any:
            self.calls.append((wire_protocol, request, network_access))
            return raw_response

    backend = FakeBackend()
    gateway = ModelGateway(backend=backend, codecs=[FakeCodec()])

    events = [item async for item in gateway.invoke(invocation)]

    assert events == [ResponseStarted(streaming=False), event]
    assert backend.calls == [
        (
            "chat_completions",
            {
                **encoded_request,
                "api_base": "https://models.example/v1",
                "api_key": "secret-value",
            },
            "unrestricted",
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
async def test_rate_limit_error_preserves_retry_after_and_safe_metadata() -> None:
    error = await _normalized_error(
        litellm.RateLimitError(
            "raw secret-bearing rate-limit message",
            "openai",
            "gpt-test",
            _response(
                429,
                code="rate_limit_exceeded",
                request_id="req-rate-limit",
                retry_after="1.75",
            ),
        )
    )

    assert error.category == "rate_limit"
    assert error.http_status == 429
    assert error.provider_code in {"429", "rate_limit_exceeded"}
    assert error.request_id == "req-rate-limit"
    assert error.retry_after_seconds == 1.75
    assert error.retryable is True
    assert error.replay_safe is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider_error", "category", "status_code"),
    [
        (litellm.Timeout("raw timeout", "gpt-test", "openai"), "timeout", 408),
        (
            litellm.APIConnectionError("raw connection", "openai", "gpt-test"),
            "connection",
            500,
        ),
        (litellm.APIError(502, "raw 502", "openai", "gpt-test"), "service_unavailable", 502),
        (
            litellm.ServiceUnavailableError("raw 503", "openai", "gpt-test"),
            "service_unavailable",
            503,
        ),
        (litellm.APIError(504, "raw 504", "openai", "gpt-test"), "service_unavailable", 504),
    ],
)
async def test_transient_typed_provider_errors_are_retryable(
    provider_error: Exception,
    category: str,
    status_code: int,
) -> None:
    error = await _normalized_error(provider_error)

    assert error.category == category
    assert error.http_status == status_code
    assert error.retryable is True
    assert error.replay_safe is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("provider_error", "category", "status_code", "provider_code", "request_id"),
    [
        (
            litellm.BadRequestError(
                "raw bad request with secret-key",
                "gpt-test",
                "openai",
                _response(400, code="invalid_tool_schema", request_id="req-400"),
                body={"code": "invalid_tool_schema"},
            ),
            "invalid_request",
            400,
            "invalid_tool_schema",
            "req-400",
        ),
        (
            litellm.AuthenticationError(
                "raw auth with secret-key",
                "openai",
                "gpt-test",
                _response(401, code="invalid_api_key", request_id="req-401"),
            ),
            "authentication",
            401,
            "invalid_api_key",
            "req-401",
        ),
        (
            litellm.PermissionDeniedError(
                "raw permission with secret-key",
                "openai",
                "gpt-test",
                _response(403, code="organization_forbidden", request_id="req-403"),
            ),
            "authorization",
            403,
            "organization_forbidden",
            "req-403",
        ),
    ],
)
async def test_client_provider_errors_are_safe_and_nonretryable(
    provider_error: Exception,
    category: str,
    status_code: int,
    provider_code: str,
    request_id: str,
) -> None:
    error = await _normalized_error(provider_error)

    assert error.category == category
    assert error.http_status == status_code
    assert error.provider_code == provider_code
    assert error.request_id == request_id
    assert error.retryable is False
    assert error.replay_safe is True
    assert "secret-key" not in str(error)
    assert "secret-key" not in repr(error.to_public_dict())


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

    assert await anext(events) == ResponseStarted(streaming=True)
    assert await anext(events) is first_event
    with pytest.raises(ModelError) as caught:
        await anext(events)

    error = caught.value
    rendered_traceback = "".join(traceback.format_exception(error))
    assert error.cause is provider_error
    assert error.replay_safe is False
    assert secret not in rendered_traceback
    assert secret not in caplog.text


@pytest.mark.asyncio
async def test_model_error_after_stream_event_is_forced_nonreplayable() -> None:
    first_event = object()

    async def provider_stream() -> AsyncIterator[object]:
        yield first_event
        raise ModelError(
            category="timeout",
            message="The provider timed out.",
            retryable=True,
            replay_safe=True,
        )

    async def fake_acompletion(**kwargs: Any) -> object:
        del kwargs
        return provider_stream()

    response = await LiteLLMBackend(acompletion_fn=fake_acompletion).invoke(
        "chat_completions",
        {"model": "openai/gpt-test", "messages": []},
    )

    assert await anext(response) is first_event
    with pytest.raises(ModelError) as caught:
        await anext(response)

    assert caught.value.category == "timeout"
    assert caught.value.retryable is True
    assert caught.value.replay_safe is False


def test_gateway_rejects_duplicate_protocol_registration():
    class FakeCodec:
        wire_protocol = "chat_completions"

    with pytest.raises(ValueError, match="chat_completions"):
        ModelGateway(backend=object(), codecs=[FakeCodec(), FakeCodec()])
