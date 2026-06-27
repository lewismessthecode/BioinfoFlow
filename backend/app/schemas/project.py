from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


ProjectStorageMode = Literal["managed", "external", "remote"]


class ProjectBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    description: str | None = None
    external_root_path: str | None = Field(default=None, max_length=500)
    remote_connection_id: UUID | None = None
    remote_root_path: str | None = Field(default=None, max_length=1000)

    @field_validator("name", mode="before")
    @classmethod
    def _strip_name(cls, value: str) -> str:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("external_root_path", "remote_root_path", mode="before")
    @classmethod
    def _strip_optional_path(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value


class ProjectCreate(ProjectBase):
    @model_validator(mode="after")
    def _validate_storage_fields(self):
        if bool(self.remote_connection_id) != bool(self.remote_root_path):
            raise ValueError("remote_connection_id and remote_root_path must be provided together")
        if self.remote_connection_id and self.external_root_path:
            raise ValueError("remote projects cannot also set external_root_path")
        return self


class ProjectUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = None
    external_root_path: str | None = Field(default=None, max_length=500)
    remote_connection_id: UUID | None = None
    remote_root_path: str | None = Field(default=None, max_length=1000)

    @field_validator("name", mode="before")
    @classmethod
    def _strip_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("external_root_path", "remote_root_path", mode="before")
    @classmethod
    def _strip_optional_path(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value


class ProjectRead(BaseModel):
    id: UUID
    name: str
    description: str | None = None
    storage_mode: ProjectStorageMode
    external_root_path: str | None = None
    remote_connection_id: UUID | None = None
    remote_root_path: str | None = None
    project_root: str
    is_default: bool = False
    created_at: datetime
    updated_at: datetime
