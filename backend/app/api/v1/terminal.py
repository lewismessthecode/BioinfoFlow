from __future__ import annotations

import asyncio
import contextlib
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.auth.dependencies import resolve_websocket_user
from app.auth.session import AuthUser
from app.path_layout import project_home
from app.schemas.terminal import (
    TerminalSessionCloseResponse,
    TerminalSessionCreate,
    TerminalSessionRead,
)
from app.services.remote_connection_service import RemoteConnectionService
from app.services.project_service import ProjectService
from app.services.terminal_service import terminal_manager
from app.utils.exceptions import NotFoundError, PermissionDeniedError
from app.utils.responses import success_response


router = APIRouter(prefix="/terminal", tags=["terminal"])


@router.post("/sessions")
async def create_terminal_session(
    payload: TerminalSessionCreate,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = ProjectService(db)
    project = await service.get_project(
        payload.project_id,
        workspace_id=user.workspace_id,
    )
    if project is None:
        raise NotFoundError("Project not found")

    existing = await terminal_manager.get_by_project(str(project.id))
    if existing is not None:
        data = TerminalSessionRead.model_validate(asdict(existing)).model_dump(
            mode="json"
        )
        return success_response(data, request=request, status_code=200)

    if getattr(project, "storage_mode", None) == "remote":
        remote_connection_id = getattr(project, "remote_connection_id", None)
        remote_root_path = getattr(project, "remote_root_path", None)
        if not remote_connection_id or not remote_root_path:
            raise NotFoundError("Remote project target not found")
        connection = await RemoteConnectionService(db).get_connection(
            str(remote_connection_id),
            workspace_id=user.workspace_id,
        )
        if connection is None:
            raise NotFoundError("Remote connection not found")
        session = await terminal_manager.create_or_get_unsupported_remote(
            project_id=str(project.id),
            remote_root_path=str(remote_root_path),
            remote_connection_id=str(remote_connection_id),
            target_label=f"remote · {connection.name}",
        )
    else:
        session = await terminal_manager.create_or_get(
            project_id=str(project.id),
            root_path=project_home(project),
        )
    data = TerminalSessionRead.model_validate(asdict(session)).model_dump(mode="json")
    return success_response(data, request=request, status_code=201)


@router.delete("/sessions/{session_id}")
async def close_terminal_session(
    session_id: str,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    snapshot = await terminal_manager.get_by_id(session_id)
    if snapshot is None:
        raise NotFoundError("Terminal session not found")

    service = ProjectService(db)
    project = await service.get_project(
        snapshot.project_id,
        workspace_id=user.workspace_id,
    )
    if project is None:
        raise NotFoundError("Terminal session not found")

    closed = await terminal_manager.close_session(session_id)
    if not closed:
        raise NotFoundError("Terminal session not found")
    data = TerminalSessionCloseResponse(id=session_id, closed=True).model_dump(
        mode="json"
    )
    return success_response(data, request=request, status_code=200)


@router.websocket("/sessions/{session_id}/ws")
async def terminal_socket(
    session_id: str,
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

    snapshot = await terminal_manager.get_by_id(session_id)
    if snapshot is None:
        await websocket.close(code=4404, reason="Terminal session not found")
        return

    service = ProjectService(db)
    project = await service.get_project(
        snapshot.project_id,
        workspace_id=user.workspace_id,
    )
    if project is None:
        await websocket.close(code=4404, reason="Terminal session not found")
        return

    try:
        queue = await terminal_manager.attach(session_id)
    except KeyError:
        await websocket.close(code=4404, reason="Terminal session not found")
        return

    async def send_messages() -> None:
        while True:
            message = await queue.get()
            await websocket.send_json(message)

    sender = asyncio.create_task(send_messages())

    try:
        while True:
            payload = await websocket.receive_json()
            event_type = payload.get("type")
            if event_type == "input":
                await terminal_manager.send_input(
                    session_id, str(payload.get("data", ""))
                )
            elif event_type == "resize":
                await terminal_manager.resize(
                    session_id,
                    cols=int(payload.get("cols", 80)),
                    rows=int(payload.get("rows", 24)),
                )
            elif event_type == "chdir":
                try:
                    await terminal_manager.change_directory(
                        session_id, str(payload.get("path", "."))
                    )
                except PermissionError as exc:
                    raise PermissionDeniedError(
                        "Path escapes project workspace"
                    ) from exc
                except FileNotFoundError as exc:
                    queue.put_nowait(
                        {"type": "error", "message": f"Directory not found: {exc}"}
                    )
            elif event_type == "ping":
                queue.put_nowait({"type": "pong"})
            else:
                queue.put_nowait(
                    {
                        "type": "error",
                        "message": f"Unsupported message type: {event_type}",
                    }
                )
    except PermissionDeniedError as exc:
        queue.put_nowait({"type": "error", "message": exc.message})
    except WebSocketDisconnect:
        pass
    finally:
        if sender:
            sender.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await sender
        await terminal_manager.detach(session_id, queue)
