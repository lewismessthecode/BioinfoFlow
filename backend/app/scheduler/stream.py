from __future__ import annotations

import asyncio
import json
from typing import AsyncGenerator, Awaitable, Callable
from uuid import uuid4

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

import app.database as app_database
from app.scheduler.scheduler import DEFAULT_STATE_COUNTS, RunScheduler
from app.utils.logging import get_logger


logger = get_logger(__name__)


TICK_SECONDS = 2.0
HEARTBEAT_SECONDS = 15.0


ResourcePayloadBuilder = Callable[[object], dict[str, object]]
EnrichActiveRuns = Callable[
    [AsyncSession, list[dict[str, object]]],
    Awaitable[list[dict[str, object]]],
]


async def _build_frame(
    *,
    scheduler: RunScheduler | None,
    resource_payload_builder: ResourcePayloadBuilder,
    enrich_active_runs: EnrichActiveRuns,
    mode: str,
) -> dict[str, object]:
    """Build one SSE payload. A fresh DB session is opened per tick so we
    don't hold a connection open for the lifetime of the stream.
    """
    snapshot = scheduler.get_resource_snapshot() if scheduler is not None else None
    resources = resource_payload_builder(snapshot)

    if scheduler is None:
        return {
            "mode": mode,
            "effective_mode": "legacy",
            "scheduler_available": False,
            "resources": resources,
            "active_runs": [],
            "queue_depth": 0,
            "states": DEFAULT_STATE_COUNTS,
        }

    status = await scheduler.get_status()
    async with app_database.async_session_maker() as session:
        active_runs = await enrich_active_runs(
            session, list(status.get("active_runs", []))
        )

    return {
        "mode": mode,
        "effective_mode": "persistent",
        "scheduler_available": True,
        "resources": resources,
        "active_runs": active_runs,
        "queue_depth": status.get("queue_depth", 0),
        "states": status.get("states", DEFAULT_STATE_COUNTS),
        "total_slots": status.get("total_slots", 0),
        "used_slots": status.get("used_slots", 0),
        "available_slots": status.get("available_slots", 0),
    }


async def resource_stream_generator(
    *,
    request: Request,
    scheduler: RunScheduler | None,
    resource_payload_builder: ResourcePayloadBuilder,
    enrich_active_runs: EnrichActiveRuns,
    mode: str,
    tick_seconds: float = TICK_SECONDS,
    heartbeat_seconds: float = HEARTBEAT_SECONDS,
) -> AsyncGenerator[str, None]:
    """Yield SSE-formatted frames describing scheduler state + host resources.

    Emits one frame immediately so clients see data without waiting a full
    tick. Subsequent frames arrive every ``tick_seconds``. When idle past
    ``heartbeat_seconds`` a comment ``: ping`` keeps intermediaries from
    closing the connection.
    """
    idle = 0.0
    try:
        # Send an immediate frame so the client has data right away.
        frame = await _build_frame(
            scheduler=scheduler,
            resource_payload_builder=resource_payload_builder,
            enrich_active_runs=enrich_active_runs,
            mode=mode,
        )
        yield _encode(frame)

        while True:
            await asyncio.sleep(min(tick_seconds, 1.0))
            idle += min(tick_seconds, 1.0)

            if await request.is_disconnected():
                break

            if idle + 1e-6 < tick_seconds:
                # Still inside the tick window; emit a heartbeat if we've
                # been idle for too long (rare when tick < heartbeat).
                if idle >= heartbeat_seconds:
                    yield ": ping\n\n"
                    idle = 0.0
                continue

            idle = 0.0
            try:
                frame = await _build_frame(
                    scheduler=scheduler,
                    resource_payload_builder=resource_payload_builder,
                    enrich_active_runs=enrich_active_runs,
                    mode=mode,
                )
            except Exception:  # noqa: BLE001
                # Never kill the stream on a transient backend hiccup;
                # skip this tick and try again next loop.
                logger.exception("scheduler.stream.frame_build_failed")
                continue
            yield _encode(frame)
    finally:
        logger.debug("scheduler.stream.client_disconnected")


def _encode(frame: dict[str, object]) -> str:
    payload = json.dumps(frame, default=str)
    return f"id: {uuid4()}\nevent: scheduler.resources\ndata: {payload}\n\n"
