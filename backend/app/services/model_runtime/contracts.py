from __future__ import annotations

from collections.abc import Mapping
from dataclasses import InitVar, dataclass, field
from typing import Any, Literal, TypeAlias


Phase: TypeAlias = Literal["commentary", "final_answer"]
WireProtocol: TypeAlias = Literal["chat_completions", "responses"]


@dataclass(frozen=True)
class TextPart:
    text: str
    phase: Phase | None = None


@dataclass(frozen=True)
class ToolCallPart:
    call_id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ToolResultPart:
    call_id: str
    output: str
    is_error: bool = False


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    parameters: dict[str, Any]


@dataclass(frozen=True)
class ModelTarget:
    endpoint_id: str
    provider_kind: str
    model_name: str
    wire_protocol: WireProtocol
    base_url: str | None = None
    api_key: InitVar[str | None] = None

    def __post_init__(self, api_key: str | None) -> None:
        object.__setattr__(self, "_resolved_api_key", api_key)

    def resolved_api_key(self) -> str | None:
        return self._resolved_api_key

    def to_public_dict(self) -> dict[str, str | None]:
        return {
            "endpoint_id": self.endpoint_id,
            "provider_kind": self.provider_kind,
            "model_name": self.model_name,
            "wire_protocol": self.wire_protocol,
            "base_url": self.base_url,
        }

    def continuation_target(self) -> ContinuationTarget:
        return ContinuationTarget(
            endpoint_id=self.endpoint_id,
            provider_kind=self.provider_kind,
            model_name=self.model_name,
            wire_protocol=self.wire_protocol,
            base_url=self.base_url,
        )


@dataclass(frozen=True)
class ContinuationTarget:
    endpoint_id: str
    provider_kind: str
    model_name: str
    wire_protocol: WireProtocol
    base_url: str | None = None

    def to_private_dict(self) -> dict[str, str | None]:
        return {
            "endpoint_id": self.endpoint_id,
            "provider_kind": self.provider_kind,
            "model_name": self.model_name,
            "wire_protocol": self.wire_protocol,
            "base_url": self.base_url,
        }

    @classmethod
    def from_private_dict(cls, payload: Any) -> ContinuationTarget | None:
        if not isinstance(payload, Mapping):
            return None
        endpoint_id = payload.get("endpoint_id")
        provider_kind = payload.get("provider_kind")
        model_name = payload.get("model_name")
        wire_protocol = payload.get("wire_protocol")
        base_url = payload.get("base_url")
        if not all(
            isinstance(value, str) and value
            for value in (endpoint_id, provider_kind, model_name)
        ):
            return None
        if wire_protocol not in {"chat_completions", "responses"}:
            return None
        if base_url is not None and not isinstance(base_url, str):
            return None
        return cls(
            endpoint_id=endpoint_id,
            provider_kind=provider_kind,
            model_name=model_name,
            wire_protocol=wire_protocol,
            base_url=base_url,
        )


@dataclass(frozen=True)
class ResponsesContinuation:
    response_id: str | None
    output_items: InitVar[tuple[dict[str, Any], ...]]
    canonical_input_count: int = 0
    target: ContinuationTarget | None = None

    def __post_init__(self, output_items: tuple[dict[str, Any], ...]) -> None:
        object.__setattr__(self, "_opaque_output_items", output_items)

    def opaque_output_items(self) -> tuple[dict[str, Any], ...]:
        return self._opaque_output_items

    def to_private_dict(self) -> dict[str, Any]:
        return {
            "response_id": self.response_id,
            "canonical_input_count": self.canonical_input_count,
            "output_items": list(self.opaque_output_items()),
            "target": self.target.to_private_dict() if self.target is not None else None,
        }

    @classmethod
    def from_private_dict(cls, payload: Any) -> ResponsesContinuation | None:
        if not isinstance(payload, Mapping):
            return None
        output_items = payload.get("output_items")
        if not isinstance(output_items, list) or not all(
            isinstance(item, dict) for item in output_items
        ):
            return None
        response_id = payload.get("response_id")
        canonical_input_count = payload.get("canonical_input_count")
        target = ContinuationTarget.from_private_dict(payload.get("target"))
        if target is None:
            return None
        return cls(
            response_id=response_id if isinstance(response_id, str) else None,
            canonical_input_count=(
                canonical_input_count
                if isinstance(canonical_input_count, int)
                and canonical_input_count >= 0
                else 0
            ),
            output_items=tuple(output_items),
            target=target,
        )

    def matches_target(self, target: ModelTarget) -> bool:
        return self.target == target.continuation_target()

    def advance_canonical_input_count(
        self,
        canonical_parts_written: int,
    ) -> ResponsesContinuation:
        return ResponsesContinuation(
            response_id=self.response_id,
            canonical_input_count=(
                self.canonical_input_count + max(canonical_parts_written, 0)
            ),
            output_items=self.opaque_output_items(),
            target=self.target,
        )


InputPart: TypeAlias = TextPart | ToolCallPart | ToolResultPart


@dataclass(frozen=True)
class ModelInvocation:
    target: ModelTarget
    instructions: str
    input_items: tuple[InputPart, ...]
    tools: tuple[ToolDefinition, ...]
    stream: bool
    max_output_tokens: int
    allow_reasoning: bool = False
    continuation: ResponsesContinuation | None = None


@dataclass(frozen=True)
class ResponseStarted:
    streaming: bool
    kind: Literal["response_started"] = field(default="response_started", init=False)


@dataclass(frozen=True)
class TextDelta:
    text: str
    phase: Phase = "final_answer"
    kind: Literal["text_delta"] = field(default="text_delta", init=False)


@dataclass(frozen=True)
class ReasoningDelta:
    text: str
    kind: Literal["reasoning_delta"] = field(default="reasoning_delta", init=False)


@dataclass(frozen=True)
class ToolCallDelta:
    index: int
    call_id: str | None
    name: str | None
    arguments_delta: str
    kind: Literal["tool_call_delta"] = field(default="tool_call_delta", init=False)


@dataclass(frozen=True)
class UsageReport:
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cached_input_tokens: int | None = None
    reasoning_tokens: int | None = None
    kind: Literal["usage"] = field(default="usage", init=False)


@dataclass(frozen=True)
class ModelWarning:
    code: str
    message: str
    kind: Literal["warning"] = field(default="warning", init=False)


@dataclass(frozen=True)
class CompletionMetadata:
    response_id: str | None
    finish_reason: str | None
    continuation: ResponsesContinuation | None = field(default=None, repr=False)
    kind: Literal["completion"] = field(default="completion", init=False)


ModelEvent: TypeAlias = (
    ResponseStarted
    | TextDelta
    | ReasoningDelta
    | ToolCallDelta
    | UsageReport
    | ModelWarning
    | CompletionMetadata
)
