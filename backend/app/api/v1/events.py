from __future__ import annotations

import json
import asyncio
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.auth.session import AuthUser
from app.repositories.project_repo import ProjectRepository
from app.runtime.events import events
from app.utils.exceptions import PermissionDeniedError
from app.utils.project_access import can_access_project


router = APIRouter(prefix="/events", tags=["events"])


@router.get("/stream")
async def stream_events(
    request: Request,
    project_id: str,
    conversation_id: str | None = None,
    run_id: str | None = None,
    image_id: str | None = None,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project_repo = ProjectRepository(db)
    project = await project_repo.get(project_id)
    if project is None or not can_access_project(
        project,
        user_id=user.id,
        workspace_id=user.workspace_id,
    ):
        raise PermissionDeniedError(
            "You do not have access to this project's event stream."
        )

    queue = await events.subscribe(project_id)
    heartbeat_seconds = 15

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(
                        queue.get(), timeout=heartbeat_seconds
                    )
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
                    continue
                if conversation_id and event.get("conversation_id") != conversation_id:
                    continue
                if run_id and event.get("run_id") != run_id:
                    continue
                if image_id and event.get("image_id") != image_id:
                    continue
                payload = json.dumps(event, default=str)
                yield f"id: {event['id']}\n"
                yield f"event: {event['event']}\n"
                yield f"data: {payload}\n\n"
        finally:
            events.unsubscribe(project_id, queue)

    return StreamingResponse(event_generator(), media_type="text/event-stream")
