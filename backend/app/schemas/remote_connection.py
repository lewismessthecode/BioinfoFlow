from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


RemoteConnectionAuthMethod = Literal["ssh_config", "key_file", "agent"]
RemoteConnectionStatus = Literal["unknown", "online", "offline", "error"]


class RemoteConnectionBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(default=22, ge=1, le=65535)
    username: str = Field(min_length=1, max_length=120)
    auth_method: RemoteConnectionAuthMethod = "ssh_config"
    ssh_alias: str | None = Field(default=None, max_length=255)
    key_path: str | None = Field(default=None, max_length=500)
    skill_instructions: str | None = None

    @field_validator("name", "host", "username", mode="before")
    @classmethod
    def _strip_required_string(cls, value: str) -> str:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("ssh_alias", "key_path", mode="before")
    @classmethod
    def _strip_optional_string(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value


class RemoteConnectionCreate(RemoteConnectionBase):
    pass


class RemoteConnectionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=120)
    host: str | None = Field(default=None, min_length=1, max_length=255)
    port: int | None = Field(default=None, ge=1, le=65535)
    username: str | None = Field(default=None, min_length=1, max_length=120)
    auth_method: RemoteConnectionAuthMethod | None = None
    ssh_alias: str | None = Field(default=None, max_length=255)
    key_path: str | None = Field(default=None, max_length=500)
    skill_instructions: str | None = None

    @field_validator("name", "host", "username", mode="before")
    @classmethod
    def _strip_required_string(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("ssh_alias", "key_path", mode="before")
    @classmethod
    def _strip_optional_string(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value


class RemoteConnectionRead(BaseModel):
    id: UUID
    workspace_id: UUID
    name: str
    host: str
    port: int
    username: str
    auth_method: RemoteConnectionAuthMethod
    ssh_alias: str | None = None
    key_path: str | None = None
    skill_instructions: str | None = None
    last_status: RemoteConnectionStatus
    last_error: str | None = None
    last_checked_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class RemoteConnectionTestRead(BaseModel):
    status: RemoteConnectionStatus
    error: str | None = None
    checked_at: datetime
    connection: RemoteConnectionRead
