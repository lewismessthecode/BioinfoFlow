from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

import app.database as app_database
from app.api.deps import get_current_user, get_db
from app.auth.session import AuthUser
from app.config import settings
from app.path_layout import project_home
from app.services.agent_core.sandbox import FilesystemPolicy
from app.utils.exceptions import BadRequestError, NotFoundError, PermissionDeniedError
from app.schemas.agent_core import (
    AgentActionDecisionRequest,
    AgentActionRead,
    AgentArtifactRead,
    AgentEventRead,
    AgentModelSelection,
    AgentMemoryDecisionRequest,
    AgentMemoryProposalCreate,
    AgentMemoryRead,
    AgentSessionCreate,
    AgentSessionRead,
    AgentSessionUpdate,
    AgentTurnCreate,
    AgentTurnRead,
)
from app.services.agent_core import AgentCoreService, AgentMemoryService
from app.services.agent_core.metrics import agent_metrics
from app.utils.logging import get_logger
from app.services.agent_core.model_selection import (
    normalize_model_selection,
    session_model_selection_from_metadata,
)
from app.services.agent_core.tools import build_default_tool_registry
from app.services.agent_core.tools.toolsets import ToolsetExposure
from app.services.project_service import ProjectService
from app.utils.responses import success_response


router = APIRouter(prefix="/agent", tags=["agent"])
logger = get_logger(__name__)


def _dump(model) -> dict:
    return model.model_dump(mode="json", exclude_none=True)


def _session_read(session) -> AgentSessionRead:
    model_selection = session_model_selection_from_metadata(
        getattr(session, "session_metadata", None)
    )
    return AgentSessionRead.model_validate(session).model_copy(
        update={
            "model_selection": (
                AgentModelSelection.model_validate(model_selection)
                if model_selection
                else None
            )
        }
    )


def _turn_read(turn) -> AgentTurnRead:
    snapshot = getattr(turn, "model_profile_snapshot", None) or {}
    model_selection_payload = (
        snapshot.get("resolved_model_selection")
        or snapshot.get("requested_model_selection")
    )
    if isinstance(model_selection_payload, dict) and snapshot.get("resolved_model_id"):
        model_selection_payload = {
            **model_selection_payload,
            "model_id": snapshot.get("resolved_model_id"),
        }
    model_selection = normalize_model_selection(model_selection_payload)
    return AgentTurnRead.model_validate(turn).model_copy(
        update={
            "model_selection": (
                AgentModelSelection.model_validate(model_selection)
                if model_selection
                else None
            )
        }
    )


def _event_read(event) -> AgentEventRead:
    return AgentEventRead.model_validate(event)


def _action_read(action) -> AgentActionRead:
    return AgentActionRead.model_validate(action)


def _artifact_read(artifact) -> AgentArtifactRead:
    return AgentArtifactRead.model_validate(artifact)


def _memory_read(memory) -> AgentMemoryRead:
    return AgentMemoryRead.model_validate(memory)


