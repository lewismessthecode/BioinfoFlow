from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator


AGENT_UI_PROTOCOL_VERSION = 1

PermissionMode = Literal["ask_changes", "ask_dangerous", "full_access"]
WorkspaceAccess = Literal["read_only", "read_write"]
ApprovalAllowedResponse = Literal["approve", "reject"]
SessionStatus = Literal["active", "archived", "closing", "deleted"]
RunStatus = Literal[
    "queued", "running", "waiting_user", "completed", "failed", "cancelled"
]
RunPhase = Literal["model", "tools", "interaction"]
ToolProgressStatus = Literal[
    "pending",
    "running",
    "completed",
    "failed",
    "blocked",
    "cancelled",
    "interaction_required",
]
ToolExecutionMode = Literal["parallel", "serial", "mixed"]
ToolCategory = Literal[
    "read",
    "search",
    "command",
    "edit",
    "write",
    "workflow",
    "plan",
    "interaction",
    "other",
]
ExecutionTargetKind = Literal["local", "remote_ssh"]
ExecutionTargetStatus = Literal["online", "offline", "error", "unknown"]


class StrictContract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class UiCapabilities(StrictContract):
    reasoning: bool = True
    tool_activity: bool = True
    approvals: bool = True
    artifacts: bool = True
    starter_prompts: bool = True
    multi_target_execution: bool = True
    retry: bool = True
    edit_and_resend: bool = True


def default_ui_capabilities() -> UiCapabilities:
    return UiCapabilities()


class ExecutionTargetView(StrictContract):
    id: str
    handle: str
    alias: str
    kind: ExecutionTargetKind
    status: ExecutionTargetStatus = "unknown"
    primary: bool = False
    disabled_reason: str | None = None


class ToolTargetView(StrictContract):
    id: str
    handle: str
    alias: str
    kind: ExecutionTargetKind
    root: str | None = None


class ExecutionScopeSelection(StrictContract):
    mode: Literal["auto", "manual"] = "auto"
    target_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_manual_targets(self) -> ExecutionScopeSelection:
        normalized = list(dict.fromkeys(item for item in self.target_ids if item))
        if self.mode == "manual" and not normalized:
            raise ValueError("manual execution scope requires at least one target")
        self.target_ids = normalized
        return self


class ModelSummary(StrictContract):
    provider: str
    model: str
    display_name: str
    supports_vision: bool = False
    supports_reasoning: bool = False
    supports_tools: bool = False


class RunSettingsView(StrictContract):
    model: ModelSummary
    permission_mode: PermissionMode
    execution_scope: ExecutionScopeSelection
    allowed_targets: list[ExecutionTargetView] = Field(default_factory=list)


class StarterPromptView(StrictContract):
    id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=120)
    prompt: str = Field(min_length=1, max_length=2000)
    icon: Literal["check", "explain", "review", "chat"] = "chat"


class AgentUiBootstrap(StrictContract):
    protocol_version: Literal[1] = AGENT_UI_PROTOCOL_VERSION
    capabilities: UiCapabilities = Field(default_factory=default_ui_capabilities)
    execution_targets: list[ExecutionTargetView] = Field(default_factory=list)
    execution_scope: ExecutionScopeSelection = Field(
        default_factory=ExecutionScopeSelection
    )
    starter_prompts: list[StarterPromptView] = Field(default_factory=list)
    composer_hint: str | None = None


class AskUserInteractionResponse(StrictContract):
    type: Literal["ask_user"] = "ask_user"
    answers: dict[str, JsonValue]


class ApprovalInteractionResponse(StrictContract):
    type: Literal["approval"] = "approval"
    approved: bool


class RecoveryInteractionResponse(StrictContract):
    type: Literal["recovery"] = "recovery"
    choice: Literal["inspect", "retry", "cancel"]


InteractionResponse = Annotated[
    AskUserInteractionResponse
    | ApprovalInteractionResponse
    | RecoveryInteractionResponse,
    Field(discriminator="type"),
]


class _MessagePart(StrictContract):
    id: str = Field(min_length=1, max_length=300)


class TextPart(_MessagePart):
    type: Literal["text"] = "text"
    text: str


class ReasoningSummaryPart(_MessagePart):
    type: Literal["reasoning_summary"] = "reasoning_summary"
    text: str


class AttachmentRefPart(_MessagePart):
    type: Literal["attachment_ref"] = "attachment_ref"
    attachment_id: UUID
    filename: str
    kind: str
    mime_type: str | None = None
    size_bytes: int = Field(default=0, ge=0)


