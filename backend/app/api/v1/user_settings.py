from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.auth.session import AuthUser
from app.schemas.user_settings import UserSettingsUpdate
from app.services.agent.runtime.providers import PROVIDER_REGISTRY
from app.services.user_settings_service import UserSettingsService
from app.utils.responses import error_response, success_response

router = APIRouter(prefix="/user-settings", tags=["user-settings"])


@router.get("")
async def get_settings(
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current user's LLM settings (API keys are masked)."""
    service = UserSettingsService(db)
    settings = await service.get_settings(user.id)
    return success_response(settings.model_dump(), request=request)


@router.patch("")
async def update_settings(
    payload: UserSettingsUpdate,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update user's LLM settings. Partial update — only provided fields change."""
    service = UserSettingsService(db)
    settings = await service.update_settings(user.id, payload)
    return success_response(settings.model_dump(), request=request)


@router.post("/test/{provider}")
async def test_provider(
    provider: str,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Test a provider's API key with a minimal API call."""
    if provider not in PROVIDER_REGISTRY:
        return error_response(
            code="INVALID_PROVIDER",
            message=f"Unknown provider: {provider}. Must be one of: {', '.join(sorted(PROVIDER_REGISTRY.keys()))}",
            status_code=400,
            request=request,
        )

    service = UserSettingsService(db)
    result = await service.test_provider(user.id, provider)
    return success_response(result.model_dump(), request=request)


@router.get("/models")
async def list_available_models(
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List available models based on the user's configured providers."""
    service = UserSettingsService(db)
    models = await service.get_available_models(user.id)
    return success_response(
        [m.model_dump() for m in models],
        request=request,
    )
