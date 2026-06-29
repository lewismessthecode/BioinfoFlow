from __future__ import annotations

from enum import Enum

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class TaskPriority(str, Enum):
    URGENT = "urgent"
    NORMAL = "normal"
    LOW = "low"


class TaskState(str, Enum):
    QUEUED = "queued"
    DISPATCHED = "dispatched"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ScheduledTask(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "scheduled_tasks"
    __table_args__ = (
        Index(
            "uq_scheduled_tasks_active_run",
            "run_id",
            unique=True,
            sqlite_where=text("state IN ('queued', 'dispatched')"),
            postgresql_where=text("state IN ('queued', 'dispatched')"),
        ),
    )

    run_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("runs.run_id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    state: Mapped[str] = mapped_column(
        String(20),
        default=TaskState.QUEUED.value,
        index=True,
        nullable=False,
    )
    priority: Mapped[str] = mapped_column(
        String(20),
        default=TaskPriority.NORMAL.value,
        nullable=False,
    )
    attempt: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    weight: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    delay_until: Mapped[DateTime | None] = mapped_column(
        DateTime(timezone=True),
        index=True,
    )
    dispatched_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[str | None] = mapped_column(Text)
    worker_id: Mapped[str | None] = mapped_column(String(50))
