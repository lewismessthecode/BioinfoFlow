from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    model_validator,
)


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
PRESENTATION_PROTOCOL = "bioinfoflow.agent.presentation"
PRESENTATION_SCHEMA_VERSION = 1


class StrictContract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PresentationEnvelope(StrictContract):
    presentation_protocol: Literal["bioinfoflow.agent.presentation"] = (
        PRESENTATION_PROTOCOL
    )
    presentation_schema_version: Literal[1] = PRESENTATION_SCHEMA_VERSION


class EnvironmentScope(StrictContract):
    mode: Literal["auto", "manual"] = "auto"
    environment_ids: list[str] | None = None

    @model_validator(mode="after")
    def validate_environment_ids(self) -> EnvironmentScope:
        if self.mode == "auto":
            if self.environment_ids:
                raise ValueError("auto environment scope cannot select environments")
            self.environment_ids = None
            return self
        if not self.environment_ids:
            raise ValueError("manual environment scope requires environment_ids")
        self.environment_ids = list(dict.fromkeys(self.environment_ids))
        return self


class OpenSessionRequest(StrictContract):
    user_id: str
    workspace_id: UUID
    project_id: UUID | None = None
    title: str | None = Field(default=None, max_length=200)
    model: dict | None = None
    workspace: dict | None = None
    permission_mode: PermissionMode = "ask_dangerous"
    workspace_access: WorkspaceAccess = "read_write"
    environment_scope: EnvironmentScope = Field(default_factory=EnvironmentScope)
    prompt_snapshot: dict
    metadata: dict | None = None


class _Command(StrictContract):
    command_id: str = Field(min_length=1, max_length=200)


class InputTextPart(StrictContract):
    type: Literal["text"] = "text"
    text: str


class InputAttachmentRefPart(StrictContract):
    type: Literal["attachment_ref"] = "attachment_ref"
    attachment_id: UUID


class InputFileRefPart(StrictContract):
    type: Literal["file_ref"] = "file_ref"
    project_id: UUID | None = None
    path: str | None = None
    attachment_id: UUID | None = None

    @model_validator(mode="after")
    def validate_source(self) -> InputFileRefPart:
        if self.attachment_id is not None:
            if self.project_id is not None or self.path is not None:
                raise ValueError("file_ref must use attachment_id or project path")
            return self
        if self.project_id is None or not self.path:
            raise ValueError("file_ref requires attachment_id or project_id and path")
        return self


class InputDirectoryRefPart(StrictContract):
    type: Literal["directory_ref"] = "directory_ref"
    project_id: UUID | None = None
    path: str | None = None
    attachment_id: UUID | None = None

    @model_validator(mode="after")
    def validate_source(self) -> InputDirectoryRefPart:
        if self.attachment_id is not None:
            if self.project_id is not None or self.path is not None:
                raise ValueError("directory_ref must use attachment_id or project path")
            return self
        if self.project_id is None or not self.path:
            raise ValueError(
                "directory_ref requires attachment_id or project_id and path"
            )
        return self


class InputWorkflowRefPart(StrictContract):
    type: Literal["workflow_ref"] = "workflow_ref"
    workflow_id: UUID
    project_id: UUID | None = None
    scope: Literal["global", "project"] = "global"

    @model_validator(mode="after")
    def validate_scope(self) -> InputWorkflowRefPart:
        if self.scope == "project" and self.project_id is None:
            raise ValueError("project workflow_ref requires project_id")
        if self.scope == "global" and self.project_id is not None:
            raise ValueError("global workflow_ref cannot include project_id")
        return self


class InputRunRefPart(StrictContract):
    type: Literal["run_ref"] = "run_ref"
    run_id: str


InputPart = Annotated[
    InputTextPart
    | InputAttachmentRefPart
    | InputFileRefPart
    | InputDirectoryRefPart
    | InputWorkflowRefPart
    | InputRunRefPart,
    Field(discriminator="type"),
]


class MessageCommand(_Command):
    type: Literal["message"] = "message"
    parts: list[InputPart] = Field(min_length=1)


class SteerCommand(_Command):
    type: Literal["steer"] = "steer"
    parts: list[InputPart] = Field(min_length=1)


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


class RespondCommand(_Command):
    type: Literal["respond"] = "respond"
    interaction_id: str = Field(min_length=1, max_length=200)
    response: InteractionResponse


class CancelCommand(_Command):
    type: Literal["cancel"] = "cancel"
    reason: str | None = None


