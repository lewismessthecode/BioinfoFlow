from __future__ import annotations

from datetime import datetime
from enum import Enum

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
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

    project = relationship("Project", back_populates="runs")
    workflow = relationship("Workflow", back_populates="runs")
