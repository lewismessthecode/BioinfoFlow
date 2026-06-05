from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.auth.session import AuthUser
from app.schemas.llm import (
    LlmModelCreate,
    LlmModelProfileCreate,
    LlmModelProfileRead,
    LlmModelProfileUpdate,
    LlmModelRead,
    LlmModelUpdate,
    LlmProviderCreate,
    LlmProviderRead,
    LlmProviderTestResult,
    LlmProviderUpdate,
)
from app.services.llm import LlmCatalogService
from app.utils.responses import success_response


router = APIRouter(prefix="/llm", tags=["llm"])


def _dump(model) -> dict:
    return model.model_dump(mode="json")


def _with_user_context(data: dict, user: AuthUser) -> dict:
    return {
        **data,
        "workspace_id": user.workspace_id,
        "user_id": user.id,
        "role": user.role,
    }


@router.get("/providers")
async def list_providers(
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = LlmCatalogService(db)
    providers = await service.list_providers(
        workspace_id=user.workspace_id,
        user_id=user.id,
    )
    return success_response(
        [
            _dump(LlmProviderRead.model_validate(provider))
            for provider in providers
        ],
        request=request,
    )


@router.post("/providers")
async def create_provider(
    payload: LlmProviderCreate,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = LlmCatalogService(db)
    data = _with_user_context(payload.model_dump(), user)
    provider = await service.create_provider(data)
    return success_response(
        _dump(LlmProviderRead.model_validate(provider)),
        request=request,
        status_code=201,
    )


@router.patch("/providers/{provider_id}")
async def update_provider(
    provider_id: str,
    payload: LlmProviderUpdate,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = LlmCatalogService(db)
    provider = await service.update_provider(
        provider_id,
        _with_user_context(payload.model_dump(exclude_unset=True), user),
    )
    return success_response(_dump(LlmProviderRead.model_validate(provider)), request=request)


@router.post("/providers/{provider_id}/test")
async def test_provider(
    provider_id: str,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = LlmCatalogService(db)
    provider = await service.test_provider(
        provider_id,
        workspace_id=user.workspace_id,
        user_id=user.id,
        role=user.role,
    )
    status = provider.test_status or {}
    result = LlmProviderTestResult(
        provider_id=provider.id,
        success=bool(status.get("success")),
        model=status.get("model"),
        error=status.get("error"),
        latency_ms=status.get("latency_ms"),
    )
    return success_response(_dump(result), request=request)


@router.get("/models")
async def list_models(
    request: Request,
    provider_id: str | None = Query(default=None),
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = LlmCatalogService(db)
    models = await service.list_models(
        provider_id=provider_id,
        workspace_id=user.workspace_id,
        user_id=user.id,
    )
    return success_response(
        [_dump(LlmModelRead.model_validate(model)) for model in models],
        request=request,
    )


@router.post("/models")
async def create_model(
    payload: LlmModelCreate,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = LlmCatalogService(db)
    model = await service.create_model(_with_user_context(payload.model_dump(), user))
    return success_response(
        _dump(LlmModelRead.model_validate(model)),
        request=request,
        status_code=201,
    )


@router.patch("/models/{model_id}")
async def update_model(
    model_id: str,
    payload: LlmModelUpdate,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = LlmCatalogService(db)
    model = await service.update_model(
        model_id,
        _with_user_context(payload.model_dump(exclude_unset=True), user),
    )
    return success_response(_dump(LlmModelRead.model_validate(model)), request=request)


@router.get("/model-profiles")
async def list_model_profiles(
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = LlmCatalogService(db)
    profiles = await service.list_profiles(
        workspace_id=user.workspace_id,
        user_id=user.id,
    )
    return success_response(
        [
            _dump(LlmModelProfileRead.model_validate(profile))
            for profile in profiles
        ],
        request=request,
    )


@router.post("/model-profiles")
async def create_model_profile(
    payload: LlmModelProfileCreate,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = LlmCatalogService(db)
    data = _with_user_context(payload.model_dump(), user)
    profile = await service.create_profile(data)
    return success_response(
        _dump(LlmModelProfileRead.model_validate(profile)),
        request=request,
        status_code=201,
    )


@router.patch("/model-profiles/{profile_id}")
async def update_model_profile(
    profile_id: str,
    payload: LlmModelProfileUpdate,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = LlmCatalogService(db)
    profile = await service.update_profile(
        profile_id,
        _with_user_context(payload.model_dump(exclude_unset=True), user),
    )
    return success_response(
        _dump(LlmModelProfileRead.model_validate(profile)),
        request=request,
    )
