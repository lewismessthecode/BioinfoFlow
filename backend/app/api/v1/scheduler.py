from __future__ import annotations

import asyncio
import contextlib
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.auth.dependencies import resolve_websocket_user
from app.models.run import Run
from app.models.workflow import Workflow
from app.scheduler.resources import SystemResources
from app.scheduler.scheduler import DEFAULT_STATE_COUNTS
from app.scheduler.stream import resource_stream_generator
from app.services.btop_service import (
    BtopUnavailableError,
    resize as btop_resize,
    send_input as btop_send_input,
    spawn_btop_session,
    terminate_session as btop_terminate,
)
from app.services.run_dispatch import get_run_scheduler
from app.utils.responses import success_response


router = APIRouter(prefix="/scheduler", tags=["scheduler"])


def _serialize_timestamp(value: datetime | str | None) -> str | None:
    if value is None or isinstance(value, str):
        return value
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _resource_payload(snapshot: SystemResources | None) -> dict[str, object]:
    if snapshot is None:
        return {
            "enabled": False,
            "sampled_at": None,
            "cpu": {"total": None, "available": None},
            "memory": {"total_gb": None, "available_gb": None},
            "disk": {"total_gb": None, "available_gb": None},
            "gpu": {"count": 0, "memory_gb": 0.0},
        }

    return {
        "enabled": True,
        "sampled_at": _serialize_timestamp(snapshot.sampled_at),
        "cpu": {"total": snapshot.cpu_count, "available": snapshot.cpu_available},
        "memory": {
            "total_gb": snapshot.memory_total_gb,
            "available_gb": snapshot.memory_available_gb,
        },
        "disk": {
            "total_gb": snapshot.disk_total_gb,
            "available_gb": snapshot.disk_available_gb,
        },
        "gpu": {"count": snapshot.gpu_count, "memory_gb": snapshot.gpu_memory_gb},
    }


async def _enrich_active_runs(
    session: AsyncSession,
    active_runs: list[dict[str, object]],
) -> list[dict[str, object]]:
    """Attach workflow_name to each active run via a single batched query.

    Keeps the existing ``{run_id, weight}`` keys intact — additive only so
    older clients (CLI, legacy frontend) continue to work.
    """
    if not active_runs:
        return active_runs

    run_ids = [str(entry["run_id"]) for entry in active_runs]
    stmt = (
        select(Run.run_id, Workflow.name)
        .outerjoin(Workflow, Workflow.id == Run.workflow_id)
        .where(Run.run_id.in_(run_ids))
    )
    result = await session.execute(stmt)
    lookup = {run_id: workflow_name for run_id, workflow_name in result.all()}

    return [
        {
            **entry,
            "workflow_name": lookup.get(str(entry["run_id"])),
        }
        for entry in active_runs
    ]


@router.get("/status")
async def get_scheduler_status(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    scheduler = get_run_scheduler()
    if scheduler is None:
        data = {
            "mode": "persistent",
            "effective_mode": "persistent",
            "scheduler_available": False,
            "resource_monitoring_enabled": False,
            "workers": 0,
            "queue_depth": 0,
            "states": DEFAULT_STATE_COUNTS,
            "total_slots": 0,
            "used_slots": 0,
            "available_slots": 0,
            "active_runs": [],
        }
        return success_response(data, request=request)

    data = await scheduler.get_status()
    data["active_runs"] = await _enrich_active_runs(db, data.get("active_runs", []))
    return success_response(
        {
            "mode": "persistent",
            "effective_mode": "persistent",
            "scheduler_available": True,
            **data,
        },
        request=request,
    )


@router.get("/resources")
async def get_scheduler_resources(request: Request):
    scheduler = get_run_scheduler()
    snapshot = scheduler.get_resource_snapshot() if scheduler is not None else None
    return success_response(
        {
            "mode": "persistent",
            **_resource_payload(snapshot),
        },
        request=request,
    )


@router.get("/resources/stream")
async def stream_scheduler_resources(request: Request):
    """Server-sent events feed for the live resource monitor.

    Emits a combined frame (resources + enriched active_runs + queue_depth)
    every ~2 s. Heartbeat ``: ping\\n\\n`` on a 15 s idle timeout. Cleans up
    on client disconnect.

    Unlike ``/events/stream``, this feed is host-scoped (not project-scoped):
    resource snapshots describe the backend host, not a tenant's project.
    """
    return StreamingResponse(
        resource_stream_generator(
            request=request,
            scheduler=get_run_scheduler(),
            resource_payload_builder=_resource_payload,
            enrich_active_runs=_enrich_active_runs,
            mode="persistent",
        ),
        media_type="text/event-stream",
    )


@router.websocket("/btop/ws")
async def btop_socket(
    websocket: WebSocket,
    db: AsyncSession = Depends(get_db),
):
    """WebSocket bridge for the Advanced drawer's btop process panel.

    Per-connection pty spawn of ``btop -p 1``. Uses the same JSON frame
    contract as :mod:`app.api.v1.terminal` so the frontend can reuse the
    xterm glue:

    - server → client: ``{"type": "output", "data": "..."}``,
      ``{"type": "exit", "exit_code": n}``,
      ``{"type": "error", "code": "btop_unavailable" | "spawn_failed", "message": "..."}``
    - client → server: ``{"type": "input", "data": "..."}``,
      ``{"type": "resize", "cols": n, "rows": n}``, ``{"type": "ping"}``
    """
    await websocket.accept()
    try:
        await resolve_websocket_user(websocket, db)
    except HTTPException as exc:
        code = 4401 if exc.status_code == 401 else 4403
        await websocket.close(code=code, reason="Unauthorized")
        return

    initial_cols = 120
    initial_rows = 32
    try:
        first = await asyncio.wait_for(websocket.receive_json(), timeout=0.5)
        if isinstance(first, dict) and first.get("type") == "resize":
            initial_cols = int(first.get("cols", initial_cols))
            initial_rows = int(first.get("rows", initial_rows))
    except (asyncio.TimeoutError, WebSocketDisconnect, ValueError):
        pass

    try:
        session = await spawn_btop_session(cols=initial_cols, rows=initial_rows)
    except BtopUnavailableError as exc:
        await websocket.send_json(
            {
                "type": "error",
                "code": "btop_unavailable",
                "message": f"btop binary not found: {exc}",
            }
        )
        await websocket.close(code=4404)
        return
    except OSError as exc:
        await websocket.send_json(
            {
                "type": "error",
                "code": "spawn_failed",
                "message": str(exc),
            }
        )
        await websocket.close(code=4500)
        return

    async def pump_output() -> None:
        while True:
            message = await session.queue.get()
            await websocket.send_json(message)
            if message.get("type") == "exit":
                break

    sender = asyncio.create_task(pump_output())

    try:
        while True:
            payload = await websocket.receive_json()
            event_type = payload.get("type")
            if event_type == "input":
                await btop_send_input(session, str(payload.get("data", "")))
            elif event_type == "resize":
                await btop_resize(
                    session,
                    cols=int(payload.get("cols", initial_cols)),
                    rows=int(payload.get("rows", initial_rows)),
                )
            elif event_type == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    finally:
        sender.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await sender
        await btop_terminate(session)
