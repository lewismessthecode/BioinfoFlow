from __future__ import annotations

from fastapi import APIRouter
from app.services.agent_harness.factory import (
    open_session_request_workspace,
    resolve_model_snapshot,
)
from app.services.agent_harness.runtime import agent_runtime
from app.services.agent_harness.session_deletion import session_mutation_lock
from app.api.v1.agent_command import (
    dispatch_command,
    router as command_router,
    stream_events,
)
from app.api.v1.agent_query import (
    download_artifact,
    get_artifact,
    get_snapshot,
    get_trace,
    get_trace_event_detail,
    list_agent_environments,
    list_session_artifacts,
    router as query_router,
    search_context,
)
from app.api.v1.agent_session import (
    create_session,
    delete_attachment,
    delete_session,
    list_sessions,
    preview_attachment,
    router as session_router,
    update_session,
    upload_attachments,
)
from app.api.v1.agent_settings import (
    get_settings,
    router as settings_router,
    update_settings,
)

router = APIRouter(prefix="/agent", tags=["agent"])
router.include_router(settings_router)
router.include_router(query_router)
router.include_router(session_router)
router.include_router(command_router)

__all__ = [
    "agent_runtime",
    "create_session",
    "delete_attachment",
    "delete_session",
    "dispatch_command",
    "download_artifact",
    "get_artifact",
    "get_settings",
    "get_snapshot",
    "get_trace",
    "get_trace_event_detail",
    "list_agent_environments",
    "list_session_artifacts",
    "list_sessions",
    "open_session_request_workspace",
    "preview_attachment",
    "resolve_model_snapshot",
    "router",
    "search_context",
    "session_mutation_lock",
    "stream_events",
    "update_session",
    "update_settings",
    "upload_attachments",
]
