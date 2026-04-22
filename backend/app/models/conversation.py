from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class PolicyMode:
    """Execution policy mode constants."""

    SAFE_AUTO = "SAFE_AUTO"  # Auto-execute low-risk, require approval for high-risk


class ConversationStorageBackend:
    """Conversation storage backends."""

    LEGACY = "legacy"
    HERMES = "hermes"


class Conversation(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "conversations"

    title: Mapped[str | None] = mapped_column(String(200))
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    policy_mode: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=PolicyMode.SAFE_AUTO,
        doc="Execution policy: SAFE_AUTO requires approval for high-risk actions",
    )
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    created_by_user_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, index=True
    )
    storage_backend: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=ConversationStorageBackend.LEGACY,
        index=True,
    )
    hermes_session_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        unique=True,
        index=True,
    )
    workspace_binding_id: Mapped[str | None] = mapped_column(
        String(36),
        nullable=True,
        index=True,
    )

    execution_policy: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
        doc=(
            "Per-conversation execution mode override. NULL falls back to "
            "settings.agent_execution_policy. Valid values: 'auto' "
            "(default — approve ACT_HIGH), 'approve_all' (also approve "
            "ACT_LOW), 'bypass' (auto-allow everything, including "
            "ACT_HIGH). User-settable via the composer mode picker."
        ),
    )

    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )

    project = relationship("Project", back_populates="conversations")
    messages = relationship(
        "Message", back_populates="conversation", cascade="all, delete"
    )
    approvals = relationship(
        "AgentApproval", back_populates="conversation", cascade="all, delete"
    )
    response_handles = relationship(
        "AgentResponseHandle", back_populates="conversation", cascade="all, delete"
    )
    approval_handles = relationship(
        "AgentApprovalHandle", back_populates="conversation", cascade="all, delete"
    )
