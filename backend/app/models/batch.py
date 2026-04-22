from __future__ import annotations

from enum import Enum

from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class BatchStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Batch(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "batches"

    batch_id: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=BatchStatus.PENDING.value
    )
    total_runs: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed_runs: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_runs: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    description: Mapped[str | None] = mapped_column(Text)

    project = relationship("Project")
    batch_runs = relationship(
        "BatchRun",
        back_populates="batch",
        cascade="all, delete-orphan",
    )


class BatchRun(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "batch_runs"
    __table_args__ = (
        UniqueConstraint("batch_id", "run_id", name="uq_batch_runs_batch_run"),
    )

    batch_id: Mapped[str] = mapped_column(
        ForeignKey("batches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    run_id: Mapped[str] = mapped_column(
        ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True
    )

    batch = relationship("Batch", back_populates="batch_runs")
    run = relationship("Run")
