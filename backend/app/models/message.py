from __future__ import annotations

from enum import Enum

from sqlalchemy import JSON, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class MessageRole(str, Enum):
    USER = "user"
    AGENT = "agent"
    SYSTEM = "system"


class MessageType(str, Enum):
    TEXT = "text"
    THINKING = "thinking"
    THINKING_CONTENT = "thinking_content"
    ARTIFACT = "artifact"
    PLAN = "plan"
    STATUS = "status"
    COMPLETION = "completion"
    # Stream-only types (not persisted to DB)
    TEXT_DELTA = "text_delta"
    THINKING_DELTA = "thinking_delta"
    TOOL_CALL_START = "tool_call_start"
    TOOL_CALL_END = "tool_call_end"
    ERROR = "error"


class Message(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "messages"

    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[str | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=True
    )
    role: Mapped[MessageRole] = mapped_column(String(20), nullable=False)
    type: Mapped[MessageType] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    message_metadata: Mapped[dict | None] = mapped_column("metadata", JSON)

    conversation = relationship("Conversation", back_populates="messages")
    project = relationship("Project")
