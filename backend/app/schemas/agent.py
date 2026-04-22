from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel


ExecutionPolicy = Literal["auto", "approve_all", "bypass"]


class AgentMessageType(str, Enum):
    TEXT = "text"
    THINKING = "thinking"
    ARTIFACT = "artifact"
    PLAN = "plan"
    STATUS = "status"
    COMPLETION = "completion"
    # Stream-only types
    TEXT_DELTA = "text_delta"
    THINKING_DELTA = "thinking_delta"
    THINKING_CONTENT = "thinking_content"
    TOOL_CALL_START = "tool_call_start"
    TOOL_CALL_END = "tool_call_end"
    ERROR = "error"


class AgentMessage(BaseModel):
    conversation_id: str | None = None
    project_id: str
    type: AgentMessageType = AgentMessageType.TEXT
    content: str
    metadata: dict | None = None
    model: str | None = None
    execution_policy: ExecutionPolicy | None = None


class AgentMessageRole(str, Enum):
    USER = "user"
    AGENT = "agent"
    SYSTEM = "system"


class AgentMessageResponse(BaseModel):
    message_id: UUID | None = None
    conversation_id: UUID
    response_id: UUID | None = None
    status: str


class AgentConversationCreate(BaseModel):
    project_id: UUID | None = None
    title: str | None = None
    execution_policy: ExecutionPolicy | None = None


class AgentConversationUpdate(BaseModel):
    title: str | None = None
    pinned: bool | None = None
    execution_policy: ExecutionPolicy | None = None


class AgentConversationMove(BaseModel):
    target_project_id: UUID


class AgentConversationRead(BaseModel):
    id: UUID
    project_id: UUID
    title: str | None = None
    pinned: bool | None = None
    storage_backend: str | None = None
    workspace_binding_id: str | None = None
    execution_policy: ExecutionPolicy | None = None
    created_at: datetime
    updated_at: datetime


class AgentMessageRead(BaseModel):
    id: UUID
    role: AgentMessageRole
    type: AgentMessageType
    content: str | None = None
    metadata: dict | None = None
    created_at: datetime


class AgentConversationHistory(BaseModel):
    conversation_id: UUID
    project_id: UUID
    title: str | None = None
    pinned: bool | None = None
    storage_backend: str | None = None
    execution_policy: ExecutionPolicy | None = None
    messages: list[AgentMessageRead]


class AgentTraceRead(BaseModel):
    id: UUID
    conversation_id: UUID
    message_id: UUID | None = None
    type: str
    payload: dict | None = None
    created_at: datetime


class AgentTraceResponse(BaseModel):
    conversation_id: UUID
    events: list[AgentTraceRead]


# Approval schemas
class ApprovalAction(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"


class ApprovalResolveRequest(BaseModel):
    """Request to resolve an approval."""

    action: ApprovalAction


class ApprovalRead(BaseModel):
    """Response schema for an approval record."""

    id: UUID
    conversation_id: UUID
    step_id: str
    approval_type: str
    payload: dict | None = None
    status: str
    resolved_by: str | None = None
    resolved_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ApprovalResolveResponse(BaseModel):
    """Response after resolving an approval."""

    approval_id: UUID
    status: str
    resolved_at: datetime


class ApprovalListResponse(BaseModel):
    """Response for listing approvals."""

    conversation_id: UUID
    approvals: list[ApprovalRead]
