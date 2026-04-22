from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.api.error_handler import handle_api_errors
from app.auth.session import AuthUser
from app.schemas.project_workflow import (
    ProjectWorkflowGroupRead,
    ProjectWorkflowPinRequest,
)
from app.schemas.workflow import WorkflowRead
from app.services.project_workflow_service import ProjectWorkflowService
from app.utils.responses import error_response, success_response


router = APIRouter(prefix="/projects", tags=["projects"])


def _serialize_workflow(workflow) -> dict:
    return WorkflowRead.model_validate(workflow, from_attributes=True).model_dump(
        mode="json", by_alias=True
    )


@router.get("/{project_id}/workflows")
@handle_api_errors
async def list_project_workflows(
    project_id: str,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = ProjectWorkflowService(db)
    try:
        groups = await service.list_project_workflows(project_id=project_id)
    except FileNotFoundError:
        return error_response(
            code="NOT_FOUND",
            message="Project not found",
            status_code=404,
            request=request,
        )

    data = [
        ProjectWorkflowGroupRead.model_validate(
            {
                "source": g["source"],
                "name": g["name"],
                "pinned_workflow": _serialize_workflow(g["pinned_workflow"]),
                "versions": [_serialize_workflow(wf) for wf in g["versions"]],
            }
        ).model_dump(mode="json")
        for g in groups
    ]
    return success_response(data, request=request)


@router.post("/{project_id}/workflows/{workflow_id}:bind")
@handle_api_errors
async def bind_workflow_to_project(
    project_id: str,
    workflow_id: str,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = ProjectWorkflowService(db)
    await service.bind_workflow(project_id=project_id, workflow_id=workflow_id)
    return success_response(
        {"project_id": project_id, "workflow_id": workflow_id},
        request=request,
        status_code=201,
    )


@router.delete("/{project_id}/workflows/{workflow_id}:unbind")
@handle_api_errors
async def unbind_workflow_from_project(
    project_id: str,
    workflow_id: str,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = ProjectWorkflowService(db)
    await service.unbind_workflow(project_id=project_id, workflow_id=workflow_id)
    return success_response(None, request=request, status_code=204)


@router.post("/{project_id}/workflow-pins")
@handle_api_errors(
    PermissionError=("WORKFLOW_NOT_ENABLED_FOR_PROJECT", 403),
    ValueError=("VALIDATION_ERROR", 400),
)
async def set_project_workflow_pin(
    project_id: str,
    payload: ProjectWorkflowPinRequest,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = ProjectWorkflowService(db)
    await service.set_pin(
        project_id=project_id, pinned_workflow_id=str(payload.pinned_workflow_id)
    )
    return success_response(
        {
            "project_id": project_id,
            "pinned_workflow_id": str(payload.pinned_workflow_id),
        },
        request=request,
        status_code=201,
    )
