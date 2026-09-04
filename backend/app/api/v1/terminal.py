from __future__ import annotations

import asyncio
import contextlib
from dataclasses import asdict

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
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
from app.services.terminal_service import (
    TerminalNotInteractiveError,
    TerminalSubscriberQueue,
    terminal_manager,
)
from app.utils.exceptions import NotFoundError, PermissionDeniedError
from app.utils.responses import success_response


router = APIRouter(prefix="/terminal", tags=["terminal"])

TERMINAL_NOT_INTERACTIVE_MESSAGE = "Terminal target is not interactive yet."
TERMINAL_SESSION_CLOSED_MESSAGE = "Terminal session is no longer available."


async def _send_terminal_messages(
    websocket: WebSocket, queue: TerminalSubscriberQueue
) -> None:
    children: set[asyncio.Task] = set()

    async def close_for_queue_reason() -> None:
        reason = queue.close_reason
        code = {"slow": 1013, "shutdown": 1001, "idle": 1001}.get(reason, 1000)
        text = "Terminal subscriber too slow" if reason == "slow" else "Terminal closed"
        await websocket.close(code=code, reason=text)

    async def deliver_natural_exit() -> bool:
        if queue.close_reason != "exit":
            return False
        with contextlib.suppress(asyncio.QueueEmpty):
            while True:
                message = queue.get_nowait()
                if message.get("type") == "exit":
                    await websocket.send_json(message)
                    await websocket.close(code=1000, reason="Terminal exited")
                    return True
        return False

    def child(awaitable) -> asyncio.Task:
        task = asyncio.create_task(awaitable)
        children.add(task)
        task.add_done_callback(children.discard)
        return task

    try:
        while True:
            get_message = child(queue.get())
            wait_closed = child(queue.closed.wait())
            done, pending = await asyncio.wait(
                {get_message, wait_closed},
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
            if queue.closed.is_set():
                if queue.close_reason == "exit":
                    if get_message in done:
                        message = get_message.result()
                        if message.get("type") == "exit":
                            await websocket.send_json(message)
                            await websocket.close(code=1000, reason="Terminal exited")
                            return
                    if await deliver_natural_exit():
                        return
                await close_for_queue_reason()
                return
            message = get_message.result()
            send_message = child(websocket.send_json(message))
            closed_during_send = child(queue.closed.wait())
            await asyncio.wait(
                {send_message, closed_during_send},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if queue.closed.is_set() and not (
                queue.close_reason == "exit" and message.get("type") == "exit"
            ):
                if not send_message.done():
                    send_message.cancel()
                await asyncio.gather(send_message, return_exceptions=True)
                if await deliver_natural_exit():
                    return
                await close_for_queue_reason()
                return
            closed_during_send.cancel()
            await asyncio.gather(closed_during_send, return_exceptions=True)
            await send_message
            if message.get("type") == "exit":
                await websocket.close(code=1000, reason="Terminal exited")
                return
    except Exception:
        with contextlib.suppress(Exception):
            await websocket.close(code=1011, reason="Terminal send failed")
        raise
    finally:
        for task in children:
            if not task.done():
                task.cancel()
        if children:
            await asyncio.gather(*children, return_exceptions=True)


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
        connection_service = RemoteConnectionService(db)
        connection = await connection_service.get_connection(
            str(remote_connection_id),
            workspace_id=user.workspace_id,
        )
        if connection is None:
            raise NotFoundError("Remote connection not found")
        connection_config = await connection_service.resolve_connection_config(
            connection
        )
        session = await terminal_manager.create_or_get_remote(
            project_id=str(project.id),
            connection=connection_config,
            remote_root_path=str(remote_root_path),
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

    def safe_enqueue(message: dict) -> None:
        terminal_manager.enqueue_subscriber_message(queue, message)

    sender = asyncio.create_task(_send_terminal_messages(websocket, queue))

    try:
        while True:
            payload = await websocket.receive_json()
            event_type = payload.get("type")
            if event_type == "input":
                try:
                    await terminal_manager.send_input(
                        session_id, str(payload.get("data", ""))
                    )
                except KeyError:
                    safe_enqueue(
                        {
                            "type": "error",
                            "message": TERMINAL_SESSION_CLOSED_MESSAGE,
                        }
                    )
                except TerminalNotInteractiveError:
                    safe_enqueue(
                        {
                            "type": "error",
                            "message": TERMINAL_NOT_INTERACTIVE_MESSAGE,
                        }
                    )
            elif event_type == "resize":
                try:
                    await terminal_manager.resize(
                        session_id,
                        cols=int(payload.get("cols", 80)),
                        rows=int(payload.get("rows", 24)),
                    )
                except KeyError:
                    safe_enqueue(
                        {
                            "type": "error",
                            "message": TERMINAL_SESSION_CLOSED_MESSAGE,
                        }
                    )
                except TerminalNotInteractiveError:
                    safe_enqueue(
                        {
                            "type": "error",
                            "message": TERMINAL_NOT_INTERACTIVE_MESSAGE,
                        }
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
                    safe_enqueue(
                        {"type": "error", "message": f"Directory not found: {exc}"}
                    )
                except TerminalNotInteractiveError:
                    safe_enqueue(
                        {"type": "error", "message": TERMINAL_NOT_INTERACTIVE_MESSAGE}
                    )
                except KeyError:
                    safe_enqueue(
                        {"type": "error", "message": TERMINAL_SESSION_CLOSED_MESSAGE}
                    )
            elif event_type == "ping":
                safe_enqueue({"type": "pong"})
            else:
                safe_enqueue(
                    {
                        "type": "error",
                        "message": f"Unsupported message type: {event_type}",
                    }
                )
    except PermissionDeniedError as exc:
        sender.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await sender
        sender = None
        with contextlib.suppress(WebSocketDisconnect):
            await websocket.send_json({"type": "error", "message": exc.message})
            await websocket.close(code=1008, reason="Terminal path denied")
    except WebSocketDisconnect:
        pass
    finally:
        if sender:
            sender.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await sender
        await terminal_manager.detach(session_id, queue)
