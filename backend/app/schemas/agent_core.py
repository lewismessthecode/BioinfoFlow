from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


PermissionMode = Literal["ask_each_action", "guarded_auto", "bypass"]
AutomationMode = Literal["advise_only", "assisted", "autonomous"]
AgentMode = Literal["plan", "execution"]
ExecutionTargetType = Literal["local", "remote_ssh"]
ExecutionScopeMode = Literal["auto", "manual"]
SessionStatus = Literal["active", "archived", "deleted"]
TurnStatus = Literal[
    "queued",
    "running",
    "waiting_user",
    "waiting_approval",
    "completed",
    "failed",
    "cancelled",
]
EventVisibility = Literal["user", "internal", "audit"]
ActionKind = Literal[
    "tool",
    "platform",
    "shell",
    "code",
    "workflow",
    "run",
    "memory",
    "config",
    "subagent",
]
ActionStatus = Literal[
    "requested",
    "waiting_decision",
    "running",
    "completed",
    "failed",
    "cancelled",
    "rejected",
]
RiskLevel = Literal[
    "read", "act_low", "act_high", "destructive", "external", "critical"
]
ActionDecision = Literal["approve", "reject", "modify", "answer"]
MemoryStatus = Literal["proposed", "accepted", "rejected", "disabled"]
AttachmentKind = Literal["file", "folder", "image"]
AttachmentSource = Literal["upload", "clipboard"]
AttachmentStatus = Literal["processing", "ready", "error", "pending_delete"]


class AgentModelSelection(BaseModel):
    provider: str | None = None
    model: str | None = None
    model_id: UUID | None = None
    profile_id: UUID | None = None


class AgentExecutionTarget(BaseModel):
    type: ExecutionTargetType = Field(
        default="local",
        validation_alias=AliasChoices("type", "kind"),
    )
    connection_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("connection_id", "remote_connection_id"),
    )


class AgentExecutionScope(BaseModel):
    mode: ExecutionScopeMode = "auto"
    selected_targets: list[AgentExecutionTarget] | None = None


class AgentTokenUsageSummary(BaseModel):
    has_token_usage: bool
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cached_input_tokens: int | None = None
    reasoning_tokens: int | None = None
    context_window: int | None = None
    max_output_tokens: int | None = None
    turns_with_usage: int = 0
    raw_totals: dict[str, int] = Field(default_factory=dict)


class AgentSkillRead(BaseModel):
    name: str
    title: str | None = None
    version: str
    description: str
    category: str | None = None
    tags: list[str] = Field(default_factory=list)
    source: str
    root: str | None = None
    path: str
    body: str | None = None


class AgentSettingsRead(BaseModel):
    custom_instructions: str = ""


class AgentSettingsUpdate(BaseModel):
    custom_instructions: str = Field(default="", max_length=20_000)


class AgentSessionCreate(BaseModel):
    project_id: UUID | None = None
    title: str | None = None
    role_profile: str = "bioinformatician"
    permission_mode: PermissionMode = "guarded_auto"
    automation_mode: AutomationMode = "assisted"
    mode: AgentMode = "execution"
    default_model_profile_id: UUID | None = None
    model_selection: AgentModelSelection | None = None
    execution_target: AgentExecutionTarget | None = None
    execution_scope: AgentExecutionScope | None = None
    metadata: dict | None = None


class AgentSessionUpdate(BaseModel):
    title: str | None = None
    role_profile: str | None = None
    permission_mode: PermissionMode | None = None
    automation_mode: AutomationMode | None = None
    mode: AgentMode | None = None
    default_model_profile_id: UUID | None = None
    model_selection: AgentModelSelection | None = None
    execution_target: AgentExecutionTarget | None = None
    execution_scope: AgentExecutionScope | None = None
    status: SessionStatus | None = None
    metadata: dict | None = None
    pending_strategy: Literal["future_only", "approve_pending_tools"] = "future_only"


class AgentPendingReconciliation(BaseModel):
    affected_count: int = 0
    excluded_count: int = 0
    already_resolved_count: int = 0


class AgentSessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID | None = None
    workspace_id: UUID
    user_id: str
    title: str | None = None
    role_profile: str
    permission_mode: PermissionMode
    automation_mode: AutomationMode
    permission_policy_version: int = 1
    default_model_profile_id: UUID | None = None
    runtime_mode: str = "api"
    prompt_snapshot: dict | None = None
    toolset_policy: dict | None = None
    context_policy: dict | None = None
    compression_state: dict | None = None
    lineage: dict | None = None
    model_selection: AgentModelSelection | None = None
    execution_target: AgentExecutionTarget = Field(
        default_factory=lambda: AgentExecutionTarget(type="local")
    )
    execution_scope: AgentExecutionScope | None = None
    token_usage_summary: AgentTokenUsageSummary | None = None
    status: SessionStatus
    metadata: dict | None = Field(default=None, validation_alias="session_metadata")
    pending_strategy: Literal["future_only", "approve_pending_tools"] | None = None
    pending_reconciliation: AgentPendingReconciliation | None = None
    created_at: datetime
    updated_at: datetime


class AgentAttachmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    session_id: UUID
    workspace_id: UUID
    user_id: str
    kind: AttachmentKind
    source: AttachmentSource
    filename: str
    mime_type: str | None = None
    size_bytes: int
    file_count: int | None = None
    image_width: int | None = None
    image_height: int | None = None
    status: AttachmentStatus
    metadata: dict | None = Field(
        default=None,
        validation_alias="attachment_metadata",
    )
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class AgentTurnCreate(BaseModel):
    input_text: str
    input_parts: list[dict] | None = None
    active_skill_names: list[str] | None = None
    model_profile_id: UUID | None = None
    model_selection: AgentModelSelection | None = None
    execution_target: AgentExecutionTarget | None = None
    execution_scope: AgentExecutionScope | None = None
    metadata: dict | None = None


class AgentTurnSteer(BaseModel):
    input_text: str = Field(min_length=1)
    input_parts: list[dict] | None = None
    active_skill_names: list[str] | None = None
    metadata: dict | None = None


class AgentTurnSteerRead(BaseModel):
    steer_id: UUID
    turn_id: UUID
    delivery: Literal["pending"] = "pending"


class AgentTurnRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    session_id: UUID
    project_id: UUID | None = None
    workspace_id: UUID
    user_id: str
    input_text: str
    input_parts: list[dict] | None = None
    active_skill_names: list[str] = Field(default_factory=list)
    status: TurnStatus
    model_selection: AgentModelSelection | None = None
    model_profile_snapshot: dict | None = None
    final_text: str | None = None
    token_usage: dict | None = None
    termination_reason: str | None = None
    loop_state: dict | None = None
    iteration_count: int = 0
    budget_snapshot: dict | None = None
    interrupt_requested_at: datetime | None = None
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None


class AgentEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    session_id: UUID
    turn_id: UUID | None = None
    seq: int
    type: str
    payload: dict
    visibility: EventVisibility
    schema_version: int
    created_at: datetime
    updated_at: datetime


class AgentActionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    session_id: UUID
    turn_id: UUID
    parent_action_id: UUID | None = None
    kind: ActionKind
    name: str
    tool_call_id: str | None = None
    tool_batch_id: UUID | None = None
    tool_call_ordinal: int | None = None
    input: dict
    normalized_input: dict | None = None
    input_preview: str | None = None
    redacted_input: dict | None = None
    exposure_policy: dict | None = None
    risk_level: RiskLevel
    risk_reasons: list | None = None
    read_scope: list | None = None
    write_scope: list | None = None
    affected_resources: list | None = None
    permission_decision: dict | None = None
    evaluated_policy_version: int | None = None
    permission_context_snapshot: dict | None = None
    status: ActionStatus
    result: dict | None = None
    output_ref: dict | None = None
    output_summary: str | None = None
    requires_resume: bool = False
    error: dict | None = None
    audit_summary: str | None = None
    rollback_hint: str | None = None
    artifact_policy: dict | None = None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None


class AgentActionDecisionRequest(BaseModel):
    decision: ActionDecision
    note: str | None = None
    modified_input: dict | None = None
    # Carries the user's response for ``ask_user`` (decision == "answer"): a
    # mapping of question header → selected option label(s).
    answer: dict | None = None


class AgentArtifactRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    session_id: UUID
    turn_id: UUID
    action_id: UUID | None = None
    type: str
    title: str
    summary: str | None = None
    payload: dict | None = None
    file_path: str | None = None
    resource_ref: dict | None = None
    created_at: datetime
    updated_at: datetime


class AgentMemoryProposalCreate(BaseModel):
    project_id: UUID | None = None
    session_id: UUID | None = None
    scope: str
    type: str
    content: dict
    source: dict | None = None
    confidence: int | None = Field(default=None, ge=0, le=100)


class AgentMemoryDecisionRequest(BaseModel):
    note: str | None = None


class AgentMemoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    project_id: UUID | None = None
    session_id: UUID | None = None
    scope: str
    type: str
    content: dict
    source: dict | None = None
    confidence: int | None = None
    status: MemoryStatus
    created_at: datetime
    updated_at: datetime
