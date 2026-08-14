from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


PermissionMode = Literal["read_only", "ask_dangerous", "full_access"]
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


class StrictContract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class OpenSessionRequest(StrictContract):
    user_id: str
    workspace_id: UUID
    project_id: UUID | None = None
    title: str | None = Field(default=None, max_length=200)
    model: dict | None = None
    workspace: dict | None = None
    permission_mode: PermissionMode = "ask_dangerous"
    prompt_snapshot: dict
    metadata: dict | None = None


class _Command(StrictContract):
    command_id: str = Field(min_length=1, max_length=200)


class PromptCommand(_Command):
    type: Literal["prompt"] = "prompt"
    text: str
    attachment_ids: list[UUID] = Field(default_factory=list)


class SteerCommand(_Command):
    type: Literal["steer"] = "steer"
    text: str


class FollowUpCommand(_Command):
    type: Literal["follow_up"] = "follow_up"
    text: str
    attachment_ids: list[UUID] = Field(default_factory=list)


class RespondCommand(_Command):
    type: Literal["respond"] = "respond"
    interaction_id: str = Field(min_length=1, max_length=200)
    response: dict


class CancelCommand(_Command):
    type: Literal["cancel"] = "cancel"
    reason: str | None = None


AgentCommand = Annotated[
    PromptCommand | SteerCommand | FollowUpCommand | RespondCommand | CancelCommand,
    Field(discriminator="type"),
]


class MessagePayload(StrictContract):
    role: Literal["user", "assistant", "tool"]
    content: list[dict]
    call_id: str | None = None
    is_error: bool = False
    reasoning_summary: str | None = None
    tool_calls: list[dict] = Field(default_factory=list)
    attachment_ids: list[UUID] = Field(default_factory=list)
    artifact_ids: list[UUID] = Field(default_factory=list)


class InteractionRequestPayload(StrictContract):
    interaction_id: str
    request: dict


class InteractionResponsePayload(StrictContract):
    interaction_id: str
    response: dict


class CompactionPayload(StrictContract):
    summary: str
    through_sequence: int = Field(ge=0)


class NoticePayload(StrictContract):
    code: str
    message: str
    details: dict | None = None


class _Entry(StrictContract):
    id: UUID
    session_id: UUID
    run_id: UUID | None = None
    sequence: int = Field(ge=1)
    schema_version: int = Field(default=1, ge=1)
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


class CompactionEntry(_Entry):
    type: Literal["compaction"] = "compaction"
    payload: CompactionPayload


class NoticeEntry(_Entry):
    type: Literal["notice"] = "notice"
    payload: NoticePayload


HistoryEntry = Annotated[
    MessageEntry
    | InteractionRequestEntry
    | InteractionResponseEntry
    | CompactionEntry
    | NoticeEntry,
    Field(discriminator="type"),
]


ENTRY_PAYLOAD_TYPES: dict[str, type[StrictContract]] = {
    "message": MessagePayload,
    "interaction_request": InteractionRequestPayload,
    "interaction_response": InteractionResponsePayload,
    "compaction": CompactionPayload,
    "notice": NoticePayload,
}


class SessionView(StrictContract):
    id: UUID
    user_id: str
    workspace_id: UUID
    project_id: UUID | None = None
    title: str | None = None
    permission_mode: PermissionMode
    status: SessionStatus
    created_at: datetime
    updated_at: datetime


class RunView(StrictContract):
    id: UUID
    session_id: UUID
    status: RunStatus
    phase: RunPhase | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    termination_reason: str | None = None
    error: dict | None = None
    created_at: datetime
    updated_at: datetime


class AssistantDraftView(StrictContract):
    text: str = ""
    reasoning_summary: str | None = None
    end_offset: int = Field(default=0, ge=0)


class ToolProgressView(StrictContract):
    call_id: str
    name: str
    status: ToolProgressStatus


class PendingInteractionView(StrictContract):
    interaction_id: str
    request: dict


class SessionSnapshot(StrictContract):
    session: SessionView
    current_run: RunView | None
    entries: list[HistoryEntry]
    assistant_draft: AssistantDraftView | None = None
    tool_progress: list[ToolProgressView] = Field(default_factory=list)
    pending_interaction: PendingInteractionView | None = None
    revision: int = Field(ge=0)


class SnapshotEvent(StrictContract):
    type: Literal["snapshot"] = "snapshot"
    snapshot: SessionSnapshot | None


class RunUpdatedEvent(StrictContract):
    type: Literal["run.updated"] = "run.updated"
    run_id: UUID
    status: RunStatus
    phase: RunPhase | None = None


class AssistantDeltaEvent(StrictContract):
    type: Literal["assistant.delta"] = "assistant.delta"
    run_id: UUID
    delta: str
    start_offset: int = Field(ge=0)
    end_offset: int = Field(ge=0)


class ToolUpdatedEvent(StrictContract):
    type: Literal["tool.updated"] = "tool.updated"
    run_id: UUID
    call_id: str
    status: str
    update: dict | None = None


class InteractionRequestedEvent(StrictContract):
    type: Literal["interaction.requested"] = "interaction.requested"
    run_id: UUID
    interaction_id: str
    request: dict


class EntryCommittedEvent(StrictContract):
    type: Literal["entry.committed"] = "entry.committed"
    entry: HistoryEntry | None


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
    "AgentCommand",
    "AgentEvent",
    "AssistantDraftView",
    "AssistantDeltaEvent",
    "CancelCommand",
    "CompactionEntry",
    "CompactionPayload",
    "EntryCommittedEvent",
    "FollowUpCommand",
    "HistoryEntry",
    "InteractionRequestEntry",
    "InteractionRequestPayload",
    "InteractionRequestedEvent",
    "InteractionResponseEntry",
    "InteractionResponsePayload",
    "MessageEntry",
    "MessagePayload",
    "NoticeEntry",
    "NoticePayload",
    "OpenSessionRequest",
    "PendingInteractionView",
    "PromptCommand",
    "RespondCommand",
    "RunPhase",
    "RunStatus",
    "RunUpdatedEvent",
    "RunView",
    "SessionSnapshot",
    "SessionStatus",
    "SessionView",
    "SnapshotEvent",
    "SteerCommand",
    "ToolProgressStatus",
    "ToolProgressView",
    "ToolUpdatedEvent",
]
