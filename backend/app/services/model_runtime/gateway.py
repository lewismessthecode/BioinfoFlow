from __future__ import annotations

from collections.abc import AsyncIterator, Iterable
from typing import Any

from app.services.model_runtime.backend.litellm import LiteLLMBackend
from app.services.model_runtime.codecs.base import ModelCodec
from app.services.model_runtime.codecs.chat_completions import ChatCompletionsCodec
from app.services.model_runtime.codecs.responses import ResponsesCodec
from app.services.model_runtime.contracts import (
    CompletionMetadata,
    ModelEvent,
    ModelInvocation,
    ResponseStarted,
    ResponsesContinuation,
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
            if wire_protocol == "responses" and isinstance(event, CompletionMetadata):
                current_output = (
                    event.continuation.opaque_output_items()
                    if event.continuation is not None
                    else ()
                )
                replay_input = _merge_replay_input(
                    request.get("input"),
                    current_output,
                )
                event = CompletionMetadata(
                    response_id=event.response_id,
                    finish_reason=event.finish_reason,
                    continuation=ResponsesContinuation(
                        response_id=event.response_id,
                        output_items=replay_input,
                        canonical_input_count=len(invocation.input_items),
                    ),
                )
            yield event


def _merge_replay_input(
    request_input: Any,
    current_output: tuple[dict[str, Any], ...],
) -> tuple[dict[str, Any], ...]:
    merged: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    candidates = [
        *(
            item
            for item in request_input
            if isinstance(request_input, (list, tuple)) and isinstance(item, dict)
        ),
        *current_output,
    ]
    for item in candidates:
        key = _stable_replay_key(item)
        if key is not None and key in seen:
            continue
        if key is not None:
            seen.add(key)
        merged.append(item)
    return tuple(merged)


def _stable_replay_key(item: dict[str, Any]) -> tuple[str, str] | None:
    item_id = item.get("id")
    if isinstance(item_id, str) and item_id:
        return "id", item_id
    if item.get("type") == "function_call":
        call_id = item.get("call_id")
        if isinstance(call_id, str) and call_id:
            return "function_call", call_id
    return None