class FileRefPart(_MessagePart):
    type: Literal["file_ref"] = "file_ref"
    label: str
    project_id: UUID | None = None
    attachment_id: UUID | None = None
    path: str | None = None


class DirectoryRefPart(_MessagePart):
    type: Literal["directory_ref"] = "directory_ref"
    label: str
    project_id: UUID | None = None
    attachment_id: UUID | None = None
    path: str | None = None


class WorkflowRefPart(_MessagePart):
    type: Literal["workflow_ref"] = "workflow_ref"
    workflow_id: UUID
    label: str
    project_id: UUID | None = None


class RunRefPart(_MessagePart):
    type: Literal["run_ref"] = "run_ref"
    run_id: str
    label: str


class ArtifactRefPart(_MessagePart):
    type: Literal["artifact_ref"] = "artifact_ref"
    artifact_id: UUID
    title: str | None = None
    media_type: str | None = None


class ToolPublicDetail(StrictContract):
    id: str
    kind: Literal[
        "command",
        "working_directory",
        "path",
        "input",
        "output",
        "changes",
        "error",
        "metadata",
    ]
    label: str | None = None
    value: str
    format: Literal["text", "code", "path", "json", "diff"] = "text"
    copyable: bool = False
    truncated: bool = False
    redacted: bool = False


class ToolCallPart(_MessagePart):
    type: Literal["tool_call"] = "tool_call"
    call_id: str
    group_id: str
    execution_mode: ToolExecutionMode
    name: str
    display_name: str
    category: ToolCategory = "other"
    summary: str
    arguments: dict[str, JsonValue] = Field(default_factory=dict)
    public_details: list[ToolPublicDetail] = Field(default_factory=list)
    target: ToolTargetView | None = None


class UnknownPart(_MessagePart):
    type: Literal["unknown"] = "unknown"
    original_type: str
    display_text: str


ToolOutputContentPart = Annotated[
    TextPart
    | ReasoningSummaryPart
    | AttachmentRefPart
    | FileRefPart
    | DirectoryRefPart
    | WorkflowRefPart
    | RunRefPart
    | ArtifactRefPart
    | UnknownPart,
    Field(discriminator="type"),
]


class ToolTextOutput(StrictContract):
    type: Literal["text"] = "text"
    text: str


class ToolJsonOutput(StrictContract):
    type: Literal["json"] = "json"
    value: JsonValue


class ToolContentPartsOutput(StrictContract):
    type: Literal["content_parts"] = "content_parts"
    parts: list[ToolOutputContentPart]


ToolOutput = Annotated[
    ToolTextOutput | ToolJsonOutput | ToolContentPartsOutput,
    Field(discriminator="type"),
]


class ToolResultPart(_MessagePart):
    type: Literal["tool_result"] = "tool_result"
    call_id: str
    status: ToolProgressStatus
    summary: str | None = None
    output: ToolOutput | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None
    public_details: list[ToolPublicDetail] = Field(default_factory=list)
    target: ToolTargetView | None = None


MessagePart = Annotated[
    TextPart
    | ReasoningSummaryPart
    | AttachmentRefPart
    | FileRefPart
    | DirectoryRefPart
    | WorkflowRefPart
    | RunRefPart
    | ArtifactRefPart
    | ToolCallPart
    | ToolResultPart
    | UnknownPart,
    Field(discriminator="type"),
]


class MessagePayload(StrictContract):
    role: Literal["user", "assistant", "tool"]
    parts: list[MessagePart]


class InteractionOption(StrictContract):
    id: str
    label: str
    description: str = ""
    recommended: bool = False


class AskUserQuestion(StrictContract):
    id: str
    header: str
    question: str
    multi_select: bool = False
    options: list[InteractionOption] = Field(min_length=2, max_length=3)


class ApprovalRiskView(StrictContract):
    level: str
    effects: list[str] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    affected_resources: list[str] = Field(default_factory=list)


class AskUserInteractionRequest(StrictContract):
    type: Literal["ask_user"] = "ask_user"
    call_id: str
    questions: list[AskUserQuestion] = Field(min_length=1, max_length=3)


class ApprovalInteractionRequest(StrictContract):
    type: Literal["approval"] = "approval"
    call_id: str
    tool_name: str
    summary: str
    input_preview: str | None = None
    allowed_responses: list[ApprovalAllowedResponse] = Field(min_length=1)
    risk: ApprovalRiskView
    target: ToolTargetView | None = None


