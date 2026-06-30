from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


RemoteConnectionAuthMethod = Literal[
    "password",
    "private_key",
    "ssh_config",
    "key_file",
    "agent",
]
RemoteConnectionStatus = Literal["unknown", "online", "offline", "error"]


class RemoteConnectionBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(default=22, ge=1, le=65535)
    username: str = Field(min_length=1, max_length=120)
    auth_method: RemoteConnectionAuthMethod = "password"
    ssh_alias: str | None = Field(default=None, max_length=255)
    key_path: str | None = Field(default=None, max_length=500)
    password: str | None = Field(default=None, max_length=2000)
    private_key: str | None = Field(default=None, max_length=20000)
    passphrase: str | None = Field(default=None, max_length=2000)
    skill_instructions: str | None = None

    @field_validator("name", "host", "username", mode="before")
    @classmethod
    def _strip_required_string(cls, value: str) -> str:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("ssh_alias", "key_path", "password", "private_key", "passphrase", mode="before")
    @classmethod
    def _strip_optional_string(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value

    @model_validator(mode="after")
    def _validate_auth_fields(self):
        _validate_auth_method_fields(
            auth_method=self.auth_method,
            ssh_alias=self.ssh_alias,
            key_path=self.key_path,
            password=self.password,
            private_key=self.private_key,
        )
        return self


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
    password: str | None = Field(default=None, max_length=2000)
    private_key: str | None = Field(default=None, max_length=20000)
    passphrase: str | None = Field(default=None, max_length=2000)
    skill_instructions: str | None = None

    @field_validator("name", "host", "username", mode="before")
    @classmethod
    def _strip_required_string(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("ssh_alias", "key_path", "password", "private_key", "passphrase", mode="before")
    @classmethod
    def _strip_optional_string(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            stripped = value.strip()
            return stripped or None
        return value


def _validate_auth_method_fields(
    *,
    auth_method: RemoteConnectionAuthMethod,
    ssh_alias: str | None,
    key_path: str | None,
    password: str | None = None,
    private_key: str | None = None,
) -> None:
    if auth_method == "password" and not password:
        raise ValueError("password is required when auth_method is password")
    if auth_method == "private_key" and not private_key:
        raise ValueError("private_key is required when auth_method is private_key")
    if auth_method == "ssh_config" and not ssh_alias:
        raise ValueError("ssh_alias is required when auth_method is ssh_config")
    if auth_method == "key_file" and not key_path:
        raise ValueError("key_path is required when auth_method is key_file")
    if auth_method in {"password", "private_key", "agent"} and key_path:
        raise ValueError(f"key_path must be empty when auth_method is {auth_method}")
    if auth_method != "ssh_config" and ssh_alias:
        raise ValueError(f"ssh_alias must be empty when auth_method is {auth_method}")


def validate_remote_connection_auth_fields(
    *,
    auth_method: RemoteConnectionAuthMethod,
    ssh_alias: str | None,
    key_path: str | None,
    password: str | None = None,
    private_key: str | None = None,
) -> None:
    """Validate a complete persisted remote auth configuration."""
    try:
        _validate_auth_method_fields(
            auth_method=auth_method,
            ssh_alias=ssh_alias,
            key_path=key_path,
            password=password,
            private_key=private_key,
        )
    except ValueError as exc:
        from app.utils.exceptions import ValidationError

        raise ValidationError(str(exc)) from exc


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
