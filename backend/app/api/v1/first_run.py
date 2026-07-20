from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.api.error_handler import handle_api_errors
from app.auth.session import AuthUser
from app.services.demo_bootstrap_service import DemoBootstrapService
from app.utils.responses import success_response


router = APIRouter(prefix="/first-run", tags=["first-run"])


@router.post("/bootstrap")
@handle_api_errors
async def bootstrap_first_run(
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await DemoBootstrapService(db).bootstrap(
        workspace_id=user.workspace_id,
        user_id=user.id,
    )
    return success_response(result, request=request)
