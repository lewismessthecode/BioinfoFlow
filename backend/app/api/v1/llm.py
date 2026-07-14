from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.api.error_handler import handle_api_errors
from app.auth.session import AuthUser
from app.schemas.llm import (
    LlmModelCreate,
    LlmModelProfileCreate,
    LlmModelProfileRead,
    LlmModelProfileUpdate,
    LlmModelRead,
    LlmModelUpdate,
    LlmConfigurationRead,
    LlmConfiguredProviderRead,
    LlmProviderSetupRequest,
    LlmProviderSetupResult,
    LlmProviderCredentialRead,
    LlmProviderCredentialUpdate,
    LlmProviderCreate,
    LlmProviderRead,
    LlmProviderTemplateRead,
    LlmProviderTestRequest,
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
@handle_api_errors
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


@router.get("/provider-templates")
@handle_api_errors
async def list_provider_templates(
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    del user
    service = LlmCatalogService(db)
    templates = [
        LlmProviderTemplateRead.model_validate(template.as_dict())
        for template in service.list_provider_templates()
    ]
    return success_response(
        [
            template.model_dump(mode="json", exclude_none=True)
            for template in templates
        ],
        request=request,
    )


@router.get("/configuration")
@handle_api_errors
async def get_configuration(
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = LlmCatalogService(db)
    configuration = await service.configuration(
        workspace_id=user.workspace_id,
        user_id=user.id,
    )
    providers = [
        LlmConfiguredProviderRead.model_validate(
            {
                **LlmProviderRead.model_validate(item["provider"]).model_dump(mode="json"),
                "credential": item["credential"],
            }
        )
        for item in configuration["providers"]
    ]
    payload = LlmConfigurationRead(
        summary=configuration["summary"],
        providers=providers,
        models=[
            LlmModelRead.model_validate(model)
            for model in configuration["models"]
        ],
        profiles=[
            LlmModelProfileRead.model_validate(profile)
            for profile in configuration["profiles"]
        ],
    )
    return success_response(_dump(payload), request=request)


@router.post("/provider-setups")
@handle_api_errors
async def setup_provider(
    payload: LlmProviderSetupRequest,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = LlmCatalogService(db)
    data = _with_user_context(payload.model_dump(exclude_unset=True), user)
    setup = await service.setup_provider(data)
    provider = LlmConfiguredProviderRead.model_validate(
        {
            **LlmProviderRead.model_validate(setup["provider"]).model_dump(mode="json"),
            "credential": setup["credential"],
        }
    )
    result = LlmProviderSetupResult(
        provider=provider,
        models=[
            LlmModelRead.model_validate(model)
            for model in setup["models"]
        ],
        discovered=setup["discovered"],
    )
    return success_response(_dump(result), request=request)


@router.post("/providers")
@handle_api_errors
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


@router.put("/providers/{provider_id}/credential")
@handle_api_errors
async def upsert_provider_credential(
    provider_id: str,
    payload: LlmProviderCredentialUpdate,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = LlmCatalogService(db)
    provider, credential = await service.upsert_provider_credential(
        provider_id,
        payload.model_dump(exclude_unset=True),
        workspace_id=user.workspace_id,
        user_id=user.id,
        role=user.role,
    )
    read = LlmProviderCredentialRead.model_validate(
        service.credential_read_dict(provider, credential)
    )
    return success_response(_dump(read), request=request)


@router.patch("/providers/{provider_id}")
@handle_api_errors
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
@handle_api_errors
async def test_provider(
    provider_id: str,
    request: Request,
    payload: LlmProviderTestRequest | None = None,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = LlmCatalogService(db)
    status = await service.test_provider(
        provider_id,
        model_id=str(payload.model_id) if payload and payload.model_id else None,
        workspace_id=user.workspace_id,
        user_id=user.id,
        role=user.role,
    )
    result = LlmProviderTestResult(
        provider_id=provider_id,
        success=bool(status.get("success")),
        model=status.get("model") or status.get("model_id"),
        wire_protocol=status.get("wire_protocol") or "chat_completions",
        error_code=status.get("error_code"),
        error=status.get("error") or status.get("error_message"),
        latency_ms=status.get("latency_ms"),
        retryable=bool(status.get("retryable")),
        http_status=status.get("http_status"),
        provider_code=status.get("provider_code"),
    )
    return success_response(_dump(result), request=request)


@router.post("/providers/{provider_id}/discover-models")
@handle_api_errors
async def discover_provider_models(
    provider_id: str,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = LlmCatalogService(db)
    models = await service.discover_models(
        provider_id,
        workspace_id=user.workspace_id,
        user_id=user.id,
        role=user.role,
    )
    return success_response(
        [_dump(LlmModelRead.model_validate(model)) for model in models],
        request=request,
    )


@router.get("/models")
@handle_api_errors
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
@handle_api_errors
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
@handle_api_errors
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
@handle_api_errors
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
@handle_api_errors
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
@handle_api_errors
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
