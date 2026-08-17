from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import GUID
from app.models.base import Base, TimestampMixin, UUIDMixin


class AgentModelTrace(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "agent_model_traces"
    __table_args__ = (
        Index(
            "ix_agent_model_traces_session_started",
            "session_id",
            "started_at",
            "id",
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
    iteration: Mapped[int] = mapped_column(Integer, nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False)
    context_through_sequence: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    model: Mapped[str] = mapped_column(String(500), nullable=False)
    wire_protocol: Mapped[str] = mapped_column(String(40), nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="pending", index=True
    )
    context_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    request_payload: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    response_payload: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    usage: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    provider_response_id: Mapped[str | None] = mapped_column(String(500), nullable=True)
    finish_reason: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    request_prepared_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    first_byte_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


__all__ = ["AgentModelTrace"]
