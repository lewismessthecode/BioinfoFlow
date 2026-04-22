"""Agent approval model for tracking approval requests."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.enums import ApprovalStatus
from app.models.base import Base, TimestampMixin, UUIDMixin


class ApprovalType:
    """Approval type constants."""

    RUN = "run"
    FILE_DIFF = "file_diff"
    CODE_EXEC = "code_exec"


class AgentApproval(Base, UUIDMixin, TimestampMixin):
    """Model for tracking agent approval requests.

    When the agent encounters a high-risk action (e.g., starting a run,
    modifying files, executing code), it creates an approval record and
    waits for user resolution before proceeding.
    """

    __tablename__ = "agent_approvals"

    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    step_id: Mapped[str] = mapped_column(String(100), nullable=False)

    approval_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=ApprovalType.RUN,
    )

    payload: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
        doc="Contains diff, command, run_config, or other context for the approval",
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=ApprovalStatus.PENDING,
        index=True,
    )

    resolved_by: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        doc="User or system that resolved the approval",
    )

    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    conversation = relationship("Conversation", back_populates="approvals")
