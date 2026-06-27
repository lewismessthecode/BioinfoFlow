from __future__ import annotations

import asyncio
import contextlib
import shlex
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db, require_admin
from app.auth.dependencies import resolve_websocket_user
from app.auth.session import AuthUser
from app.config import settings
from app.schemas.remote_connection import (
    RemoteConnectionCreate,
    RemoteConnectionRead,
    RemoteConnectionTestRead,
    RemoteConnectionUpdate,
)
from app.services.remote_connection_service import (
    RemoteConnectionService,
    SshRemoteConnectionTester,
    remote_connection_config_from_model,
)
from app.services.remote_execution import SshRemoteExecutor
from app.utils.responses import error_response, success_response


router = APIRouter(prefix="/connections", tags=["connections"])

_EXEC_WS_MAX_COMMAND_LENGTH = 4000
_EXEC_WS_MAX_TIMEOUT_SECONDS = 300
_EXEC_WS_MAX_OUTPUT_BYTES = 64 * 1024


def get_remote_connection_tester():
    return SshRemoteConnectionTester()


def get_remote_executor():
    return SshRemoteExecutor()


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
    user: AuthUser = Depends(require_admin),
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
    connection_id: UUID,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = RemoteConnectionService(db)
    connection = await service.get_connection(
        str(connection_id),
        workspace_id=user.workspace_id,
    )
    if not connection:
        return _not_found(request)
    return success_response(_serialize(connection), request=request)


