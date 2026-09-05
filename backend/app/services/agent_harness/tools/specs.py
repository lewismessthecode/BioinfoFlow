from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, TypeAlias

from app.services.agent_harness.contracts import (
    PermissionMode as ContractPermissionMode,
)
from app.services.agent_harness.contracts import ToolCategory
from app.services.agent_harness.contracts import (
    WorkspaceAccess as ContractWorkspaceAccess,
)
from app.services.model_runtime import ToolDefinition


ReplayPolicy: TypeAlias = Literal["safe", "verify", "never"]
PermissionMode: TypeAlias = ContractPermissionMode
WorkspaceAccess: TypeAlias = ContractWorkspaceAccess
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
    display_name: str
    category: ToolCategory
    summary: str
    input_summary_fields: tuple[str, ...] = ()
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
    summary: str | None = None
    input_preview: str | None = None
    questions: tuple[dict[str, Any], ...] = ()
    risk: dict[str, Any] | None = None
    target: dict[str, str] | None = None
    allowed_responses: tuple[Literal["approve", "reject"], ...] = ()


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
        summary: str | None = None,
        input_preview: str | None = None,
        questions: tuple[dict[str, Any], ...] = (),
        risk: dict[str, Any] | None = None,
        target: dict[str, str] | None = None,
        allowed_responses: tuple[Literal["approve", "reject"], ...] = (),
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
                summary=summary,
                input_preview=input_preview,
                questions=questions,
                risk=risk,
                target=target,
                allowed_responses=allowed_responses,
            ),
        )


@dataclass(frozen=True, slots=True)
class ToolBatchResult:
    results: tuple[ToolResult, ...]
    pending_calls: tuple[ToolCall, ...] = ()


@dataclass(frozen=True, slots=True)
class ToolExecutionContext:
    backend: Any
    call_id: str = ""
    cancellation: Any | None = None
    environment: dict[str, str] = field(default_factory=dict)
    sandbox_mode: Literal["read-only", "workspace-write", "danger-full-access"] = (
        "workspace-write"
    )


class HarnessTool(Protocol):
    spec: ToolSpec

    async def run(
        self, arguments: dict[str, Any], context: ToolExecutionContext
    ) -> dict[str, Any]: ...
