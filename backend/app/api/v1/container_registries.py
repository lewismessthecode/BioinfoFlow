from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_admin
from app.api.error_handler import handle_api_errors
from app.auth.session import AuthUser
from app.schemas.container_registry import (
    ContainerRegistryCreate,
    ContainerRegistryRead,
    ContainerRegistryTestResult,
    ContainerRegistryUpdate,
)
from app.services.container_registry_service import ContainerRegistryService
from app.utils.responses import success_response


router = APIRouter(prefix="/container-registries", tags=["container-registries"])


def _dump(model) -> dict:
    return model.model_dump(mode="json")


def _with_user_context(data: dict, user: AuthUser) -> dict:
    return {
        **data,
        "updated_by": user.id,
    }


@router.get("")
@handle_api_errors
async def list_container_registries(
    request: Request,
    user: AuthUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    del user
    service = ContainerRegistryService(db)
    registries = await service.list_registries()
    return success_response(
        [
            _dump(ContainerRegistryRead.model_validate(service.registry_read_dict(item)))
            for item in registries
        ],
        request=request,
    )


@router.post("")
@handle_api_errors
async def create_container_registry(
    payload: ContainerRegistryCreate,
    request: Request,
    user: AuthUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    service = ContainerRegistryService(db)
    registry = await service.create_registry(
        _with_user_context(payload.model_dump(), user)
    )
    return success_response(
        _dump(ContainerRegistryRead.model_validate(service.registry_read_dict(registry))),
        request=request,
        status_code=201,
    )


@router.get("/{registry_id}")
@handle_api_errors
async def get_container_registry(
    registry_id: str,
    request: Request,
    user: AuthUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    del user
    service = ContainerRegistryService(db)
    registry = await service.get_registry(registry_id)
    return success_response(
        _dump(ContainerRegistryRead.model_validate(service.registry_read_dict(registry))),
        request=request,
    )


@router.patch("/{registry_id}")
@handle_api_errors
async def update_container_registry(
    registry_id: str,
    payload: ContainerRegistryUpdate,
    request: Request,
    user: AuthUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    service = ContainerRegistryService(db)
    registry = await service.update_registry(
        registry_id,
        _with_user_context(payload.model_dump(exclude_unset=True), user),
    )
    return success_response(
        _dump(ContainerRegistryRead.model_validate(service.registry_read_dict(registry))),
        request=request,
    )


@router.delete("/{registry_id}")
@handle_api_errors
async def delete_container_registry(
    registry_id: str,
    request: Request,
    user: AuthUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    del user
    service = ContainerRegistryService(db)
    await service.delete_registry(registry_id)
    return success_response(None, request=request, status_code=204)


@router.post("/{registry_id}/test")
@handle_api_errors
async def test_container_registry(
    registry_id: str,
    request: Request,
    user: AuthUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    del user
    service = ContainerRegistryService(db)
    result = await service.test_registry(registry_id)
    return success_response(
        _dump(ContainerRegistryTestResult.model_validate(result)),
        request=request,
    )
