from __future__ import annotations

from fastapi import HTTPException, Request, WebSocket
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.agent_tokens import AgentTokenService
from app.auth.session import AuthUser, validate_session, validate_user
from app.config import settings
from app.services.workspace_service import WorkspaceService
from app.utils.authorization import can_manage_workspace_members
from app.workspace import DEFAULT_WORKSPACE_ID

_ANONYMOUS_USER = AuthUser(
    id="dev",
    name="Local User",
    email="local@bioinfoflow",
    role="owner",
    workspace_id=DEFAULT_WORKSPACE_ID,
)


async def declare_agent_token_access(request: Request) -> None:
    """Declare that an API endpoint has an explicit Agent scope contract.

    Agent bearer credentials are rejected by default. Routers exposed to
    ``bif`` must opt in and then call :func:`require_agent_scope` with the
    concrete project/session/run they are about to access.
    """
    request.state.agent_token_access_declared = True


def require_agent_scope(
    request: Request,
    *,
    project_id: str | None = None,
    connection_id: str | None = None,
    session_id: str | None = None,
    run_id: str | None = None,
    allow_projectless: bool = False,
):
    """Enforce the durable claims of an authenticated Agent bearer token."""
    context = getattr(getattr(request, "state", None), "agent_token", None)
    if context is None:
        return None
    if project_id is not None:
        if context.project_id is None or str(project_id) != context.project_id:
            raise HTTPException(
                status_code=403, detail="Agent token project scope mismatch"
            )
    elif not allow_projectless:
        raise HTTPException(
            status_code=403,
            detail="Endpoint did not constrain the Agent token project scope",
        )
    if session_id is not None and str(session_id) != context.session_id:
        raise HTTPException(
            status_code=403, detail="Agent token session scope mismatch"
        )
    if run_id is not None and str(run_id) != context.run_id:
        raise HTTPException(status_code=403, detail="Agent token run scope mismatch")
    if connection_id is not None and str(connection_id) != context.connection_id:
        raise HTTPException(
            status_code=403,
            detail="Agent token connection scope mismatch",
        )
    return context


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
    if request.headers.get("authorization"):
        user = await _resolve_user_from_agent_token(request, db, required=True)
        if user is not None:
            return user
    if not settings.auth_enabled_effective:
        return _ANONYMOUS_USER
    return await _resolve_user_from_session_token(
        request.cookies.get("better-auth.session_token"),
        db,
        required=True,
    )


async def _resolve_user_from_agent_token(
    request: Request, db: AsyncSession, *, required: bool
) -> AuthUser | None:
    authorization = request.headers.get("authorization")
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        if required:
            raise HTTPException(status_code=401, detail="Unauthorized")
        return None
    context = await AgentTokenService(db).authenticate(token)
    if context is None:
        if required:
            raise HTTPException(status_code=401, detail="Unauthorized")
        return None
    if not getattr(request.state, "agent_token_access_declared", False):
        raise HTTPException(
            status_code=403,
            detail="Agent token is not allowed for this endpoint",
        )
    if settings.auth_enabled_effective:
        user = validate_user(context.user_id)
        if user is None or user.workspace_id != context.workspace_id:
            if required:
                raise HTTPException(status_code=401, detail="Unauthorized")
            return None
        await WorkspaceService(db).ensure_membership(user)
    else:
        user = _ANONYMOUS_USER.model_copy(
            update={
                "id": context.user_id,
                "workspace_id": context.workspace_id,
            }
        )
    request.state.agent_token = context
    return user


async def resolve_optional_user(request: Request, db: AsyncSession) -> AuthUser | None:
    """Resolve an authenticated user when present without forcing login."""
    if request.headers.get("authorization"):
        user = await _resolve_user_from_agent_token(request, db, required=True)
        if user is not None:
            return user
    if not settings.auth_enabled_effective:
        return _ANONYMOUS_USER
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
    if not settings.auth_is_team:
        return user
    if not can_manage_workspace_members(user.role):
        raise HTTPException(status_code=403, detail="Forbidden")
    return user


async def require_owner(request: Request, db: AsyncSession) -> AuthUser:
    user = await resolve_current_user(request, db)
    if not settings.auth_is_team:
        return user
    if user.role != "owner":
        raise HTTPException(status_code=403, detail="Forbidden")
    return user
