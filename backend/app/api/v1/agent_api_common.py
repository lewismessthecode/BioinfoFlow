from __future__ import annotations

import json

from fastapi.responses import StreamingResponse
from pydantic import TypeAdapter
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.session import AuthUser
from app.repositories.agent_harness_repo import AgentHarnessRepository
from app.repositories.remote_connection_repo import RemoteConnectionRepository
from app.services.agent_harness.contracts import AgentEvent, EnvironmentScope
from app.services.agent_harness.environment_catalog import EnvironmentCatalog
from app.services.agent_harness.environment_scope import (
    EnvironmentScopeRequest,
    EnvironmentSelectionError,
    resolve_environment_scope,
)
from app.utils.exceptions import BadRequestError, ConflictError, NotFoundError


class AgentEventStreamResponse(StreamingResponse):
    media_type = "text/event-stream"


_agent_event_data_schema = TypeAdapter(AgentEvent).json_schema()
_agent_event_data_schema["$id"] = "urn:bioinfoflow:schema:agent-event"
agent_event_stream_schema = {
    "type": "string",
    "description": (
        "UTF-8 Server-Sent Events. Each frame is `event: <AgentEvent.type>`, "
        "followed by `data: <JSON AgentEvent>` and a blank line. The decoded "
        "JSON data conforms to `x-sse-data-schema`."
    ),
    "x-sse-data-schema": _agent_event_data_schema,
}


async def resolve_environment_scope_payload(
    db: AsyncSession,
    *,
    workspace_id: str,
    requested: EnvironmentScope,
    allow_remote: bool,
) -> dict[str, object]:
    authorized = await EnvironmentCatalog(
        RemoteConnectionRepository(db)
    ).list_authorized(workspace_id=workspace_id, allow_remote=allow_remote)
    try:
        resolved = resolve_environment_scope(
            EnvironmentScopeRequest(
                mode=requested.mode,
                selected_environment_ids=tuple(requested.environment_ids or ()),
            ),
            authorized,
        )
    except EnvironmentSelectionError as exc:
        raise BadRequestError(str(exc)) from exc
    if resolved.mode == "auto":
        return {"mode": "auto"}
    return {"mode": "manual", "environment_ids": list(resolved.environment_ids)}


def dump_model(model) -> dict:
    return model.model_dump(mode="json")


async def owned_session(
    repository: AgentHarnessRepository, *, session_id: str, user: AuthUser
):
    session = await repository.get_session(session_id)
    if (
        session is None
        or session.status == "deleted"
        or session.user_id != user.id
        or str(session.workspace_id) != user.workspace_id
    ):
        raise NotFoundError(f"Agent session not found: {session_id}")
    return session


async def mutable_owned_session(
    repository: AgentHarnessRepository, *, session_id: str, user: AuthUser
):
    session = await owned_session(repository, session_id=session_id, user=user)
    if session.status != "active":
        raise ConflictError("Agent session is closing")
    return session


def event_payload(event: AgentEvent) -> str:
    return json.dumps(dump_model(event), ensure_ascii=False, separators=(",", ":"))
