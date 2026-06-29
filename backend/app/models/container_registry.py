from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class ContainerRegistryCredentialSource:
    NONE = "none"
    ENV = "env"
    STORED = "stored"

    VALUES = (NONE, ENV, STORED)


class ContainerRegistryStatus:
    UNTESTED = "untested"
    OK = "ok"
    ERROR = "error"

    VALUES = (UNTESTED, OK, ERROR)

    # Compatibility with the shorter names used by earlier registry drafts.
    UNKNOWN = UNTESTED
    ONLINE = OK


RegistryCredentialSource = ContainerRegistryCredentialSource
RegistryStatus = ContainerRegistryStatus


class ContainerRegistry(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "container_registries"
    __table_args__ = (
        CheckConstraint(
            "credential_source IN ('none', 'env', 'stored')",
            name="ck_container_registries_credential_source",
        ),
        CheckConstraint(
            "last_status IN ('untested', 'ok', 'error')",
            name="ck_container_registries_last_status",
        ),
        Index(
            "uq_container_registries_default_singleton",
            "is_default",
            unique=True,
            sqlite_where=text("is_default = true"),
            postgresql_where=text("is_default = true"),
        ),
    )

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    endpoint: Mapped[str] = mapped_column(String(500), nullable=False)
    namespace: Mapped[str | None] = mapped_column(String(255), nullable=True)
    insecure: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_default: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        index=True,
    )
    credential_source: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=ContainerRegistryCredentialSource.NONE,
    )
    env_username_var: Mapped[str | None] = mapped_column(String(120), nullable=True)
    env_password_var: Mapped[str | None] = mapped_column(String(120), nullable=True)
    encrypted_username: Mapped[str | None] = mapped_column(Text, nullable=True)
    encrypted_password: Mapped[str | None] = mapped_column(Text, nullable=True)
    credential_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    username_hint: Mapped[str | None] = mapped_column(String(120), nullable=True)
    password_hint: Mapped[str | None] = mapped_column(String(120), nullable=True)
    last_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=ContainerRegistryStatus.UNTESTED,
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    updated_by: Mapped[str | None] = mapped_column(String(36), nullable=True)

    projects = relationship("Project", back_populates="container_registry")
