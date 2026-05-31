from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.auth.session import AuthUser
from app.services.stats_service import StatsService
from app.utils.responses import success_response


router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("")
async def get_stats(
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Dashboard statistics aggregating runs, workflows, images, and projects.
    Returns counts and recent activity for the dashboard overview.
    """
    service = StatsService(db)
    data = await service.get_dashboard_stats(
        user_id=user.id,
        workspace_id=user.workspace_id,
    )
    return success_response(data, request=request)
