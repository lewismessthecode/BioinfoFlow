from __future__ import annotations

from fastapi import APIRouter, Depends, Request, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.api.error_handler import handle_api_errors
from app.auth.session import AuthUser
from app.config import settings
from app.schemas.image import ImagePullRequest, ImageRead
from app.services.image_service import (
    DockerUnavailableError,
    ImageDeleteConflictError,
    ImageService,
)
from app.utils.authorization import can_perform_destructive_business_action
from app.utils.exceptions import AppError
from app.utils.responses import error_response, success_response


router = APIRouter(prefix="/images", tags=["images"])


def _serialize(image) -> dict:
    return ImageRead.model_validate(image, from_attributes=True).model_dump(
        mode="json", by_alias=True
    )


@router.get("")
async def list_images(
    request: Request,
    limit: int = 20,
    cursor: str | None = None,
    search: str | None = None,
    status: str | None = None,
    force_sync: bool = False,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = ImageService(db)
    images, pagination, docker_status = await service.list_images(
        limit=limit,
        cursor=cursor,
        search=search,
        status=status,
        force_sync=force_sync,
    )
    data = [_serialize(image) for image in images]
    return success_response(
        data, request=request, pagination=pagination, status=docker_status
    )


@router.get("/{image_id}")
async def get_image(
    image_id: str,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = ImageService(db)
    image = await service.get_image(image_id)
    if not image:
        return error_response(
            code="NOT_FOUND",
            message="Image not found",
            status_code=404,
            request=request,
        )
    return success_response(_serialize(image), request=request)


@router.post("/pull")
@handle_api_errors
async def pull_image(
    payload: ImagePullRequest,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = ImageService(db)
    try:
        image = await service.pull_image(
            name=payload.name,
            tag=payload.tag or "latest",
            registry=payload.registry or "docker.io",
            project_id=str(payload.project_id) if payload.project_id else None,
            user_id=user.id,
            workspace_id=user.workspace_id,
            registry_id=str(payload.registry_id) if payload.registry_id else None,
        )
    except DockerUnavailableError as exc:
        return error_response(
            code="SERVICE_UNAVAILABLE",
            message=str(exc),
            status_code=503,
            request=request,
        )
    except AppError:
        raise
    except Exception:  # noqa: BLE001
        return error_response(
            code="DOCKER_ERROR",
            message="Failed to pull image",
            status_code=500,
            request=request,
        )
    return success_response(_serialize(image), request=request, status_code=202)


@router.post("/load")
@handle_api_errors
async def load_image_tarball(
    request: Request,
    file: UploadFile = File(...),
    project_id: str | None = Form(None),
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = ImageService(db)
    content = await file.read()
    if len(content) > settings.max_image_upload_size_bytes:
        return error_response(
            code="FILE_TOO_LARGE",
            message=f"Image tarball exceeds maximum upload size of {settings.max_image_upload_size_bytes} bytes",
            status_code=413,
            request=request,
        )
    try:
        images = await service.load_image_tarball(
            content=content,
            project_id=project_id,
            user_id=user.id,
            workspace_id=user.workspace_id,
        )
    except DockerUnavailableError as exc:
        return error_response(
            code="SERVICE_UNAVAILABLE",
            message=str(exc),
            status_code=503,
            request=request,
        )
    except AppError:
        raise
    except Exception:  # noqa: BLE001
        return error_response(
            code="DOCKER_ERROR",
            message="Failed to load image tarball",
            status_code=500,
            request=request,
        )
    data = [_serialize(image) for image in images]
    return success_response(data, request=request, status_code=201)


@router.delete("/{image_id}")
@handle_api_errors
async def delete_image(
    image_id: str,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = ImageService(db)
    image = await service.get_image(image_id)
    if not image:
        return error_response(
            code="NOT_FOUND",
            message="Image not found",
            status_code=404,
            request=request,
        )
    if not can_perform_destructive_business_action(user.role):
        return error_response(
            code="FORBIDDEN",
            message="Deleting images requires an administrator in team mode",
            status_code=403,
            request=request,
        )
    try:
        deleted = await service.delete_image(image)
    except ImageDeleteConflictError as exc:
        return error_response(
            code=exc.code,
            message=str(exc),
            details=exc.details,
            status_code=409,
            request=request,
        )
    except Exception:  # noqa: BLE001
        return error_response(
            code="DOCKER_ERROR",
            message="Failed to delete image",
            status_code=500,
            request=request,
        )
    if not deleted:
        return error_response(
            code="DOCKER_ERROR",
            message="Failed to delete image",
            status_code=500,
            request=request,
        )
    return success_response(None, request=request, status_code=204)
