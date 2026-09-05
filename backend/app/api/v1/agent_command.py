from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_current_user, get_current_user_for_stream, get_db
from app.api.v1.agent_api_common import (
    AgentEventStreamResponse,
    agent_event_stream_schema,
    dump_model,
    event_payload,
    mutable_owned_session,
    owned_session,
)
from app.auth.session import AuthUser
from app.repositories.agent_harness_repo import AgentHarnessRepository
from app.schemas.common import SuccessEnvelope
from app.services.agent_harness.command_authorization import authorize_command_parts
from app.services.agent_harness.contracts import AgentCommand, SessionSnapshot
from app.utils.exceptions import ConflictError
from app.utils.responses import success_response

from app.api.v1 import agent as agent_api


router = APIRouter()


@router.post(
    "/sessions/{session_id}/commands",
    status_code=202,
    response_model=SuccessEnvelope[SessionSnapshot],
)
async def dispatch_command(
    session_id: str,
    payload: AgentCommand,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    repository = AgentHarnessRepository(db)
    await owned_session(repository, session_id=session_id, user=user)
    async with agent_api.session_mutation_lock(session_id):
        db.expire_all()
        agent_session = await mutable_owned_session(
            repository, session_id=session_id, user=user
        )
        command = payload
        await authorize_command_parts(
            db,
            session_id=str(agent_session.id),
            project_id=(
                str(agent_session.project_id) if agent_session.project_id else None
            ),
            command=command,
            user=user,
        )
        try:
            await agent_api.agent_runtime.dispatch(session_id, command)
        except ValueError as exc:
            raise ConflictError(str(exc)) from exc
        return success_response(
            dump_model(await agent_api.agent_runtime.snapshot(session_id)),
            request=request,
            status_code=202,
        )


@router.get(
    "/sessions/{session_id}/events",
    response_class=AgentEventStreamResponse,
    responses={
        200: {
            "description": "Server-sent Agent Harness events",
            "content": {"text/event-stream": {"schema": agent_event_stream_schema}},
        }
    },
)
async def stream_events(
    session_id: str,
    user: AuthUser = Depends(get_current_user_for_stream, scope="function"),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    repository = AgentHarnessRepository(db)
    await owned_session(repository, session_id=session_id, user=user)

    async def generate():
        async for event in agent_api.agent_runtime.events(session_id):
            payload = event_payload(event)
            yield f"event: {event.type}\ndata: {payload}\n\n"

    return AgentEventStreamResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


__all__ = [
    "dispatch_command",
    "stream_events",
    "router",
]
