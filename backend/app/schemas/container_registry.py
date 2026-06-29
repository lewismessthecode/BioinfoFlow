from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


RegistryCredentialSource = Literal["none", "env", "stored"]
RegistryStatus = Literal["untested", "ok", "error"]


class ContainerRegistryCreate(BaseModel):
    name: str
    endpoint: str
    namespace: str | None = None
    insecure: bool = False
    is_default: bool = False
    credential_source: RegistryCredentialSource = "none"
    env_username_var: str | None = None
    env_password_var: str | None = None
    username: str | None = None
    password: str | None = None


class ContainerRegistryUpdate(BaseModel):
    name: str | None = None
    endpoint: str | None = None
    namespace: str | None = None
    insecure: bool | None = None
    is_default: bool | None = None
    credential_source: RegistryCredentialSource | None = None
    env_username_var: str | None = None
    env_password_var: str | None = None
    username: str | None = None
    password: str | None = None


class ContainerRegistryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    endpoint: str
    namespace: str | None = None
    insecure: bool
    is_default: bool
    credential_source: RegistryCredentialSource
    env_username_var: str | None = None
    env_password_var: str | None = None
    username_hint: str | None = None
    password_hint: str | None = None
    last_status: RegistryStatus
    last_error: str | None = None
    last_checked_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ContainerRegistryTestResult(BaseModel):
    registry_id: UUID
    success: bool
    status: RegistryStatus
    error: str | None = None
    checked_at: datetime