AgentCommand = Annotated[
    MessageCommand | SteerCommand | RespondCommand | CancelCommand,
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


class ReasoningTracePart(_MessagePart):
    type: Literal["reasoning_trace"] = "reasoning_trace"
    text: str
    provider: str
    model: str
    source: str
    truncated: bool = False
    started_at: datetime | None = None
    completed_at: datetime | None = None


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


class UnknownPart(_MessagePart):
    type: Literal["unknown"] = "unknown"
    original_type: str
    display_text: str


ToolOutputContentPart = Annotated[
    TextPart
    | ReasoningSummaryPart
    | ReasoningTracePart
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


MessagePart = Annotated[
    TextPart
    | ReasoningSummaryPart
    | ReasoningTracePart
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


class UnknownEntryPayload(StrictContract):
    original_type: str
    display_text: str


class UnknownEntry(_Entry):
    type: Literal["unknown"] = "unknown"
    payload: UnknownEntryPayload


HistoryEntry = Annotated[
    MessageEntry
    | InteractionRequestEntry
    | InteractionResponseEntry
    | NoticeEntry
    | PlanEntry
    | UnknownEntry,
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


class ModelSummary(StrictContract):
    provider: str
    model: str
    display_name: str
    supports_vision: bool = False
    supports_reasoning: bool = False
    supports_tools: bool = False


class SessionView(StrictContract):
    id: UUID
    user_id: str
    workspace_id: UUID
    project_id: UUID | None = None
    title: str | None = None
    model: ModelSummary
    permission_mode: PermissionMode
    workspace_access: WorkspaceAccess
    settings_revision: int = Field(default=1, ge=1)
    environment_scope: EnvironmentScope = Field(default_factory=EnvironmentScope)
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
    type: Literal["text", "reasoning_summary", "reasoning_trace"]
    text: str = ""
    end_offset: int = Field(default=0, ge=0)
    provider: str | None = None
    model: str | None = None
    source: str | None = None
    truncated: bool = False
    started_at: datetime | None = None
    completed_at: datetime | None = None


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


class SessionSnapshot(PresentationEnvelope):
    session: SessionView
    runs: list[RunView]
    entries: list[HistoryEntry]
    active_run: ActiveRunView | None = None


class SnapshotEvent(PresentationEnvelope):
    type: Literal["snapshot"] = "snapshot"
    snapshot: SessionSnapshot


class RunUpdatedEvent(PresentationEnvelope):
    type: Literal["run.updated"] = "run.updated"
    run: RunView


class AssistantDeltaEvent(PresentationEnvelope):
    type: Literal["assistant.delta"] = "assistant.delta"
    run_id: UUID
    draft_id: str
    part_id: str
    part_type: Literal["text", "reasoning_summary", "reasoning_trace"]
    delta: str
    start_offset: int = Field(ge=0)
    end_offset: int = Field(ge=0)
    provider: str | None = None
    model: str | None = None
    source: str | None = None
    truncated: bool = False
    started_at: datetime | None = None
    completed_at: datetime | None = None


class ToolUpdatedEvent(PresentationEnvelope):
    type: Literal["tool.updated"] = "tool.updated"
    run_id: UUID
    tool: ToolProgressView


class InteractionRequestedEvent(PresentationEnvelope):
    type: Literal["interaction.requested"] = "interaction.requested"
    run_id: UUID
    interaction: PendingInteractionView


class EntryCommittedEvent(PresentationEnvelope):
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


__all__ = [
    "ActiveRunView",
    "AgentCommand",
    "AgentEvent",
    "ApprovalInteractionRequest",
    "ApprovalInteractionResponse",
    "ArtifactRefPart",
    "AskUserInteractionRequest",
    "AskUserInteractionResponse",
    "AssistantDraftPartView",
    "AssistantDraftView",
    "AssistantDeltaEvent",
    "AttachmentRefPart",
    "CancelCommand",
    "DirectoryRefPart",
    "EnvironmentScope",
    "EntryCommittedEvent",
    "FileRefPart",
    "HistoryEntry",
    "InputAttachmentRefPart",
    "InputDirectoryRefPart",
    "InputFileRefPart",
    "InputPart",
    "InputRunRefPart",
    "InputTextPart",
    "InputWorkflowRefPart",
    "InteractionRequest",
    "InteractionRequestEntry",
    "InteractionRequestPayload",
    "InteractionRequestedEvent",
    "InteractionResponse",
    "InteractionResponseEntry",
    "InteractionResponsePayload",
    "MessageEntry",
    "MessageCommand",
    "MessagePart",
    "ModelSummary",
    "MessagePayload",
    "NoticeEntry",
    "NoticePayload",
    "OpenSessionRequest",
    "PRESENTATION_PROTOCOL",
    "PRESENTATION_SCHEMA_VERSION",
    "PendingInteractionView",
    "PlanEntry",
    "PlanItem",
    "PlanPayload",
    "ReasoningSummaryPart",
    "ReasoningTracePart",
    "RecoveryInteractionRequest",
    "RecoveryInteractionResponse",
    "RespondCommand",
    "RunPhase",
    "RunRefPart",
    "RunStatus",
    "RunUpdatedEvent",
    "RunErrorView",
    "RunView",
    "SessionSnapshot",
    "SessionStatus",
    "SessionView",
    "SnapshotEvent",
    "SteerCommand",
    "WorkspaceAccess",
    "TextPart",
    "ToolCallPart",
    "ToolCategory",
    "ToolContentPartsOutput",
    "ToolExecutionMode",
    "ToolJsonOutput",
    "ToolOutput",
    "ToolProgressStatus",
    "ToolProgressView",
    "ToolResultPart",
    "ToolTextOutput",
    "ToolUpdatedEvent",
    "UnknownPart",
    "UnknownEntry",
    "WorkflowRefPart",
]
