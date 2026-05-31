from __future__ import annotations

from enum import Enum

from sqlalchemy import JSON, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class ImageStatus(str, Enum):
    LOCAL = "local"
    REMOTE = "remote"
    PULLING = "pulling"
    FAILED = "failed"


class DockerImage(Base, UUIDMixin, TimestampMixin):
    """Metadata mirrored from the host Docker daemon.

    Docker images are instance-level infrastructure resources, so these rows are
    intentionally not scoped to a workspace.
    """

    __tablename__ = "docker_images"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    tag: Mapped[str] = mapped_column(String(100), nullable=False)
    full_name: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[ImageStatus] = mapped_column(String(20), default=ImageStatus.REMOTE)
    registry: Mapped[str] = mapped_column(String(200), nullable=False)
    pull_progress: Mapped[int | None] = mapped_column(Integer)
    error_message: Mapped[str | None] = mapped_column(Text)
    labels: Mapped[dict | None] = mapped_column(JSON)
    env: Mapped[list[str] | None] = mapped_column(JSON)
    entrypoint: Mapped[list[str] | None] = mapped_column(JSON)
