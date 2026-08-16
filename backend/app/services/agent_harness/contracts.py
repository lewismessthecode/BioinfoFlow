from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, model_validator

from app.services.agent_ui.contracts import (
    ActiveRunView,
    AgentEvent,
    ApprovalInteractionRequest,
    ApprovalInteractionResponse,
    ArtifactRefPart,
    AskUserInteractionRequest,
    AskUserInteractionResponse,
    AssistantDeltaEvent,
    AssistantDraftPartView,
    AssistantDraftView,
    AttachmentRefPart,
    DirectoryRefPart,
    ENTRY_PAYLOAD_TYPES,
    EntryCommittedEvent,
    ExecutionScopeSelection,
    FileRefPart,
    HistoryEntry,
    InteractionRequest,
    InteractionRequestEntry,
    InteractionRequestPayload,
    InteractionRequestedEvent,
    InteractionResponse,
    InteractionResponseEntry,
    InteractionResponsePayload,
    MessageEntry,
    MessagePart,
    MessagePayload,
    ModelSummary,
    NoticeEntry,
    NoticePayload,
    PendingInteractionView,
    PermissionMode,
    PlanEntry,
    PlanItem,
    PlanPayload,
    ReasoningSummaryPart,
    RecoveryInteractionRequest,
    RecoveryInteractionResponse,
    RunErrorView,
    RunPhase,
    RunRefPart,
    RunSettingsView,
    RunStatus,
    RunUpdatedEvent,
    RunView,
    SessionSnapshot,
    SessionStatus,
    SessionView,
    SnapshotEvent,
    StrictContract,
    TextPart,
    ToolCallPart,
    ToolCategory,
    ToolContentPartsOutput,
    ToolExecutionMode,
    ToolJsonOutput,
    ToolOutput,
    ToolProgressStatus,
    ToolProgressView,
    ToolPublicDetail,
    ToolResultPart,
    ToolTextOutput,
    ToolUpdatedEvent,
    UnknownPart,
    WorkflowRefPart,
    WorkspaceAccess,
)


class OpenSessionRequest(StrictContract):
    user_id: str
    workspace_id: UUID
    project_id: UUID | None = None
    title: str | None = Field(default=None, max_length=200)
    model: dict | None = None
    workspace: dict | None = None
    execution_scope: ExecutionScopeSelection = Field(
        default_factory=ExecutionScopeSelection
    )
    permission_mode: PermissionMode = "ask_dangerous"
    workspace_access: WorkspaceAccess = "read_write"
    prompt_snapshot: dict
    metadata: dict | None = None


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
                raise ValueError(
                    "directory_ref must use attachment_id or project path"
                )
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


class ModelSelectionInput(StrictContract):
    model_id: UUID | None = None
    profile_id: UUID | None = None
    provider: str | None = Field(default=None, min_length=1, max_length=200)
    model: str | None = Field(default=None, min_length=1, max_length=500)

    @model_validator(mode="after")
    def validate_selector(self) -> ModelSelectionInput:
        provider_selected = self.provider is not None or self.model is not None
        if provider_selected and (self.provider is None or self.model is None):
            raise ValueError("provider and model must be supplied together")
        if sum((self.model_id is not None, self.profile_id is not None, provider_selected)) > 1:
            raise ValueError(
                "choose only one model selector: model_id, profile_id, or provider and model"
            )
        return self


class RunSettingsInput(StrictContract):
    model: ModelSelectionInput | None = None
    permission_mode: PermissionMode | None = None
    execution_scope: ExecutionScopeSelection | None = None


class _Command(StrictContract):
    command_id: str = Field(min_length=1, max_length=200)


class MessageCommand(_Command):
    type: Literal["message"] = "message"
    parts: list[InputPart] = Field(min_length=1)
    run_settings: RunSettingsInput | None = None


class SteerCommand(_Command):
    type: Literal["steer"] = "steer"
    parts: list[InputPart] = Field(min_length=1)


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


__all__ = [
    "ActiveRunView",
    "AgentCommand",
    "AgentEvent",
    "ApprovalInteractionRequest",
    "ApprovalInteractionResponse",
    "ArtifactRefPart",
    "AskUserInteractionRequest",
    "AskUserInteractionResponse",
    "AssistantDeltaEvent",
    "AssistantDraftPartView",
    "AssistantDraftView",
    "AttachmentRefPart",
    "CancelCommand",
    "DirectoryRefPart",
    "ENTRY_PAYLOAD_TYPES",
    "EntryCommittedEvent",
    "ExecutionScopeSelection",
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
    "MessageCommand",
    "MessageEntry",
    "MessagePart",
    "MessagePayload",
    "ModelSelectionInput",
    "ModelSummary",
    "NoticeEntry",
    "NoticePayload",
    "OpenSessionRequest",
    "PendingInteractionView",
    "PermissionMode",
    "PlanEntry",
    "PlanItem",
    "PlanPayload",
    "ReasoningSummaryPart",
    "RecoveryInteractionRequest",
    "RecoveryInteractionResponse",
    "RespondCommand",
    "RunErrorView",
    "RunPhase",
    "RunRefPart",
    "RunSettingsInput",
    "RunSettingsView",
    "RunStatus",
    "RunUpdatedEvent",
    "RunView",
    "SessionSnapshot",
    "SessionStatus",
    "SessionView",
    "SnapshotEvent",
    "SteerCommand",
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
    "ToolTextOutput",
    "ToolUpdatedEvent",
    "UnknownPart",
    "WorkflowRefPart",
    "WorkspaceAccess",
]
