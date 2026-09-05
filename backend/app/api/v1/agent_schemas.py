"""HTTP schemas and presentation mappers for the Agent API.

The Agent router is intentionally kept as an HTTP adapter: request validation,
response schemas and conversion of persistence records to wire-safe payloads
live here, while route handlers retain orchestration and HTTP concerns.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.agent_harness import AgentHarnessArtifact, AgentHarnessAttachment
from app.services.agent_harness.contracts import (
    EnvironmentScope,
    PermissionMode,
    WorkspaceAccess,
)
from app.services.agent_harness.projection import artifact_view


class AgentSessionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    project_id: UUID | None = None
    title: str | None = Field(default=None, max_length=200)
    permission_mode: PermissionMode = "ask_dangerous"
    workspace_access: WorkspaceAccess = "read_write"
    environment_scope: EnvironmentScope = Field(default_factory=EnvironmentScope)
    model_id: UUID | None = None
    profile_id: UUID | None = None
    provider: str | None = Field(default=None, min_length=1, max_length=200)
    model: str | None = Field(default=None, min_length=1, max_length=500)
    metadata: dict | None = None

    @model_validator(mode="after")
    def validate_model_selector(self) -> AgentSessionCreate:
        provider_selected = self.provider is not None or self.model is not None
        if provider_selected and (self.provider is None or self.model is None):
            raise ValueError("provider and model must be supplied together")
        selector_count = sum(
            (
                self.model_id is not None,
                self.profile_id is not None,
                provider_selected,
            )
        )
        if selector_count > 1:
            raise ValueError(
                "choose only one model selector: model_id, profile_id, or provider and model"
            )
        return self


class AgentSessionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str | None = Field(default=None, max_length=200)
    permission_mode: PermissionMode | None = None
    workspace_access: WorkspaceAccess | None = None
    environment_scope: EnvironmentScope | None = None
    status: Literal["active", "archived"] | None = None
    model_id: UUID | None = None
    profile_id: UUID | None = None
    provider: str | None = Field(default=None, min_length=1, max_length=200)
    model: str | None = Field(default=None, min_length=1, max_length=500)

    @model_validator(mode="after")
    def validate_update(self) -> AgentSessionUpdate:
        if not self.model_fields_set:
            raise ValueError("at least one session setting is required")
        for field_name in (
            "permission_mode",
            "workspace_access",
            "environment_scope",
            "status",
        ):
            if (
                field_name in self.model_fields_set
                and getattr(self, field_name) is None
            ):
                raise ValueError(f"{field_name} cannot be null")
        selector_fields = {"model_id", "profile_id", "provider", "model"}
        if selector_fields & self.model_fields_set:
            provider_selected = self.provider is not None or self.model is not None
            if provider_selected and (self.provider is None or self.model is None):
                raise ValueError("provider and model must be supplied together")
            selector_count = sum(
                (
                    self.model_id is not None,
                    self.profile_id is not None,
                    provider_selected,
                )
            )
            if selector_count != 1:
                raise ValueError(
                    "choose exactly one model selector: model_id, profile_id, "
                    "or provider and model"
                )
        return self


class AgentSettingsRead(BaseModel):
    custom_instructions: str = ""


class AgentSettingsUpdate(BaseModel):
    custom_instructions: str = Field(default="", max_length=20_000)


class AgentEnvironmentView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    kind: Literal["local", "ssh"]
    label: str
    description: str | None = None
    status: Literal["online", "offline", "error", "unknown"]


class AgentSessionSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    title: str | None = None
    project_id: UUID | None = None
    permission_mode: PermissionMode
    workspace_access: WorkspaceAccess
    status: Literal["active", "archived", "closing", "deleted"]
    created_at: datetime
    updated_at: datetime


class AgentAttachmentView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    session_id: UUID
    workspace_id: UUID
    user_id: str
    kind: str
    source: str
    filename: str
    mime_type: str | None = None
    size_bytes: int = Field(ge=0)
    file_count: int | None = Field(default=None, ge=0)
    image_width: int | None = Field(default=None, ge=0)
    image_height: int | None = Field(default=None, ge=0)
    status: str
    metadata: dict | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class AgentArtifactView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_id: UUID
    id: UUID
    session_id: UUID
    run_id: UUID | None = None
    type: str
    title: str
    summary: str | None = None
    payload: dict | None = None
    location: str | None = None
    media_type: str | None = None
    status: Literal["ready", "metadata_only"]
    resource_ref: dict | None = None
    created_at: datetime
    updated_at: datetime


class DeletedResource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    deleted: Literal[True]


def model_selection(
    payload: AgentSessionCreate | AgentSessionUpdate,
) -> dict[str, str] | None:
    """Convert the validated model selector into the factory's wire shape."""

    if payload.model_id:
        return {"model_id": str(payload.model_id)}
    if payload.profile_id:
        return {"profile_id": str(payload.profile_id)}
    if payload.provider and payload.model:
        return {"provider": payload.provider, "model": payload.model}
    return None


def attachment_data(attachment: AgentHarnessAttachment) -> dict:
    return {
        "id": str(attachment.id),
        "session_id": str(attachment.session_id),
        "workspace_id": str(attachment.workspace_id),
        "user_id": attachment.user_id,
        "kind": attachment.kind,
        "source": attachment.source,
        "filename": attachment.filename,
        "mime_type": attachment.mime_type,
        "size_bytes": attachment.size_bytes,
        "file_count": attachment.file_count,
        "image_width": attachment.image_width,
        "image_height": attachment.image_height,
        "status": attachment.status,
        "metadata": attachment.attachment_metadata,
        "error_message": attachment.error_message,
        "created_at": attachment.created_at.isoformat(),
        "updated_at": attachment.updated_at.isoformat(),
    }


def artifact_data(artifact: AgentHarnessArtifact) -> dict:
    return artifact_view(artifact)


__all__ = [
    "AgentArtifactView",
    "AgentAttachmentView",
    "AgentEnvironmentView",
    "AgentSessionCreate",
    "AgentSessionSummary",
    "AgentSessionUpdate",
    "AgentSettingsRead",
    "AgentSettingsUpdate",
    "DeletedResource",
    "artifact_data",
    "attachment_data",
    "model_selection",
]