class RecoveryInteractionRequest(StrictContract):
    type: Literal["recovery"] = "recovery"
    call_id: str
    tool_name: str
    message: str
    options: list[InteractionOption]


InteractionRequest = Annotated[
    AskUserInteractionRequest | ApprovalInteractionRequest | RecoveryInteractionRequest,
    Field(discriminator="type"),
]


class InteractionRequestPayload(StrictContract):
    interaction_id: str
    request: InteractionRequest


class InteractionResponsePayload(StrictContract):
    interaction_id: str
    response: InteractionResponse


class CompactionPayload(StrictContract):
    summary: str
    through_sequence: int = Field(ge=0)


class NoticePayload(StrictContract):
    code: str
    message: str
    details: dict | None = None


class PlanItem(StrictContract):
    id: str
    text: str
    status: Literal["pending", "in_progress", "completed"]


class PlanPayload(StrictContract):
    plan_id: str
    revision: int = Field(ge=1)
    title: str | None = None
    items: list[PlanItem]
    updated_at: datetime


class _Entry(StrictContract):
    id: UUID
    session_id: UUID
    run_id: UUID | None = None
    sequence: int = Field(ge=1)
    schema_version: int = Field(default=2, ge=1)
    created_at: datetime


class MessageEntry(_Entry):
    type: Literal["message"] = "message"
    payload: MessagePayload


class InteractionRequestEntry(_Entry):
    type: Literal["interaction_request"] = "interaction_request"
    payload: InteractionRequestPayload


class InteractionResponseEntry(_Entry):
    type: Literal["interaction_response"] = "interaction_response"
    payload: InteractionResponsePayload


class NoticeEntry(_Entry):
    type: Literal["notice"] = "notice"
    payload: NoticePayload


class PlanEntry(_Entry):
    type: Literal["plan"] = "plan"
    payload: PlanPayload


HistoryEntry = Annotated[
    MessageEntry
    | InteractionRequestEntry
    | InteractionResponseEntry
    | NoticeEntry
    | PlanEntry,
    Field(discriminator="type"),
]


ENTRY_PAYLOAD_TYPES: dict[str, type[StrictContract]] = {
    "message": MessagePayload,
    "interaction_request": InteractionRequestPayload,
    "interaction_response": InteractionResponsePayload,
    "compaction": CompactionPayload,
    "notice": NoticePayload,
    "plan": PlanPayload,
}


class SessionView(StrictContract):
    id: UUID
    user_id: str
    workspace_id: UUID
    project_id: UUID | None = None
    title: str | None = None
    model: ModelSummary
    permission_mode: PermissionMode
    workspace_access: WorkspaceAccess
    execution_scope: ExecutionScopeSelection = Field(
        default_factory=ExecutionScopeSelection
    )
    status: SessionStatus
    created_at: datetime
    updated_at: datetime


class RunErrorView(StrictContract):
    code: str
    message: str


class RunView(StrictContract):
    id: UUID
    session_id: UUID
    status: RunStatus
    phase: RunPhase | None = None
    revision: int = Field(default=0, ge=0)
    settings: RunSettingsView | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    termination_reason: str | None = None
    error: RunErrorView | None = None
    created_at: datetime
    updated_at: datetime

    @model_validator(mode="after")
    def validate_error_state(self) -> RunView:
        if self.status == "failed" and self.error is None:
            raise ValueError("failed RunView requires a public error")
        if self.status != "failed" and self.error is not None:
            raise ValueError("only failed RunView may expose an error")
        return self


class AssistantDraftPartView(StrictContract):
    id: str
    type: Literal["text", "reasoning_summary"]
    text: str = ""
    end_offset: int = Field(default=0, ge=0)


class AssistantDraftView(StrictContract):
    id: str
    run_id: UUID
    parts: list[AssistantDraftPartView]


class ToolProgressView(StrictContract):
    call_id: str
    group_id: str
    execution_mode: ToolExecutionMode
    name: str
    display_name: str
    category: ToolCategory
    summary: str
    arguments: dict[str, JsonValue] = Field(default_factory=dict)
    status: ToolProgressStatus
    revision: int = Field(default=0, ge=0)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    input_summary: str | None = None
    output_summary: str | None = None
    error: str | None = None
    public_details: list[ToolPublicDetail] = Field(default_factory=list)
    target: ToolTargetView | None = None


class PendingInteractionView(StrictContract):
    interaction_id: str
    run_id: UUID
    revision: int = Field(ge=1)
    request: InteractionRequest


class ActiveRunView(StrictContract):
    run: RunView
    assistant_draft: AssistantDraftView | None = None
    tool_progress: list[ToolProgressView] = Field(default_factory=list)
    pending_interaction: PendingInteractionView | None = None


