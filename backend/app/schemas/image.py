from __future__ import annotations

from datetime import datetime
from uuid import UUID
from enum import Enum

from pydantic import BaseModel


class ImageStatus(str, Enum):
    LOCAL = "local"
    REMOTE = "remote"
    PULLING = "pulling"
    FAILED = "failed"


class ImageBase(BaseModel):
    name: str
    tag: str
    full_name: str
    description: str | None = None
    size_bytes: int | None = None
    status: ImageStatus
    registry: str
    pull_progress: int | None = None
    error_message: str | None = None
    labels: dict | None = None
    env: list[str] | None = None
    entrypoint: list[str] | None = None


class ImageRead(ImageBase):
    id: UUID
    created_at: datetime
    updated_at: datetime


class ImagePullRequest(BaseModel):
    name: str
    tag: str | None = None
    registry: str | None = None
    project_id: UUID | None = None
