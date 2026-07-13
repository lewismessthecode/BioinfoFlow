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
    ResponseStarted,
    WireProtocol,
)


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
        raw_response = await self._backend.invoke(wire_protocol, request)
        yield ResponseStarted(streaming=hasattr(raw_response, "__aiter__"))
        async for event in codec.decode_response(raw_response):
            finalize_event = getattr(codec, "finalize_event", None)
            yield (
                finalize_event(invocation, request, event)
                if callable(finalize_event)
                else event
            )
