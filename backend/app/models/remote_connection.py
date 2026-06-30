from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class RemoteConnectionAuthMethod:
    PASSWORD = "password"
    PRIVATE_KEY = "private_key"
    SSH_CONFIG = "ssh_config"
    KEY_FILE = "key_file"
    AGENT = "agent"

    VALUES = (PASSWORD, PRIVATE_KEY, SSH_CONFIG, KEY_FILE, AGENT)


class RemoteConnectionStatus:
    UNKNOWN = "unknown"
    ONLINE = "online"
    OFFLINE = "offline"
    ERROR = "error"

    VALUES = (UNKNOWN, ONLINE, OFFLINE, ERROR)


class RemoteConnection(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "remote_connections"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "name",
            name="uq_remote_connections_workspace_name",
        ),
        CheckConstraint(
            "port >= 1 AND port <= 65535",
            name="ck_remote_connections_port_range",
        ),
        CheckConstraint(
            "auth_method IN ('password', 'private_key', 'ssh_config', 'key_file', 'agent')",
            name="ck_remote_connections_auth_method",
        ),
        CheckConstraint(
            "last_status IN ('unknown', 'online', 'offline', 'error')",
            name="ck_remote_connections_last_status",
        ),
    )

    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    host: Mapped[str] = mapped_column(String(255), nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False, default=22)
    username: Mapped[str] = mapped_column(String(120), nullable=False)
    auth_method: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=RemoteConnectionAuthMethod.PASSWORD,
    )
    ssh_alias: Mapped[str | None] = mapped_column(String(255), nullable=True)
    key_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    encrypted_password: Mapped[str | None] = mapped_column(Text, nullable=True)
    encrypted_private_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    encrypted_passphrase: Mapped[str | None] = mapped_column(Text, nullable=True)
    skill_instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=RemoteConnectionStatus.UNKNOWN,
        index=True,
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    workspace = relationship("Workspace")
