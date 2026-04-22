from __future__ import annotations

from fastapi import HTTPException, Request, WebSocket
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.session import AuthUser, validate_session
from app.config import settings
from app.services.workspace_service import WorkspaceService
from app.workspace import DEFAULT_WORKSPACE_ID

_ANONYMOUS_USER = AuthUser(
    id="dev",
    name="Local User",
    email="local@bioinfoflow",
    role="owner",
    workspace_id=DEFAULT_WORKSPACE_ID,
)


async def _resolve_user_from_session_token(
    token: str | None, db: AsyncSession, *, required: bool
) -> AuthUser | None:
    if not settings.auth_enabled_effective:
        return _ANONYMOUS_USER

    if not token:
        if required:
            raise HTTPException(status_code=401, detail="Unauthorized")
        return None

    user = validate_session(token)
    if user is None:
        if required:
            raise HTTPException(status_code=401, detail="Unauthorized")
        return None

    workspace_service = WorkspaceService(db)
    await workspace_service.ensure_membership(user)
    return user


async def resolve_current_user(request: Request, db: AsyncSession) -> AuthUser:
    """Resolve the current request user and ensure workspace membership."""
    return await _resolve_user_from_session_token(
        request.cookies.get("better-auth.session_token"),
        db,
        required=True,
    )


async def resolve_optional_user(
    request: Request, db: AsyncSession
) -> AuthUser | None:
    """Resolve an authenticated user when present without forcing login."""
    return await _resolve_user_from_session_token(
        request.cookies.get("better-auth.session_token"),
        db,
        required=False,
    )


async def resolve_websocket_user(websocket: WebSocket, db: AsyncSession) -> AuthUser:
    return await _resolve_user_from_session_token(
        websocket.cookies.get("better-auth.session_token"),
        db,
        required=True,
    )


async def require_admin(request: Request, db: AsyncSession) -> AuthUser:
    user = await resolve_current_user(request, db)
    if user.role not in {"owner", "admin"}:
        raise HTTPException(status_code=403, detail="Forbidden")
    return user


async def require_owner(request: Request, db: AsyncSession) -> AuthUser:
    user = await resolve_current_user(request, db)
    if user.role != "owner":
        raise HTTPException(status_code=403, detail="Forbidden")
    return user
