from __future__ import annotations

from collections.abc import AsyncIterator, Iterable
from typing import Any

from app.services.model_runtime.backend.litellm import LiteLLMBackend
from app.services.model_runtime.codecs.base import ModelCodec
from app.services.model_runtime.codecs.chat_completions import ChatCompletionsCodec
from app.services.model_runtime.codecs.responses import ResponsesCodec
from app.services.model_runtime.contracts import (
    ModelEvent,
    ModelInvocation,
    ReasoningDelta,
    ResponseStarted,
    TextDelta,
    ToolCallDelta,
    WireProtocol,
)
from app.services.model_runtime.errors import ModelError
from app.services.model_runtime.streams import aclose_async_iterator


class ModelGateway:
    """Dispatch canonical invocations through a protocol codec and backend."""

    def __init__(
        self,
        *,
        backend: Any | None = None,
        codecs: Iterable[ModelCodec] | None = None,
    ) -> None:
        self._backend = backend or LiteLLMBackend()
        configured_codecs = (
            list(codecs)
            if codecs is not None
            else [ChatCompletionsCodec(), ResponsesCodec()]
        )
        self._codecs: dict[WireProtocol, ModelCodec] = {}
        for codec in configured_codecs:
            wire_protocol = codec.wire_protocol
            if wire_protocol in self._codecs:
                raise ValueError(f"Duplicate codec registration: {wire_protocol}")
            self._codecs[wire_protocol] = codec

    def __repr__(self) -> str:
        protocols = ", ".join(sorted(self._codecs))
        return f"{type(self).__name__}(protocols=[{protocols}])"

    async def invoke(self, invocation: ModelInvocation) -> AsyncIterator[ModelEvent]:
        wire_protocol = invocation.target.wire_protocol
        codec = self._codecs.get(wire_protocol)
        if codec is None:
            raise ValueError(f"No codec registered for wire protocol: {wire_protocol}")

        request = codec.encode_request(invocation)
        if invocation.target.base_url is not None:
            request["api_base"] = invocation.target.base_url
        api_key = invocation.target.resolved_api_key()
        if api_key is not None:
            request["api_key"] = api_key
        raw_response = await self._backend.invoke(
            wire_protocol,
            request,
            network_access=invocation.target.network_access,
        )
        semantic_output_emitted = False
        decoded_events = None
        try:
            yield ResponseStarted(streaming=hasattr(raw_response, "__aiter__"))
            decoded_events = codec.decode_response(raw_response)
            async for event in decoded_events:
                finalize_event = getattr(codec, "finalize_event", None)
                finalized_event = (
                    finalize_event(invocation, request, event)
                    if callable(finalize_event)
                    else event
                )
                if isinstance(
                    finalized_event,
                    (TextDelta, ReasoningDelta, ToolCallDelta),
                ):
                    semantic_output_emitted = True
                yield finalized_event
        except ModelError as exc:
            if semantic_output_emitted and exc.replay_safe:
                raise _copy_model_error(exc, replay_safe=False) from None
            raise
        finally:
            if decoded_events is not None:
                await aclose_async_iterator(decoded_events)
            await aclose_async_iterator(raw_response)


def _copy_model_error(exc: ModelError, *, replay_safe: bool) -> ModelError:
    return ModelError(
        category=exc.category,
        message=exc.message,
        http_status=exc.http_status,
        provider_code=exc.provider_code,
        retryable=exc.retryable,
        replay_safe=replay_safe,
        retry_after_seconds=exc.retry_after_seconds,
        request_id=exc.request_id,
        cause=exc.cause,
    )
