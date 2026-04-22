from __future__ import annotations

from enum import Enum

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
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

    run_id: Mapped[str] = mapped_column(
        String(50),
        ForeignKey("runs.run_id"),
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
