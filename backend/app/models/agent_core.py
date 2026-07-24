from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class AgentSessionStatus:
    ACTIVE = "active"
    ARCHIVED = "archived"
    DELETED = "deleted"


class AgentTurnStatus:
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_USER = "waiting_user"
    WAITING_APPROVAL = "waiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AgentEventVisibility:
    USER = "user"
    INTERNAL = "internal"
    AUDIT = "audit"


class AgentActionStatus:
    REQUESTED = "requested"
    WAITING_DECISION = "waiting_decision"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


class AgentToolCallBatchStatus:
    EVALUATING = "evaluating"
    WAITING = "waiting"
    READY = "ready"
    CONTINUING = "continuing"
    TERMINAL = "terminal"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AgentMemoryStatus:
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    DISABLED = "disabled"


class AgentMessageStatus:
    DRAFT = "draft"
    COMMITTED = "committed"
    SUPERSEDED = "superseded"


class AgentSession(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "agent_sessions"

    project_id: Mapped[str | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    role_profile: Mapped[str] = mapped_column(String(80), nullable=False, default="bioinformatician")
    permission_mode: Mapped[str] = mapped_column(String(40), nullable=False, default="guarded_auto")
    automation_mode: Mapped[str] = mapped_column(String(40), nullable=False, default="assisted")
    permission_policy_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    default_model_profile_id: Mapped[str | None] = mapped_column(
        ForeignKey("llm_model_profiles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    runtime_mode: Mapped[str] = mapped_column(String(40), nullable=False, default="api")
    active_turn_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
    )
    prompt_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    toolset_policy: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    context_policy: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    compression_state: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    lineage: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default=AgentSessionStatus.ACTIVE,
        index=True,
    )
    session_metadata: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)

    project = relationship("Project")
    workspace = relationship("Workspace")
    default_model_profile = relationship("LlmModelProfile")
    turns = relationship(
        "AgentTurn",
        back_populates="session",
        cascade="all, delete-orphan",
    )
    messages = relationship(
        "AgentMessage",
        back_populates="session",
        cascade="all, delete-orphan",
    )
    events = relationship(
        "AgentEvent",
        back_populates="session",
        cascade="all, delete-orphan",
    )
    actions = relationship(
        "AgentAction",
        back_populates="session",
        cascade="all, delete-orphan",
    )
    artifacts = relationship(
        "AgentArtifact",
        back_populates="session",
        cascade="all, delete-orphan",
    )


class AgentTurn(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "agent_turns"

    session_id: Mapped[str] = mapped_column(
        ForeignKey("agent_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id: Mapped[str | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    input_text: Mapped[str] = mapped_column(Text, nullable=False)
    input_parts: Mapped[list | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default=AgentTurnStatus.QUEUED,
        index=True,
    )
    model_profile_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    final_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_usage: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    termination_reason: Mapped[str | None] = mapped_column(String(80), nullable=True)
    loop_state: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    iteration_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tool_batch_sequence: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    budget_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    interrupt_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    accepts_steer: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default="1",
    )
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    owner_token: Mapped[str | None] = mapped_column(String(36), nullable=True)
    resume_batch_token: Mapped[str | None] = mapped_column(String(36), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    session = relationship("AgentSession", back_populates="turns")
    project = relationship("Project")
    workspace = relationship("Workspace")
    events = relationship(
        "AgentEvent",
        back_populates="turn",
        cascade="all, delete-orphan",
    )
    actions = relationship(
        "AgentAction",
        back_populates="turn",
        cascade="all, delete-orphan",
    )
    tool_call_batches = relationship(
        "AgentToolCallBatch",
        back_populates="turn",
        cascade="all, delete-orphan",
    )
    artifacts = relationship(
        "AgentArtifact",
        back_populates="turn",
        cascade="all, delete-orphan",
    )
    messages = relationship(
        "AgentMessage",
        back_populates="turn",
        cascade="all, delete-orphan",
    )


class AgentMessage(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "agent_messages"

    session_id: Mapped[str] = mapped_column(
        ForeignKey("agent_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    turn_id: Mapped[str | None] = mapped_column(
        ForeignKey("agent_turns.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    content_parts: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    message_metadata: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default=AgentMessageStatus.COMMITTED,
        index=True,
    )
    ordering_index: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    session = relationship("AgentSession", back_populates="messages")
    turn = relationship("AgentTurn", back_populates="messages")


class AgentEvent(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "agent_events"
    __table_args__ = (
        UniqueConstraint("session_id", "seq", name="uq_agent_events_session_seq"),
    )

    session_id: Mapped[str] = mapped_column(
        ForeignKey("agent_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    turn_id: Mapped[str | None] = mapped_column(
        ForeignKey("agent_turns.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    visibility: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=AgentEventVisibility.USER,
        index=True,
    )
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    session = relationship("AgentSession", back_populates="events")
    turn = relationship("AgentTurn", back_populates="events")


class AgentToolCallBatch(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "agent_tool_call_batches"
    __table_args__ = (
        UniqueConstraint("turn_id", "batch_ordinal", name="uq_agent_tool_batches_turn_ordinal"),
    )

    session_id: Mapped[str] = mapped_column(
        ForeignKey("agent_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    turn_id: Mapped[str] = mapped_column(
        ForeignKey("agent_turns.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default=AgentToolCallBatchStatus.EVALUATING,
        index=True,
    )
    tool_call_count: Mapped[int] = mapped_column(Integer, nullable=False)
    batch_ordinal: Mapped[int | None] = mapped_column(Integer, nullable=True)
    continuation_claimed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    turn = relationship("AgentTurn", back_populates="tool_call_batches")
    actions = relationship("AgentAction", back_populates="tool_batch")


class AgentAction(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "agent_actions"
    __table_args__ = (
        UniqueConstraint(
            "tool_batch_id",
            "tool_call_ordinal",
            name="uq_agent_actions_tool_batch_ordinal",
        ),
        UniqueConstraint(
            "tool_batch_id",
            "tool_call_id",
            name="uq_agent_actions_tool_batch_call_id",
        ),
    )

    session_id: Mapped[str] = mapped_column(
        ForeignKey("agent_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    turn_id: Mapped[str] = mapped_column(
        ForeignKey("agent_turns.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    parent_action_id: Mapped[str | None] = mapped_column(
        ForeignKey("agent_actions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    kind: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    tool_call_id: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    tool_batch_id: Mapped[str | None] = mapped_column(
        ForeignKey("agent_tool_call_batches.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    tool_call_ordinal: Mapped[int | None] = mapped_column(Integer, nullable=True)
    input: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    normalized_input: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    input_preview: Mapped[str | None] = mapped_column(Text, nullable=True)
    redacted_input: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    exposure_policy: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    risk_level: Mapped[str] = mapped_column(String(30), nullable=False, default="read")
    risk_reasons: Mapped[list | None] = mapped_column(JSON, nullable=True)
    read_scope: Mapped[list | None] = mapped_column(JSON, nullable=True)
    write_scope: Mapped[list | None] = mapped_column(JSON, nullable=True)
    affected_resources: Mapped[list | None] = mapped_column(JSON, nullable=True)
    permission_decision: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    evaluated_policy_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    permission_context_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default=AgentActionStatus.REQUESTED,
        index=True,
    )
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    output_ref: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    output_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    requires_resume: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    error: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    audit_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    rollback_hint: Mapped[str | None] = mapped_column(Text, nullable=True)
    artifact_policy: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    session = relationship("AgentSession", back_populates="actions")
    turn = relationship("AgentTurn", back_populates="actions")
    parent_action = relationship("AgentAction", remote_side="AgentAction.id")
    tool_batch = relationship("AgentToolCallBatch", back_populates="actions")
    artifacts = relationship("AgentArtifact", back_populates="action")


class AgentArtifact(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "agent_artifacts"

    session_id: Mapped[str] = mapped_column(
        ForeignKey("agent_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    turn_id: Mapped[str] = mapped_column(
        ForeignKey("agent_turns.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    action_id: Mapped[str | None] = mapped_column(
        ForeignKey("agent_actions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    file_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    resource_ref: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    session = relationship("AgentSession", back_populates="artifacts")
    turn = relationship("AgentTurn", back_populates="artifacts")
    action = relationship("AgentAction", back_populates="artifacts")


class AgentMemory(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "agent_memories"

    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id: Mapped[str | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    session_id: Mapped[str | None] = mapped_column(
        ForeignKey("agent_sessions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    scope: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    content: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    source: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    confidence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default=AgentMemoryStatus.PROPOSED,
        index=True,
    )

    workspace = relationship("Workspace")
    project = relationship("Project")
    session = relationship("AgentSession")
