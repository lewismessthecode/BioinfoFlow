from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ProjectBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str | None = None
    external_root_path: str | None = None


class ProjectCreate(ProjectBase):
    pass


class ProjectUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    description: str | None = None
    external_root_path: str | None = None


class ProjectRead(BaseModel):
    id: UUID
    name: str
    description: str | None = None
    storage_mode: str
    project_root: str
    is_default: bool = False
    created_at: datetime
    updated_at: datetime
