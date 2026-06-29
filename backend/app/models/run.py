from __future__ import annotations

from datetime import datetime
from enum import Enum

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class RunStatus(str, Enum):
    PENDING = "pending"
    QUEUED = "queued"
    PREPARING = "preparing"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Run(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'queued', 'preparing', 'running', "
            "'completed', 'failed', 'cancelled')",
            name="ck_runs_status_valid",
        ),
        CheckConstraint(
            "replay_kind IS NULL OR replay_kind IN ('retry', 'resume')",
            name="ck_runs_replay_kind_valid",
        ),
        CheckConstraint("attempt_number >= 1", name="ck_runs_attempt_number_positive"),
        CheckConstraint(
            "("
            "source_run_id IS NULL "
            "AND replay_kind IS NULL "
            "AND replay_idempotency_key IS NULL "
            "AND attempt_number = 1"
            ") OR ("
            "source_run_id IS NOT NULL "
            "AND replay_kind IS NOT NULL "
            "AND replay_idempotency_key IS NOT NULL "
            "AND attempt_number > 1"
            ")",
            name="ck_runs_replay_lineage_complete",
        ),
        CheckConstraint(
            "source_run_id IS NULL OR source_run_id != run_id",
            name="ck_runs_source_not_self",
        ),
        Index(
            "uq_runs_replay_intent",
            "source_run_id",
            "replay_kind",
            "replay_idempotency_key",
            unique=True,
            sqlite_where=text(
                "source_run_id IS NOT NULL "
                "AND replay_kind IS NOT NULL "
                "AND replay_idempotency_key IS NOT NULL"
            ),
            postgresql_where=text(
                "source_run_id IS NOT NULL "
                "AND replay_kind IS NOT NULL "
                "AND replay_idempotency_key IS NOT NULL"
            ),
        ),
    )

    run_id: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    workflow_id: Mapped[str | None] = mapped_column(
        ForeignKey("workflows.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[RunStatus] = mapped_column(
        String(20), default=RunStatus.PENDING.value
    )
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    samplesheet_path: Mapped[str | None] = mapped_column(String(500))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    samples_count: Mapped[int] = mapped_column(Integer, default=0)
    tasks_total: Mapped[int] = mapped_column(Integer, default=0)
    tasks_completed: Mapped[int] = mapped_column(Integer, default=0)
    current_task: Mapped[str | None] = mapped_column(String(100))
    error_message: Mapped[str | None] = mapped_column(Text)
    error_json: Mapped[dict | None] = mapped_column(JSON)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    nextflow_run_name: Mapped[str | None] = mapped_column(String(100))
    source_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("runs.run_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    replay_kind: Mapped[str | None] = mapped_column(String(20))
    replay_idempotency_key: Mapped[str | None] = mapped_column(String(128))
    attempt_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    project = relationship("Project", back_populates="runs")
    workflow = relationship("Workflow", back_populates="runs")
