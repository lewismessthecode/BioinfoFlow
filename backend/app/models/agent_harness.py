from __future__ import annotations

from datetime import datetime
from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import GUID
from app.models.base import Base, TimestampMixin, UUIDMixin


class AgentHarnessSession(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "agent_sessions"

    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    workspace_id: Mapped[str] = mapped_column(
        GUID(),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id: Mapped[str | None] = mapped_column(
        GUID(),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    model_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    workspace_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    permission_mode: Mapped[str] = mapped_column(
        String(30), nullable=False, default="ask_dangerous"
    )
    workspace_access: Mapped[str] = mapped_column(
        String(20), nullable=False, default="read_write"
    )
    settings_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    environment_scope: Mapped[dict] = mapped_column(
        JSON, nullable=False, default=lambda: {"mode": "auto"}
    )
    prompt_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    history_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    command_queue: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    command_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="active", index=True
    )
    closing_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    closing_reason: Mapped[str | None] = mapped_column(String(100), nullable=True)
    session_metadata: Mapped[dict | None] = mapped_column(
        "metadata", JSON, nullable=True
    )


class AgentHarnessRun(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "agent_runs"
    __table_args__ = (
        Index(
            "uq_agent_runs_active_session",
            "session_id",
            unique=True,
            sqlite_where=text("status IN ('queued', 'running', 'waiting_user')"),
            postgresql_where=text("status IN ('queued', 'running', 'waiting_user')"),
        ),
    )

    session_id: Mapped[str] = mapped_column(
        GUID(),
        ForeignKey("agent_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="queued", index=True
    )
    phase: Mapped[str | None] = mapped_column(String(30), nullable=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    model_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    turn_execution_config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    lease_owner: Mapped[str | None] = mapped_column(String(100), nullable=True)
    lease_generation: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    command_queue: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    command_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    draft: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    tool_progress: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)
    checkpoint: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    token_usage: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    termination_reason: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancel_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancel_reason: Mapped[str | None] = mapped_column(String(100), nullable=True)


class AgentHarnessEntry(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "agent_entries"
    __table_args__ = (
        UniqueConstraint(
            "session_id", "sequence", name="uq_agent_entries_session_sequence"
        ),
    )

    session_id: Mapped[str] = mapped_column(
        GUID(),
        ForeignKey("agent_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    run_id: Mapped[str | None] = mapped_column(
        GUID(),
        ForeignKey("agent_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)


class AgentHarnessAttachment(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "agent_attachments"

    session_id: Mapped[str] = mapped_column(
        GUID(),
        ForeignKey("agent_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    workspace_id: Mapped[str] = mapped_column(
        GUID(),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    source: Mapped[str] = mapped_column(String(30), nullable=False)
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(200), nullable=True)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    file_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    image_width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    image_height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="processing"
    )
    attachment_metadata: Mapped[dict | None] = mapped_column(
        "metadata", JSON, nullable=True
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class AgentHarnessArtifact(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "agent_artifacts"

    session_id: Mapped[str] = mapped_column(
        GUID(),
        ForeignKey("agent_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    run_id: Mapped[str | None] = mapped_column(
        GUID(),
        ForeignKey("agent_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    file_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    resource_ref: Mapped[dict | None] = mapped_column(JSON, nullable=True)


__all__ = [
    "AgentHarnessArtifact",
    "AgentHarnessAttachment",
    "AgentHarnessEntry",
    "AgentHarnessRun",
    "AgentHarnessSession",
]
