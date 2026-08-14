from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, TypeAlias

from app.services.model_runtime import ToolDefinition


ReplayPolicy: TypeAlias = Literal["safe", "verify", "never"]
PermissionMode: TypeAlias = Literal["read_only", "ask_dangerous", "full_access"]
ToolStatus: TypeAlias = Literal[
    "completed", "failed", "blocked", "cancelled", "interaction_required"
]
InteractionKind: TypeAlias = Literal["question", "confirmation", "recovery"]


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]
    replay_policy: ReplayPolicy
    mutates_workspace: bool = False
    path_argument: str | None = None
    serial: bool = False

    def model_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters=self.input_schema,
        )


@dataclass(frozen=True, slots=True)
class ToolCall:
    call_id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ToolInteraction:
    request_id: str
    call_id: str
    kind: InteractionKind
    questions: tuple[dict[str, Any], ...] = ()
    risk: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class ToolResult:
    call_id: str
    tool_name: str
    status: ToolStatus
    replay_policy: ReplayPolicy
    output: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    interaction: ToolInteraction | None = None

    @classmethod
    def interaction_required(
        cls,
        *,
        call_id: str,
        tool_name: str,
        replay_policy: ReplayPolicy,
        request_id: str,
        kind: InteractionKind,
        questions: tuple[dict[str, Any], ...] = (),
        risk: dict[str, Any] | None = None,
    ) -> ToolResult:
        return cls(
            call_id=call_id,
            tool_name=tool_name,
            status="interaction_required",
            replay_policy=replay_policy,
            interaction=ToolInteraction(
                request_id=request_id,
                call_id=call_id,
                kind=kind,
                questions=questions,
                risk=risk,
            ),
        )


@dataclass(frozen=True, slots=True)
class ToolBatchResult:
    results: tuple[ToolResult, ...]
    pending_calls: tuple[ToolCall, ...] = ()


@dataclass(frozen=True, slots=True)
class ToolExecutionContext:
    backend: Any
    cancellation: Any | None = None
    environment: dict[str, str] = field(default_factory=dict)


class HarnessTool(Protocol):
    spec: ToolSpec

    async def run(
        self, arguments: dict[str, Any], context: ToolExecutionContext
    ) -> dict[str, Any]: ...
