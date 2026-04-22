from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel

from app.schemas.workflow import WorkflowRead, WorkflowSource


class ProjectWorkflowGroupRead(BaseModel):
    """A pipeline (source+name) as enabled within a project."""

    source: WorkflowSource
    name: str
    pinned_workflow: WorkflowRead
    versions: list[WorkflowRead]


class ProjectWorkflowPinRequest(BaseModel):
    pinned_workflow_id: UUID
