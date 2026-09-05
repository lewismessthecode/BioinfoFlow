from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_current_user, get_db
from app.api.v1.agent_schemas import AgentSettingsRead, AgentSettingsUpdate
from app.auth.session import AuthUser
from app.repositories.agent_user_settings_repo import AgentUserSettingsRepository
from app.schemas.common import SuccessEnvelope
from app.utils.responses import success_response


router = APIRouter()


@router.get("/settings", response_model=SuccessEnvelope[AgentSettingsRead])
async def get_settings(
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_settings = await AgentUserSettingsRepository(db).get(
        user.workspace_id,
        user.id,
    )
    return success_response(
        AgentSettingsRead(
            custom_instructions=(
                user_settings.custom_instructions if user_settings is not None else ""
            )
        ).model_dump(mode="json"),
        request=request,
    )


@router.put("/settings", response_model=SuccessEnvelope[AgentSettingsRead])
async def update_settings(
    payload: AgentSettingsUpdate,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_settings = await AgentUserSettingsRepository(db).upsert(
        workspace_id=user.workspace_id,
        user_id=user.id,
        custom_instructions=payload.custom_instructions.strip(),
    )
    return success_response(
        AgentSettingsRead(
            custom_instructions=user_settings.custom_instructions
        ).model_dump(mode="json"),
        request=request,
    )


__all__ = [
    "get_settings",
    "update_settings",
    "router",
]