@router.patch("/{connection_id}")
async def update_connection(
    connection_id: UUID,
    payload: RemoteConnectionUpdate,
    request: Request,
    user: AuthUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    service = RemoteConnectionService(db)
    connection = await service.get_connection(
        str(connection_id),
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
    connection_id: UUID,
    request: Request,
    user: AuthUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    service = RemoteConnectionService(db)
    connection = await service.get_connection(
        str(connection_id),
        workspace_id=user.workspace_id,
    )
    if not connection:
        return _not_found(request)
    await service.delete_connection(connection)
    return success_response(None, request=request, status_code=204)


@router.post("/{connection_id}/test")
async def test_connection(
    connection_id: UUID,
    request: Request,
    user: AuthUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    tester=Depends(get_remote_connection_tester),
):
    service = RemoteConnectionService(db, tester=tester)
    connection = await service.get_connection(
        str(connection_id),
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


@router.get("/{connection_id}/directories")
async def browse_remote_directory(
    connection_id: UUID,
    request: Request,
    path: str = Query(default="."),
    limit: int = Query(default=100, ge=1, le=200),
    user: AuthUser = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
    executor: SshRemoteExecutor = Depends(get_remote_executor),
):
    service = RemoteConnectionService(db)
    connection = await service.get_connection(
        str(connection_id),
        workspace_id=user.workspace_id,
    )
    if not connection:
        return _not_found(request)
    result = await executor.run(
        remote_connection_config_from_model(connection),
        _remote_directory_command(path, limit),
        timeout_seconds=10,
        output_limit=50000,
    )
    if result.exit_code != 0:
        return error_response(
            code="REMOTE_DIRECTORY_UNAVAILABLE",
            message=(result.stderr or result.stdout or "Remote directory is unavailable").strip(),
            status_code=400,
            request=request,
        )
    entries = _parse_remote_directory_entries(path, result.stdout, limit + 1)
    return success_response(
        {
            "path": path,
            "entries": entries[:limit],
            "truncated": len(entries) > limit,
        },
        request=request,
    )


def _remote_directory_command(path: str, limit: int) -> str:
    quoted_path = shlex.quote(str(path or "."))
    line_limit = limit + 1
    return (
        f"if [ ! -d {quoted_path} ]; then "
        "printf '%s\\n' 'remote path is not a directory' >&2; exit 22; "
        "fi; "
        f"find {quoted_path} -maxdepth 1 -mindepth 1 "
        "-printf '%y\\t%f\\t%s\\n' | sort | "
        f"head -n {line_limit}"
    )


def _parse_remote_directory_entries(
    parent_path: str,
    stdout: str,
    limit: int,
) -> list[dict]:
    entries: list[dict] = []
    for line in stdout.splitlines():
        parts = line.split("\t", 2)
        if len(parts) != 3:
            continue
        kind_code, name, size_text = parts
        try:
            size = int(size_text)
        except ValueError:
            size = 0
        entries.append(
            {
                "name": name,
                "path": _remote_child_path(parent_path, name),
                "type": "dir" if kind_code == "d" else "file",
                "kind": _remote_kind(kind_code),
                "size": None if kind_code == "d" else size,
            }
        )
        if len(entries) >= limit:
            break
    return entries


def _remote_child_path(parent_path: str, name: str) -> str:
    parent = str(parent_path or ".").rstrip("/")
    if parent in {"", "."}:
        return name
    if parent == "/":
        return f"/{name}"
    return f"{parent}/{name}"


def _remote_kind(code: str) -> str:
    return {"d": "directory", "f": "file", "l": "symlink"}.get(code, "other")


@router.websocket("/{connection_id}/exec/ws")
async def exec_connection_socket(
    connection_id: UUID,
    websocket: WebSocket,
    db: AsyncSession = Depends(get_db),
):
    await websocket.accept()
    try:
        user = await resolve_websocket_user(websocket, db)
    except HTTPException as exc:
        code = 4401 if exc.status_code == 401 else 4403
        await websocket.close(code=code, reason="Unauthorized")
        return
    if settings.auth_is_team and user.role not in {"owner", "admin"}:
        await websocket.close(code=4403, reason="Forbidden")
        return

    service = RemoteConnectionService(db)
    connection = await service.get_connection(
        str(connection_id),
        workspace_id=user.workspace_id,
    )
    if not connection:
        await websocket.close(code=4404, reason="Remote connection not found")
        return

    executor = SshRemoteExecutor()

    try:
        first = await asyncio.wait_for(websocket.receive_json(), timeout=5)
    except asyncio.TimeoutError:
        await websocket.close(code=4400, reason="Command required")
        return
    except WebSocketDisconnect:
        return

    command = str(first.get("command") or "").strip()
    if not command:
        await websocket.send_json(
            {"type": "error", "message": "command must be a non-empty string"}
        )
        await websocket.close(code=4400)
        return
    if len(command) > _EXEC_WS_MAX_COMMAND_LENGTH:
        await websocket.send_json(
            {
                "type": "error",
                "message": f"command must be <= {_EXEC_WS_MAX_COMMAND_LENGTH} characters",
            }
        )
        await websocket.close(code=4400)
        return
    try:
        timeout_seconds = int(first.get("timeout_seconds") or 60)
    except (TypeError, ValueError):
        await websocket.send_json(
            {"type": "error", "message": "timeout_seconds must be an integer"}
        )
        await websocket.close(code=4400)
        return
    if timeout_seconds < 1 or timeout_seconds > _EXEC_WS_MAX_TIMEOUT_SECONDS:
        await websocket.send_json(
            {
                "type": "error",
                "message": (
                    "timeout_seconds must be between 1 and "
                    f"{_EXEC_WS_MAX_TIMEOUT_SECONDS}"
                ),
            }
        )
        await websocket.close(code=4400)
        return

    try:
        async for frame in executor.stream(
            remote_connection_config_from_model(connection),
            command,
            timeout_seconds=timeout_seconds,
            output_limit=_EXEC_WS_MAX_OUTPUT_BYTES,
        ):
            payload = {
                "type": frame.type,
                "data": frame.data,
                "exit_code": frame.exit_code,
                "timed_out": frame.timed_out,
            }
            await websocket.send_json(
                {key: value for key, value in payload.items() if value is not None}
            )
    except WebSocketDisconnect:
        return
    except Exception as exc:  # noqa: BLE001 - websocket must return structured error
        with contextlib.suppress(RuntimeError):
            await websocket.send_json({"type": "error", "message": str(exc)})
