from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.auth.session import AuthUser
from app.schemas.project import ProjectCreate, ProjectRead, ProjectUpdate
from app.services.project_service import ProjectService
from app.utils.authorization import (
    can_manage_external_roots,
    can_perform_destructive_business_action,
)
from app.utils.responses import error_response, success_response


router = APIRouter(prefix="/projects", tags=["projects"])


def _serialize(project) -> dict:
    return ProjectRead.model_validate(project, from_attributes=True).model_dump(
        mode="json", by_alias=True
    )


@router.get("")
async def list_projects(
    request: Request,
    limit: int = 20,
    cursor: str | None = None,
    search: str | None = None,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = ProjectService(db)
    projects, pagination = await service.list_projects(
        workspace_id=user.workspace_id,
        limit=limit,
        cursor=cursor,
        search=search,
    )
    data = [_serialize(project) for project in projects]
    return success_response(data, request=request, pagination=pagination)


@router.post("")
async def create_project(
    payload: ProjectCreate,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if (
        payload.external_root_path or payload.remote_connection_id
    ) and not can_manage_external_roots(user.role):
        return error_response(
            code="FORBIDDEN",
            message="External and remote project roots are restricted to administrators",
            status_code=403,
            request=request,
        )
    service = ProjectService(db)
    project_data = payload.model_dump(mode="json", by_alias=True)
    project_data["workspace_id"] = user.workspace_id
    project = await service.create_project(project_data, user_id=user.id)
    return success_response(_serialize(project), request=request, status_code=201)


@router.get("/default")
async def get_default_project(
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get or create the workspace default (uncategorized) project."""
    service = ProjectService(db)
    project = await service.get_or_create_default(
        workspace_id=user.workspace_id,
        workspace_slug="bioinfoflow-team",
        user_id=user.id,
    )
    return success_response(_serialize(project), request=request)


@router.get("/{project_id}")
async def get_project(
    project_id: str,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = ProjectService(db)
    project = await service.get_project(project_id, workspace_id=user.workspace_id)
    if not project:
        return error_response(
            code="NOT_FOUND",
            message="Project not found",
            status_code=404,
            request=request,
        )
    return success_response(_serialize(project), request=request)


@router.patch("/{project_id}")
async def update_project(
    project_id: str,
    payload: ProjectUpdate,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = ProjectService(db)
    project = await service.get_project(project_id, workspace_id=user.workspace_id)
    if not project:
        return error_response(
            code="NOT_FOUND",
            message="Project not found",
            status_code=404,
            request=request,
        )
    if (
        payload.external_root_path or payload.remote_connection_id
    ) and not can_manage_external_roots(user.role):
        return error_response(
            code="FORBIDDEN",
            message="External and remote project roots are restricted to administrators",
            status_code=403,
            request=request,
        )
    updated = await service.update_project(
        project, payload.model_dump(mode="json", exclude_unset=True, by_alias=True)
    )
    return success_response(_serialize(updated), request=request)


@router.delete("/{project_id}")
async def delete_project(
    project_id: str,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = ProjectService(db)
    project = await service.get_project(project_id, workspace_id=user.workspace_id)
    if not project:
        return error_response(
            code="NOT_FOUND",
            message="Project not found",
            status_code=404,
            request=request,
        )
    if project.is_default:
        return error_response(
            code="FORBIDDEN",
            message="Cannot delete the default project",
            status_code=403,
            request=request,
        )
    if not can_perform_destructive_business_action(user.role):
        return error_response(
            code="FORBIDDEN",
            message="Deleting projects requires an administrator in team mode",
            status_code=403,
            request=request,
        )
    await service.delete_project(project)
    return success_response(None, request=request, status_code=204)
