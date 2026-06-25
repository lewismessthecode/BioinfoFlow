from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.auth.session import AuthUser
from app.schemas.remote_connection import (
    RemoteConnectionCreate,
    RemoteConnectionRead,
    RemoteConnectionTestRead,
    RemoteConnectionUpdate,
)
from app.services.remote_connection_service import (
    RemoteConnectionService,
    UnavailableRemoteConnectionTester,
)
from app.utils.responses import error_response, success_response


router = APIRouter(prefix="/connections", tags=["connections"])


def get_remote_connection_tester():
    return UnavailableRemoteConnectionTester()


def _serialize(connection) -> dict:
    return RemoteConnectionRead.model_validate(
        connection,
        from_attributes=True,
    ).model_dump(mode="json")


def _not_found(request: Request):
    return error_response(
        code="NOT_FOUND",
        message="Remote connection not found",
        status_code=404,
        request=request,
    )


@router.get("")
async def list_connections(
    request: Request,
    limit: int = 20,
    cursor: str | None = None,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = RemoteConnectionService(db)
    connections, pagination = await service.list_connections(
        workspace_id=user.workspace_id,
        limit=limit,
        cursor=cursor,
    )
    return success_response(
        [_serialize(connection) for connection in connections],
        request=request,
        pagination=pagination,
    )


@router.post("")
async def create_connection(
    payload: RemoteConnectionCreate,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = RemoteConnectionService(db)
    connection = await service.create_connection(
        payload.model_dump(),
        workspace_id=user.workspace_id,
    )
    return success_response(_serialize(connection), request=request, status_code=201)


@router.get("/{connection_id}")
async def get_connection(
    connection_id: str,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = RemoteConnectionService(db)
    connection = await service.get_connection(
        connection_id,
        workspace_id=user.workspace_id,
    )
    if not connection:
        return _not_found(request)
    return success_response(_serialize(connection), request=request)


@router.patch("/{connection_id}")
async def update_connection(
    connection_id: str,
    payload: RemoteConnectionUpdate,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = RemoteConnectionService(db)
    connection = await service.get_connection(
        connection_id,
        workspace_id=user.workspace_id,
    )
    if not connection:
        return _not_found(request)
    updated = await service.update_connection(
        connection,
        payload.model_dump(exclude_unset=True),
    )
    return success_response(_serialize(updated), request=request)


@router.delete("/{connection_id}")
async def delete_connection(
    connection_id: str,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = RemoteConnectionService(db)
    connection = await service.get_connection(
        connection_id,
        workspace_id=user.workspace_id,
    )
    if not connection:
        return _not_found(request)
    await service.delete_connection(connection)
    return success_response(None, request=request, status_code=204)


@router.post("/{connection_id}/test")
async def test_connection(
    connection_id: str,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    tester=Depends(get_remote_connection_tester),
):
    service = RemoteConnectionService(db, tester=tester)
    connection = await service.get_connection(
        connection_id,
        workspace_id=user.workspace_id,
    )
    if not connection:
        return _not_found(request)
    updated, checked_at = await service.test_connection(connection)
    data = RemoteConnectionTestRead(
        status=updated.last_status,
        error=updated.last_error,
        checked_at=checked_at,
        connection=RemoteConnectionRead.model_validate(
            updated,
            from_attributes=True,
        ),
    ).model_dump(mode="json")
    return success_response(data, request=request)