class SessionSnapshot(StrictContract):
    protocol_version: Literal[1] = AGENT_UI_PROTOCOL_VERSION
    capabilities: UiCapabilities = Field(default_factory=default_ui_capabilities)
    session: SessionView
    runs: list[RunView]
    entries: list[HistoryEntry]
    active_run: ActiveRunView | None = None


class _UiEvent(StrictContract):
    protocol_version: Literal[1] = AGENT_UI_PROTOCOL_VERSION


class SnapshotEvent(_UiEvent):
    type: Literal["snapshot"] = "snapshot"
    snapshot: SessionSnapshot


class RunUpdatedEvent(_UiEvent):
    type: Literal["run.updated"] = "run.updated"
    run: RunView


class AssistantDeltaEvent(_UiEvent):
    type: Literal["assistant.delta"] = "assistant.delta"
    run_id: UUID
    draft_id: str
    part_id: str
    part_type: Literal["text", "reasoning_summary"]
    delta: str
    start_offset: int = Field(ge=0)
    end_offset: int = Field(ge=0)


class ToolUpdatedEvent(_UiEvent):
    type: Literal["tool.updated"] = "tool.updated"
    run_id: UUID
    tool: ToolProgressView


class InteractionRequestedEvent(_UiEvent):
    type: Literal["interaction.requested"] = "interaction.requested"
    run_id: UUID
    interaction: PendingInteractionView


class EntryCommittedEvent(_UiEvent):
    type: Literal["entry.committed"] = "entry.committed"
    entry: HistoryEntry


AgentEvent = Annotated[
    SnapshotEvent
    | RunUpdatedEvent
    | AssistantDeltaEvent
    | ToolUpdatedEvent
    | InteractionRequestedEvent
    | EntryCommittedEvent,
    Field(discriminator="type"),
]


class AgentUiContractBundle(StrictContract):
    protocol_version: Literal[1] = AGENT_UI_PROTOCOL_VERSION
    bootstrap: AgentUiBootstrap
    snapshot: SessionSnapshot
    event: AgentEvent


__all__ = [
    "AGENT_UI_PROTOCOL_VERSION",
    "ActiveRunView",
    "AgentEvent",
    "AgentUiBootstrap",
    "AgentUiContractBundle",
    "ApprovalInteractionRequest",
    "ApprovalInteractionResponse",
    "ApprovalRiskView",
    "ArtifactRefPart",
    "AskUserInteractionRequest",
    "AskUserInteractionResponse",
    "AssistantDeltaEvent",
    "AssistantDraftPartView",
    "AssistantDraftView",
    "AttachmentRefPart",
    "CompactionPayload",
    "DirectoryRefPart",
    "ENTRY_PAYLOAD_TYPES",
    "EntryCommittedEvent",
    "ExecutionScopeSelection",
    "ExecutionTargetView",
    "FileRefPart",
    "HistoryEntry",
    "InteractionRequest",
    "InteractionRequestEntry",
    "InteractionRequestPayload",
    "InteractionRequestedEvent",
    "InteractionResponse",
    "InteractionResponseEntry",
    "InteractionResponsePayload",
    "MessageEntry",
    "MessagePart",
    "MessagePayload",
    "ModelSummary",
    "NoticeEntry",
    "NoticePayload",
    "PendingInteractionView",
    "PermissionMode",
    "PlanEntry",
    "PlanItem",
    "PlanPayload",
    "ReasoningSummaryPart",
    "RecoveryInteractionRequest",
    "RecoveryInteractionResponse",
    "RunErrorView",
    "RunPhase",
    "RunRefPart",
    "RunSettingsView",
    "RunStatus",
    "RunUpdatedEvent",
    "RunView",
    "SessionSnapshot",
    "SessionStatus",
    "SessionView",
    "SnapshotEvent",
    "StarterPromptView",
    "StrictContract",
    "TextPart",
    "ToolCallPart",
    "ToolCategory",
    "ToolContentPartsOutput",
    "ToolExecutionMode",
    "ToolJsonOutput",
    "ToolOutput",
    "ToolProgressStatus",
    "ToolProgressView",
    "ToolPublicDetail",
    "ToolResultPart",
    "ToolTargetView",
    "ToolTextOutput",
    "ToolUpdatedEvent",
    "UiCapabilities",
    "UnknownPart",
    "WorkflowRefPart",
    "WorkspaceAccess",
    "default_ui_capabilities",
]
