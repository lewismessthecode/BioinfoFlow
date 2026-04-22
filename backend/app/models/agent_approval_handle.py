from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class AgentApprovalHandleStatus:
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class AgentApprovalHandle(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "agent_approval_handles"

    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    response_id: Mapped[str] = mapped_column(
        ForeignKey("agent_response_handles.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    call_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=AgentApprovalHandleStatus.PENDING,
        index=True,
    )
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    conversation = relationship("Conversation", back_populates="approval_handles")
    response = relationship("AgentResponseHandle", back_populates="approval_handles")
