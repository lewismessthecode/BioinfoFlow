from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin
from app.workspace import DEFAULT_WORKSPACE_ID


class Project(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "projects"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    storage_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="managed")
    external_root_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    created_by_user_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, index=True
    )
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        default=DEFAULT_WORKSPACE_ID,
    )
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    runs = relationship("Run", back_populates="project", cascade="all, delete")
    conversations = relationship(
        "Conversation", back_populates="project", cascade="all, delete"
    )
    workspace = relationship("Workspace", back_populates="projects")

    @property
    def project_root(self) -> str:
        return "asset://project"
