from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class WorkflowSource(str, Enum):
    NFCORE = "nf-core"
    GITHUB = "github"
    LOCAL = "local"


class WorkflowEngine(str, Enum):
    NEXTFLOW = "nextflow"
    WDL = "wdl"


class WorkflowBase(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str
    description: str | None = None
    source: WorkflowSource
    engine: WorkflowEngine
    source_ref: str | None = None
    entrypoint_relpath: str | None = None
    bundle_kind: str | None = None
    version: str
    estimated_time: str | None = None
    container_registry_id: UUID | None = None
    schema_json_data: dict | None = Field(
        default=None,
        validation_alias="schema_json",
        serialization_alias="schema_json",
    )


class WorkflowCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: WorkflowSource
    name: str | None = None
    version: str | None = None
    engine: WorkflowEngine | None = None
    source_ref: str | None = None
    entrypoint_relpath: str | None = None
    file_name: str | None = None
    bundle_path: str | None = None
    content: str | None = None
    description: str | None = None
    estimated_time: str | None = None
    container_registry_id: UUID | None = None


class WorkflowUpdate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    description: str | None = None
    estimated_time: str | None = None
    schema_json_data: dict | None = Field(
        default=None,
        validation_alias="schema_json",
        serialization_alias="schema_json",
    )


class WorkflowRead(WorkflowBase):
    id: UUID
    created_at: datetime
    updated_at: datetime
