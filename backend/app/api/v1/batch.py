from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    declare_agent_token_access,
    get_current_user,
    get_db,
    require_agent_scope,
)
from app.api.error_handler import handle_api_errors
from app.auth.session import AuthUser
from app.schemas.run import BatchCreate, RunCreate
from app.services.batch_service import BatchService
from app.utils.responses import error_response, success_response


router = APIRouter(
    prefix="/runs/batch",
    tags=["runs"],
    dependencies=[Depends(declare_agent_token_access)],
)


@router.post("")
@handle_api_errors
async def create_batch(
    payload: BatchCreate,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    require_agent_scope(request, project_id=str(payload.project_id))
    service = BatchService(db)
    batch = await service.create_batch(
        runs=[
            RunCreate(
                project_id=payload.project_id,
                workflow_id=spec.workflow_id,
                values=spec.values,
                options=spec.options,
            )
            for spec in payload.runs
        ],
        project_id=str(payload.project_id),
        description=payload.description,
        priority=payload.priority,
        user_id=user.id,
        workspace_id=user.workspace_id,
    )
    return success_response(batch, request=request, status_code=202)


@router.get("/{batch_id}")
async def get_batch(
    batch_id: str,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = BatchService(db)
    batch = await service.get_batch(
        batch_id,
        user_id=user.id,
        workspace_id=user.workspace_id,
    )
    if batch is None:
        return error_response(
            code="NOT_FOUND",
            message="Batch not found",
            status_code=404,
            request=request,
        )
    require_agent_scope(request, project_id=str(batch["project_id"]))
    return success_response(batch, request=request)


@router.post("/{batch_id}/cancel")
@handle_api_errors
async def cancel_batch(
    batch_id: str,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = BatchService(db)
    existing = await service.get_batch(
        batch_id,
        user_id=user.id,
        workspace_id=user.workspace_id,
    )
    if existing is not None:
        require_agent_scope(request, project_id=str(existing["project_id"]))
    batch = await service.cancel_batch(
        batch_id,
        user_id=user.id,
        workspace_id=user.workspace_id,
    )
    return success_response(batch, request=request)
