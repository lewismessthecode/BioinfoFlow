from __future__ import annotations

from sqlalchemy import Boolean, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin
from app.workspace import (
    DEFAULT_WORKSPACE_ID,
    DEFAULT_WORKSPACE_NAME,
    DEFAULT_WORKSPACE_SLUG,
)


class Workspace(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "workspaces"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=DEFAULT_WORKSPACE_ID
    )
    name: Mapped[str] = mapped_column(
        String(120), nullable=False, default=DEFAULT_WORKSPACE_NAME
    )
    slug: Mapped[str] = mapped_column(
        String(120), nullable=False, unique=True, default=DEFAULT_WORKSPACE_SLUG
    )
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    memberships = relationship(
        "WorkspaceMembership",
        back_populates="workspace",
        cascade="all, delete-orphan",
    )
    projects = relationship("Project", back_populates="workspace", cascade="all, delete")


class WorkspaceMembership(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "workspace_memberships"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "user_id",
            name="uq_workspace_memberships_workspace_user",
        ),
    )

    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="member")

    workspace = relationship("Workspace", back_populates="memberships")
