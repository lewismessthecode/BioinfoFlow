from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
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


class AgentMemoryStatus:
    PROPOSED = "proposed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    DISABLED = "disabled"


class AgentSession(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "agent_sessions"

    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
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
    default_model_profile_id: Mapped[str | None] = mapped_column(
        ForeignKey("llm_model_profiles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
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
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
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
    artifacts = relationship(
        "AgentArtifact",
        back_populates="turn",
        cascade="all, delete-orphan",
    )


class AgentEvent(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "agent_events"
    __table_args__ = (
        UniqueConstraint("turn_id", "seq", name="uq_agent_events_turn_seq"),
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


class AgentAction(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "agent_actions"

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
    input: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    input_preview: Mapped[str | None] = mapped_column(Text, nullable=True)
    redacted_input: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    risk_level: Mapped[str] = mapped_column(String(30), nullable=False, default="read")
    risk_reasons: Mapped[list | None] = mapped_column(JSON, nullable=True)
    read_scope: Mapped[list | None] = mapped_column(JSON, nullable=True)
    write_scope: Mapped[list | None] = mapped_column(JSON, nullable=True)
    affected_resources: Mapped[list | None] = mapped_column(JSON, nullable=True)
    permission_decision: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default=AgentActionStatus.REQUESTED,
        index=True,
    )
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    audit_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    rollback_hint: Mapped[str | None] = mapped_column(Text, nullable=True)
    artifact_policy: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    session = relationship("AgentSession", back_populates="actions")
    turn = relationship("AgentTurn", back_populates="actions")
    parent_action = relationship("AgentAction", remote_side="AgentAction.id")
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