@router.post("/sessions")
async def create_session(
    payload: AgentSessionCreate,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = AgentCoreService(db)
    session = await service.create_session(
        project_id=str(payload.project_id) if payload.project_id else None,
        workspace_id=user.workspace_id,
        user_id=user.id,
        title=payload.title,
        role_profile=payload.role_profile,
        permission_mode=payload.permission_mode,
        automation_mode=payload.automation_mode,
        default_model_profile_id=(
            str(payload.default_model_profile_id)
            if payload.default_model_profile_id
            else None
        ),
        model_selection=(
            payload.model_selection.model_dump(mode="json", exclude_none=True)
            if payload.model_selection
            else None
        ),
        metadata=payload.metadata,
        toolset_policy={"name": payload.mode},
    )
    return success_response(
        _dump(_session_read(session)),
        request=request,
        status_code=201,
    )


@router.get("/sessions")
async def list_sessions(
    request: Request,
    project_id: str | None = Query(default=None),
    parent_session_id: str | None = Query(default=None),
    include_children: bool = Query(default=False),
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = AgentCoreService(db)
    sessions, pagination = await service.list_sessions(
        workspace_id=user.workspace_id,
        user_id=user.id,
        project_id=project_id,
        parent_session_id=parent_session_id,
        include_children=include_children,
    )
    return success_response(
        [_dump(_session_read(session)) for session in sessions],
        request=request,
        pagination=pagination,
    )


@router.get("/sessions/{session_id}")
async def get_session(
    session_id: str,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = AgentCoreService(db)
    session = await service.require_session(
        session_id=session_id,
        workspace_id=user.workspace_id,
        user_id=user.id,
    )
    return success_response(_dump(_session_read(session)), request=request)


@router.patch("/sessions/{session_id}")
async def update_session(
    session_id: str,
    payload: AgentSessionUpdate,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = AgentCoreService(db)
    session = await service.update_session(
        session_id=session_id,
        workspace_id=user.workspace_id,
        user_id=user.id,
        updates=payload.model_dump(mode="json", exclude_unset=True),
    )
    return success_response(_dump(_session_read(session)), request=request)


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = AgentCoreService(db)
    await service.delete_session(
        session_id=session_id,
        workspace_id=user.workspace_id,
        user_id=user.id,
    )
    return success_response({}, request=request, status_code=204)


@router.post("/sessions/{session_id}/turns")
async def create_turn(
    session_id: str,
    payload: AgentTurnCreate,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = AgentCoreService(db)
    turn = await service.create_turn(
        session_id=session_id,
        workspace_id=user.workspace_id,
        user_id=user.id,
        input_text=payload.input_text,
        input_parts=payload.input_parts,
        model_profile_id=str(payload.model_profile_id) if payload.model_profile_id else None,
        model_selection=(
            payload.model_selection.model_dump(mode="json", exclude_none=True)
            if payload.model_selection
            else None
        ),
        metadata=payload.metadata,
    )
    return success_response(_dump(_turn_read(turn)), request=request, status_code=202)


@router.get("/sessions/{session_id}/turns")
async def list_turns(
    session_id: str,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = AgentCoreService(db)
    turns = await service.list_turns(
        session_id=session_id,
        workspace_id=user.workspace_id,
        user_id=user.id,
    )
    return success_response(
        [_dump(_turn_read(turn)) for turn in turns],
        request=request,
    )


@router.get("/turns/{turn_id}")
async def get_turn(
    turn_id: str,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = AgentCoreService(db)
    turn = await service.require_turn(
        turn_id=turn_id,
        workspace_id=user.workspace_id,
        user_id=user.id,
    )
    return success_response(_dump(_turn_read(turn)), request=request)


@router.post("/turns/{turn_id}/cancel")
async def cancel_turn(
    turn_id: str,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = AgentCoreService(db)
    turn = await service.cancel_turn(
        turn_id=turn_id,
        workspace_id=user.workspace_id,
        user_id=user.id,
    )
    return success_response(_dump(_turn_read(turn)), request=request)


@router.post("/turns/{turn_id}/interrupt")
async def interrupt_turn(
    turn_id: str,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = AgentCoreService(db)
    turn = await service.interrupt_turn(
        turn_id=turn_id,
        workspace_id=user.workspace_id,
        user_id=user.id,
    )
    return success_response(_dump(_turn_read(turn)), request=request)


@router.get("/sessions/{session_id}/state")
async def get_session_state(
    session_id: str,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = AgentCoreService(db)
    session = await service.require_session(
        session_id=session_id,
        workspace_id=user.workspace_id,
        user_id=user.id,
    )
    turns = await service.list_turns(
        session_id=session_id,
        workspace_id=user.workspace_id,
        user_id=user.id,
    )
    events = await service.list_events_for_session(
        session_id=session_id,
        workspace_id=user.workspace_id,
        user_id=user.id,
    )
    return success_response(
        {
            "session": _dump(_session_read(session)),
            "turns": [_dump(_turn_read(turn)) for turn in turns],
            "events": [_dump(_event_read(event)) for event in events],
        },
        request=request,
    )


@router.get("/metrics")
async def get_agent_metrics(request: Request):
    return success_response(agent_metrics.snapshot(), request=request)


_FS_FILE_MAX_BYTES = 256 * 1024
_FS_DENIED_NAMES = {
    ".env",
    "better-auth.db",
    "bioinfoflow.db",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    "id_rsa",
}
_FS_DENIED_SUFFIXES = {".db", ".sqlite", ".sqlite3"}


@router.get("/fs/tree")
async def get_fs_tree(
    request: Request,
    path: str | None = Query(default=None),
    project_id: str | None = Query(default=None),
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List the immediate children of a directory inside the allowed roots.

    Read-only and confined by :class:`FilesystemPolicy` to repo_root /
    bioinfoflow_home. Lazy (one level): the Files tab requests subdirectories on
    expand rather than streaming the whole tree.
    """
    policy = FilesystemPolicy()
    if path:
        base = policy.require_allowed_dir(path)
    elif project_id:
        project = await ProjectService(db).get_project(
            project_id,
            workspace_id=user.workspace_id,
        )
        if not project:
            raise NotFoundError("Project not found")
        base = policy.require_allowed_dir(str(project_home(project)))
    else:
        base = policy.require_allowed_dir(str(settings.repo_root))
    entries = []
    for child in sorted(base.iterdir(), key=lambda p: (p.is_file(), p.name.lower())):
        if child.name.startswith(".git") or _is_sensitive_fs_path(child):
            continue
        is_dir = child.is_dir()
        entries.append(
            {
                "name": child.name,
                "path": str(child),
                "type": "dir" if is_dir else "file",
                "size": None if is_dir else _safe_size(child),
            }
        )
    return success_response({"path": str(base), "entries": entries}, request=request)


@router.get("/fs/file")
async def get_fs_file(
    request: Request,
    path: str = Query(...),
    user: AuthUser = Depends(get_current_user),
):
    """Return the text contents of a file inside the allowed roots."""
    target = FilesystemPolicy().require_allowed_path(
        path, must_exist=True, allow_directory=False
    )
    if _is_sensitive_fs_path(target):
        raise PermissionDeniedError(f"File is not available through agent file browsing: {target}")
    size = _safe_size(target) or 0
    raw = target.read_bytes()[:_FS_FILE_MAX_BYTES]
    truncated = size > _FS_FILE_MAX_BYTES
    try:
        content = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise BadRequestError("File is not valid UTF-8 text") from exc
    return success_response(
        {
            "path": str(target),
            "content": content,
            "truncated": truncated,
            "size": size,
            "language": _language_for(target),
        },
        request=request,
    )


def _safe_size(path: Path) -> int | None:
    try:
        return path.stat().st_size
    except OSError:
        return None


def _is_sensitive_fs_path(path: Path) -> bool:
    name = path.name.lower()
    if name in _FS_DENIED_NAMES:
        return True
    if name.startswith(".env."):
        return True
    if path.is_file() and path.suffix.lower() in _FS_DENIED_SUFFIXES:
        return True
    return False


def _language_for(path: Path) -> str | None:
    return {
        ".py": "python",
        ".ts": "typescript",
        ".tsx": "tsx",
        ".js": "javascript",
        ".jsx": "jsx",
        ".json": "json",
        ".md": "markdown",
        ".yml": "yaml",
        ".yaml": "yaml",
        ".toml": "toml",
        ".sh": "bash",
        ".nf": "groovy",
        ".wdl": "wdl",
        ".sql": "sql",
        ".css": "css",
        ".html": "html",
    }.get(path.suffix.lower())


@router.get("/toolsets")
async def list_toolsets(request: Request):
    registry = build_default_tool_registry()
    exposure = ToolsetExposure(registry)
    return success_response(
        {
            "toolsets": [
                {
                    "name": "default",
                    "tools": [spec.name for spec in exposure.exposed_specs(policy={"name": "default"})],
                },
                {
                    "name": "execution",
                    "tools": [spec.name for spec in exposure.exposed_specs(policy={"name": "execution"})],
                },
                {
                    "name": "plan",
                    "tools": [spec.name for spec in exposure.exposed_specs(policy={"name": "plan"})],
                },
            ]
        },
        request=request,
    )


@router.get("/turns/{turn_id}/events")
async def list_turn_events(
    turn_id: str,
    request: Request,
    after_seq: int = Query(default=0, ge=0),
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = AgentCoreService(db)
    events = await service.list_events_for_turn(
        turn_id=turn_id,
        workspace_id=user.workspace_id,
        user_id=user.id,
        after_seq=after_seq,
    )
    return success_response(
        [_dump(_event_read(event)) for event in events],
        request=request,
    )


@router.get("/sessions/{session_id}/stream")
async def stream_session_events(
    request: Request,
    session_id: str,
    after_seq: int = Query(default=0, ge=0),
    follow: bool = Query(default=True),
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = AgentCoreService(db)
    await service.require_session(
        session_id=session_id,
        workspace_id=user.workspace_id,
        user_id=user.id,
    )

    async def event_generator() -> AsyncGenerator[str, None]:
        cursor = after_seq
        ready_sent = False
        idle_seconds = 0.0
        poll_seconds = 0.5
        heartbeat_seconds = 15.0
        while True:
            if await request.is_disconnected():
                break
            async with app_database.async_session_maker() as stream_db:
                stream_service = AgentCoreService(stream_db)
                events = await stream_service.list_events_for_session(
                    session_id=session_id,
                    workspace_id=user.workspace_id,
                    user_id=user.id,
                    after_seq=cursor,
                )
            for event in events:
                payload = _dump(_event_read(event))
                cursor = max(cursor, int(payload["seq"]))
                yield f"id: {payload['id']}\n"
                yield f"event: {payload['type']}\n"
                yield f"data: {json.dumps(payload, separators=(',', ':'))}\n\n"
                logger.debug(
                    "agent_core.stream.event",
                    session_id=session_id,
                    turn_id=payload.get("turn_id"),
                    seq=int(payload["seq"]),
                    event_type=payload["type"],
                    follow=follow,
                )
            if events:
                logger.info(
                    "agent_core.stream.batch",
                    session_id=session_id,
                    event_count=len(events),
                    first_seq=int(events[0].seq),
                    last_seq=int(events[-1].seq),
                    follow=follow,
                )
            if not ready_sent:
                yield "event: ready\n"
                yield 'data: {"status":"streaming"}\n\n'
                logger.info(
                    "agent_core.stream.ready",
                    session_id=session_id,
                    after_seq=after_seq,
                    follow=follow,
                )
                ready_sent = True
                if not follow:
                    break
            if events:
                idle_seconds = 0.0
            else:
                idle_seconds += poll_seconds
                if idle_seconds >= heartbeat_seconds:
                    yield ": ping\n\n"
                    idle_seconds = 0.0
            await asyncio.sleep(poll_seconds)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.post("/actions/{action_id}/decision")
async def decide_action(
    action_id: str,
    payload: AgentActionDecisionRequest,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = AgentCoreService(db)
    action = await service.decide_action(
        action_id=action_id,
        workspace_id=user.workspace_id,
        user_id=user.id,
        decision=payload.decision,
        note=payload.note,
        modified_input=payload.modified_input,
        answer=payload.answer,
    )
    return success_response(_dump(_action_read(action)), request=request)


@router.post("/actions/{action_id}/resume")
async def resume_action(
    action_id: str,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = AgentCoreService(db)
    action = await service.resume_action(
        action_id=action_id,
        workspace_id=user.workspace_id,
        user_id=user.id,
    )
    return success_response(_dump(_action_read(action)), request=request)


@router.get("/memories")
async def list_memories(
    request: Request,
    project_id: str | None = Query(default=None),
    status: str | None = Query(default=None),
    scope: str | None = Query(default=None),
    type: str | None = Query(default=None),
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    memories = await AgentMemoryService(db).list_memories(
        workspace_id=user.workspace_id,
        project_id=project_id,
        status=status,
        scope=scope,
        type=type,
    )
    return success_response(
        [_dump(_memory_read(memory)) for memory in memories],
        request=request,
    )


@router.post("/memories/proposals")
async def propose_memory(
    payload: AgentMemoryProposalCreate,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    memory = await AgentMemoryService(db).propose_memory(
        workspace_id=user.workspace_id,
        project_id=str(payload.project_id) if payload.project_id else None,
        session_id=str(payload.session_id) if payload.session_id else None,
        turn_id=None,
        scope=payload.scope,
        type=payload.type,
        content=payload.content,
        source=payload.source,
        confidence=payload.confidence,
    )
    return success_response(
        _dump(_memory_read(memory)),
        request=request,
        status_code=201,
    )


@router.post("/memories/{memory_id}/accept")
async def accept_memory(
    memory_id: str,
    payload: AgentMemoryDecisionRequest,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    memory = await AgentMemoryService(db).update_memory_status(
        memory_id=memory_id,
        workspace_id=user.workspace_id,
        user_id=user.id,
        status="accepted",
        note=payload.note,
    )
    return success_response(_dump(_memory_read(memory)), request=request)


@router.post("/memories/{memory_id}/reject")
async def reject_memory(
    memory_id: str,
    payload: AgentMemoryDecisionRequest,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    memory = await AgentMemoryService(db).update_memory_status(
        memory_id=memory_id,
        workspace_id=user.workspace_id,
        user_id=user.id,
        status="rejected",
        note=payload.note,
    )
    return success_response(_dump(_memory_read(memory)), request=request)


@router.post("/memories/{memory_id}/disable")
async def disable_memory(
    memory_id: str,
    payload: AgentMemoryDecisionRequest,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    memory = await AgentMemoryService(db).update_memory_status(
        memory_id=memory_id,
        workspace_id=user.workspace_id,
        user_id=user.id,
        status="disabled",
        note=payload.note,
    )
    return success_response(_dump(_memory_read(memory)), request=request)


@router.get("/sessions/{session_id}/artifacts")
async def list_session_artifacts(
    session_id: str,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = AgentCoreService(db)
    artifacts = await service.list_artifacts_for_session(
        session_id=session_id,
        workspace_id=user.workspace_id,
        user_id=user.id,
    )
    return success_response(
        [_dump(_artifact_read(artifact)) for artifact in artifacts],
        request=request,
    )


@router.get("/turns/{turn_id}/artifacts")
async def list_turn_artifacts(
    turn_id: str,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = AgentCoreService(db)
    artifacts = await service.list_artifacts_for_turn(
        turn_id=turn_id,
        workspace_id=user.workspace_id,
        user_id=user.id,
    )
    return success_response(
        [_dump(_artifact_read(artifact)) for artifact in artifacts],
        request=request,
    )


@router.get("/artifacts/{artifact_id}")
async def get_artifact(
    artifact_id: str,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = AgentCoreService(db)
    artifact = await service.get_artifact(
        artifact_id=artifact_id,
        workspace_id=user.workspace_id,
        user_id=user.id,
    )
    return success_response(_dump(_artifact_read(artifact)), request=request)
