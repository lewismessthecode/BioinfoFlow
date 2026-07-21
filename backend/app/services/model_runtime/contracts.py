from __future__ import annotations

from collections.abc import Mapping
from dataclasses import InitVar, dataclass, field
import hashlib
import hmac
import json
from typing import Any, Literal, TypeAlias


Phase: TypeAlias = Literal["commentary", "final_answer"]
WireProtocol: TypeAlias = Literal["chat_completions", "responses"]
NetworkAccessPolicy: TypeAlias = Literal["public_only", "unrestricted"]
ReasoningEffort: TypeAlias = Literal["low", "medium", "high"]


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
    routed_model_name: InitVar[str | None] = None
    base_url: str | None = None
    network_access: NetworkAccessPolicy = "unrestricted"
    api_key: InitVar[str | None] = None
    target_revision: InitVar[str | None] = None

    def __post_init__(
        self,
        routed_model_name: str | None,
        api_key: str | None,
        target_revision: str | None,
    ) -> None:
        object.__setattr__(self, "_routed_model_name", routed_model_name)
        object.__setattr__(self, "_resolved_api_key", api_key)
        object.__setattr__(self, "_target_revision", target_revision)

    def resolved_model_name(self) -> str:
        if not self._routed_model_name:
            raise ValueError("Model target is missing provider routing metadata.")
        return self._routed_model_name

    def resolved_api_key(self) -> str | None:
        return self._resolved_api_key

    def resolved_target_revision(self) -> str | None:
        return self._target_revision

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
            target_revision=self._target_revision,
        )


@dataclass(frozen=True)
class ContinuationTarget:
    endpoint_id: str
    provider_kind: str
    model_name: str
    wire_protocol: WireProtocol
    base_url: str | None = None
    target_revision: str | None = field(default=None, repr=False)

    def to_private_dict(self) -> dict[str, str | None]:
        return {
            "endpoint_id": self.endpoint_id,
            "provider_kind": self.provider_kind,
            "model_name": self.model_name,
            "wire_protocol": self.wire_protocol,
            "base_url": self.base_url,
            "target_revision": self.target_revision,
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
        target_revision = payload.get("target_revision")
        if not all(
            isinstance(value, str) and value
            for value in (endpoint_id, provider_kind, model_name)
        ):
            return None
        if wire_protocol not in {"chat_completions", "responses"}:
            return None
        if base_url is not None and not isinstance(base_url, str):
            return None
        if not isinstance(target_revision, str) or not target_revision:
            return None
        return cls(
            endpoint_id=endpoint_id,
            provider_kind=provider_kind,
            model_name=model_name,
            wire_protocol=wire_protocol,
            base_url=base_url,
            target_revision=target_revision,
        )


@dataclass(frozen=True)
class ResponsesContinuation:
    response_id: str | None
    output_items: InitVar[tuple[dict[str, Any], ...]]
    canonical_input_count: int = 0
    canonical_input_digest: str | None = field(default=None, repr=False)
    target: ContinuationTarget | None = None

    def __post_init__(self, output_items: tuple[dict[str, Any], ...]) -> None:
        object.__setattr__(self, "_opaque_output_items", output_items)

    def opaque_output_items(self) -> tuple[dict[str, Any], ...]:
        return self._opaque_output_items

    def to_private_dict(self) -> dict[str, Any]:
        return {
            "response_id": self.response_id,
            "canonical_input_count": self.canonical_input_count,
            "canonical_input_digest": self.canonical_input_digest,
            "output_items": list(self.opaque_output_items()),
            "target": self.target.to_private_dict()
            if self.target is not None
            else None,
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
        canonical_input_digest = payload.get("canonical_input_digest")
        target = ContinuationTarget.from_private_dict(payload.get("target"))
        if (
            target is None
            or not isinstance(canonical_input_count, int)
            or isinstance(canonical_input_count, bool)
            or canonical_input_count < 0
            or not _valid_digest(canonical_input_digest)
        ):
            return None
        return cls(
            response_id=response_id if isinstance(response_id, str) else None,
            canonical_input_count=canonical_input_count,
            canonical_input_digest=canonical_input_digest,
            output_items=tuple(output_items),
            target=target,
        )

    def matches_target(self, target: ModelTarget) -> bool:
        revision = target.resolved_target_revision()
        return bool(
            revision
            and self.target is not None
            and self.target.target_revision
            and self.target == target.continuation_target()
        )

    def matches_canonical_input(self, input_items: tuple[InputPart, ...]) -> bool:
        return bool(
            0 <= self.canonical_input_count <= len(input_items)
            and _valid_digest(self.canonical_input_digest)
            and hmac.compare_digest(
                self.canonical_input_digest or "",
                canonical_input_prefix_digest(
                    input_items[: self.canonical_input_count]
                ),
            )
        )

    def advance_canonical_input(
        self,
        canonical_parts: tuple[InputPart, ...],
    ) -> ResponsesContinuation:
        if not _valid_digest(self.canonical_input_digest):
            raise ValueError(
                "Responses continuation is missing its canonical prefix digest."
            )
        return ResponsesContinuation(
            response_id=self.response_id,
            canonical_input_count=self.canonical_input_count + len(canonical_parts),
            canonical_input_digest=_advance_canonical_input_digest(
                self.canonical_input_digest or "",
                canonical_parts,
            ),
            output_items=self.opaque_output_items(),
            target=self.target,
        )


InputPart: TypeAlias = TextPart | ToolCallPart | ToolResultPart


_CANONICAL_INPUT_DIGEST_DOMAIN = b"bioinfoflow-canonical-input-prefix.v1"


def canonical_input_prefix_digest(input_items: tuple[InputPart, ...]) -> str:
    initial = hashlib.sha256(_CANONICAL_INPUT_DIGEST_DOMAIN).hexdigest()
    return _advance_canonical_input_digest(initial, input_items)


def _advance_canonical_input_digest(
    current_digest: str,
    input_items: tuple[InputPart, ...],
) -> str:
    state = bytes.fromhex(current_digest)
    for item in input_items:
        payload = _canonical_input_payload(item)
        state = hashlib.sha256(
            _CANONICAL_INPUT_DIGEST_DOMAIN
            + b"\x00"
            + state
            + len(payload).to_bytes(8, "big")
            + payload
        ).digest()
    return state.hex()


def _canonical_input_payload(item: InputPart) -> bytes:
    if isinstance(item, TextPart):
        payload = {"type": "text", "text": item.text, "phase": item.phase}
    elif isinstance(item, ToolCallPart):
        payload = {
            "type": "tool_call",
            "call_id": item.call_id,
            "name": item.name,
            "arguments": item.arguments,
        }
    else:
        payload = {
            "type": "tool_result",
            "call_id": item.call_id,
            "output": item.output,
            "is_error": item.is_error,
        }
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        default=str,
    ).encode("utf-8")


def _valid_digest(value: object) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    try:
        bytes.fromhex(value)
    except ValueError:
        return False
    return True


@dataclass(frozen=True)
class ReasoningRequest:
    enabled: bool = False
    effort: ReasoningEffort | None = None


@dataclass(frozen=True)
class ModelInvocation:
    target: ModelTarget
    instructions: str
    input_items: tuple[InputPart, ...]
    tools: tuple[ToolDefinition, ...]
    stream: bool
    max_output_tokens: int
    reasoning: ReasoningRequest = field(default_factory=ReasoningRequest)
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
