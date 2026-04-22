from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.api.error_handler import handle_api_errors
from app.auth.session import AuthUser
from app.schemas.notification import NotificationConfigCreate, NotificationConfigRead
from app.services.notification_service import NotificationService
from app.utils.responses import error_response, success_response


router = APIRouter(prefix="/notifications", tags=["notifications"])


def _serialize(config) -> dict:
    return NotificationConfigRead.model_validate(
        config, from_attributes=True
    ).model_dump(mode="json", by_alias=True)


@router.post("")
@handle_api_errors
async def create_notification(
    payload: NotificationConfigCreate,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = NotificationService(db)
    config = await service.create_config(
        project_id=str(payload.project_id),
        channel=payload.channel.value,
        trigger=payload.trigger.value,
        config=payload.config,
        enabled=payload.enabled,
    )
    return success_response(_serialize(config), request=request, status_code=201)


@router.get("")
async def list_notifications(
    request: Request,
    project_id: str | None = None,
    trigger: str | None = None,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = NotificationService(db)
    configs = await service.list_configs(project_id=project_id, trigger=trigger)
    return success_response([_serialize(config) for config in configs], request=request)


@router.delete("/{notification_id}")
async def delete_notification(
    notification_id: str,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = NotificationService(db)
    deleted = await service.delete_config(notification_id)
    if not deleted:
        return error_response(
            code="NOT_FOUND",
            message="Notification config not found",
            status_code=404,
            request=request,
        )
    return success_response({"deleted": True}, request=request)
