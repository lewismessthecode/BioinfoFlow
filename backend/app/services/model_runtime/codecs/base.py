from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Protocol

from app.services.model_runtime.contracts import ModelEvent, ModelInvocation, WireProtocol


class ModelCodec(Protocol):
    wire_protocol: WireProtocol

    def encode_request(self, invocation: ModelInvocation) -> dict[str, Any]: ...

    def decode_response(self, response: Any) -> AsyncIterator[ModelEvent]: ...
