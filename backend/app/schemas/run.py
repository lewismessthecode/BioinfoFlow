from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RunStatus(str, Enum):
    PENDING = "pending"
    QUEUED = "queued"
    PREPARING = "preparing"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RunError(BaseModel):
    """Structured failure reason attached to a run.

    Replaces the freeform ``error_message`` string. The stage + code are
    stable identifiers the frontend can localize; ``hint`` is short
    remediation copy shown alongside the message.
    """

    stage: Literal["validation", "preparation", "execution", "post"]
    code: str
    message: str
    hint: str | None = None


class RunErrorStage:
    """Stable string constants for ``RunError.stage``.

    Why: the schema's ``Literal`` only validates incoming JSON, so an emit
    site that mistypes ``"executon"`` would silently produce an unparseable
    error row at read time. Pin every write through these constants.
    """

    VALIDATION = "validation"
    PREPARATION = "preparation"
    EXECUTION = "execution"
    POST = "post"


class RunErrorCode:
    """Stable string constants for ``RunError.code``. Add new codes here so
    every emit site shares one source of truth."""

    INVALID_FORM_VALUES = "INVALID_FORM_VALUES"
    ENGINE_NONZERO_EXIT = "ENGINE_NONZERO_EXIT"
    WORKER_LOST = "WORKER_LOST"
    RUN_STALE = "RUN_STALE"
    PATH_OUTSIDE_ALLOWED_ROOT = "PATH_OUTSIDE_ALLOWED_ROOT"
    ASSET_NOT_FOUND = "ASSET_NOT_FOUND"


class RunBase(BaseModel):
    run_id: str
    project_id: UUID
    workflow_id: UUID | None = None
    status: RunStatus
    config: dict
    samplesheet_path: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_seconds: int | None = None
    samples_count: int
    tasks_total: int
    tasks_completed: int
    current_task: str | None = None
    error_message: str | None = None
    error: RunError | None = Field(default=None, validation_alias="error_json")
    last_heartbeat_at: datetime | None = None
    nextflow_run_name: str | None = None


class RunRead(RunBase):
    id: UUID
    created_at: datetime
    updated_at: datetime


class RunOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile: str | None = None
    max_retries: int | None = Field(default=None, ge=0, le=10)
    timeout_seconds: int | None = Field(default=None, ge=1)
    resume_from_run_id: str | None = None


class RunCreate(BaseModel):
    """Canonical run submission envelope.

    Frontend and agent tools post ``{values, options}`` keyed by form field ids
    derived from ``/workflows/{id}/form-spec``. The backend translates those
    into engine-ready inputs via ``run_envelope_bridge``.
    """

    model_config = ConfigDict(extra="forbid")

    project_id: UUID
    workflow_id: UUID

    values: dict = Field(default_factory=dict)
    options: RunOptions | None = None

    @model_validator(mode="after")
    def _require_values(self):
        if not isinstance(self.values, dict):
            raise ValueError("values must be an object keyed by form field ids")
        return self


class RunUploadRead(BaseModel):
    uri: str
    path: str
    filename: str


class BatchRunSpec(BaseModel):
    """Batch run entry using the same canonical envelope fields as RunCreate."""

    model_config = ConfigDict(extra="forbid")

    workflow_id: UUID
    values: dict = Field(default_factory=dict)
    options: RunOptions | None = None

    @model_validator(mode="after")
    def _require_values(self):
        if not isinstance(self.values, dict):
            raise ValueError("values must be an object keyed by form field ids")
        return self


class BatchCreate(BaseModel):
    project_id: UUID
    runs: list[BatchRunSpec] = Field(min_length=2, max_length=500)
    description: str | None = None
    priority: str = "normal"


class RunResumeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    config_overrides: dict | None = None


class RunRetryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    config_overrides: dict | None = None


class RetryPolicyCreate(BaseModel):
    max_retries: int = Field(default=0, ge=0, le=10)
    delay_seconds: float = Field(default=30, ge=0)
    backoff_multiplier: float = Field(default=2.0, ge=1.0)
    max_delay_seconds: float = Field(default=600, ge=0)
    retry_on: list[str] = Field(default_factory=list)
