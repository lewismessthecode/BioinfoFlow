from __future__ import annotations

import asyncio
import json
import mimetypes
from pathlib import Path
from typing import AsyncGenerator, Literal
from urllib.parse import quote

import aiofiles
from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
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
    AgentAttachmentRead,
    AgentContextSearchRead,
    AgentArtifactRead,
    AgentExecutionScope,
    AgentExecutionTarget,
    AgentEventRead,
    AgentModelSelection,
    AgentMemoryDecisionRequest,
    AgentMemoryProposalCreate,
    AgentMemoryRead,
    AgentSessionCreate,
    AgentSessionRead,
    AgentSessionUpdate,
    AgentSettingsRead,
    AgentSettingsUpdate,
    AgentSkillRead,
    AgentTokenUsageSummary,
    AgentTurnCreate,
    AgentTurnRead,
    AgentTurnSteer,
)
from app.repositories.agent_user_settings_repo import AgentUserSettingsRepository
from app.repositories.llm_repo import LlmModelRepository
from app.services.agent_core import AgentCoreService, AgentMemoryService
from app.services.agent_core.attachments import AgentAttachmentService
from app.services.agent_core.context_picker import AgentContextPicker
from app.services.agent_core.execution_target import (
    session_execution_scope_from_metadata,
    session_execution_target_from_metadata,
)
from app.services.agent_core.skills import AgentSkillRegistry
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
    execution_target = session_execution_target_from_metadata(
        getattr(session, "session_metadata", None)
    )
    execution_scope = session_execution_scope_from_metadata(
        getattr(session, "session_metadata", None)
    )
    model_selection = session_model_selection_from_metadata(
        getattr(session, "session_metadata", None)
    )
    return AgentSessionRead.model_validate(session).model_copy(
        update={
            "execution_target": AgentExecutionTarget.model_validate(execution_target),
            "execution_scope": (
                AgentExecutionScope.model_validate(execution_scope)
                if execution_scope
                else None
            ),
            "model_selection": (
                AgentModelSelection.model_validate(model_selection)
                if model_selection
                else None
            ),
        }
    )


def _attachment_read(attachment) -> AgentAttachmentRead:
    return AgentAttachmentRead.model_validate(attachment)


@router.get("/settings")
async def get_settings(
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_settings = await AgentUserSettingsRepository(db).get(
        user.workspace_id, user.id
    )
    return success_response(
        _dump(
            AgentSettingsRead(
                custom_instructions=(
                    user_settings.custom_instructions
                    if user_settings is not None
                    else ""
                )
            )
        ),
        request=request,
    )


@router.put("/settings")
async def update_settings(
    payload: AgentSettingsUpdate,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_settings = await AgentUserSettingsRepository(db).upsert(
        workspace_id=user.workspace_id,
        user_id=user.id,
        custom_instructions=payload.custom_instructions.strip(),
    )
    return success_response(
        _dump(AgentSettingsRead(custom_instructions=user_settings.custom_instructions)),
        request=request,
    )


def _turn_read(turn) -> AgentTurnRead:
    snapshot = getattr(turn, "model_profile_snapshot", None) or {}
    model_selection_payload = snapshot.get("resolved_model_selection") or snapshot.get(
        "requested_model_selection"
    )
    if isinstance(model_selection_payload, dict) and snapshot.get("resolved_model_id"):
        model_selection_payload = {
            **model_selection_payload,
            "model_id": snapshot.get("resolved_model_id"),
        }
    model_selection = normalize_model_selection(model_selection_payload)
    active_skill_names = []
    metadata = snapshot.get("metadata")
    if isinstance(metadata, dict) and isinstance(
        metadata.get("active_skill_names"), list
    ):
        active_skill_names = [
            item for item in metadata["active_skill_names"] if isinstance(item, str)
        ]
    return AgentTurnRead.model_validate(turn).model_copy(
        update={
            "active_skill_names": active_skill_names,
            "model_selection": (
                AgentModelSelection.model_validate(model_selection)
                if model_selection
                else None
            ),
        }
    )


def _event_read(event) -> AgentEventRead:
    return AgentEventRead.model_validate(event)


def _action_read(action) -> AgentActionRead:
    return AgentActionRead.model_validate(action)


def _dump_action(action) -> dict:
    return _action_read(action).model_dump(mode="json", exclude_none=False)


def _artifact_read(artifact) -> AgentArtifactRead:
    return AgentArtifactRead.model_validate(artifact)


def _memory_read(memory) -> AgentMemoryRead:
    return AgentMemoryRead.model_validate(memory)


def _skill_read(skill, *, include_body: bool = False) -> AgentSkillRead:
    return AgentSkillRead(
        name=skill.name,
        title=skill.title,
        version=skill.version,
        description=skill.description,
        category=skill.category,
        tags=skill.tags,
        source=skill.source,
        root=str(skill.root) if skill.root else None,
        path=str(skill.path),
        body=skill.body if include_body else None,
    )


@router.get("/skills")
async def list_skills(
    request: Request,
    user: AuthUser = Depends(get_current_user),
):
    del user
    registry = AgentSkillRegistry.from_default_roots()
    return success_response(
        {"skills": [_dump(_skill_read(skill)) for skill in registry.list()]},
        request=request,
    )


@router.get("/skills/{skill_name}")
async def get_skill(
    skill_name: str,
    request: Request,
    user: AuthUser = Depends(get_current_user),
):
    del user
    registry = AgentSkillRegistry.from_default_roots()
    skill = registry.get(skill_name)
    return success_response(
        _dump(_skill_read(skill, include_body=True)), request=request
    )


@router.get("/context/search")
async def search_context(
    request: Request,
    q: str = Query(default="", max_length=500),
    scope: str = Query(default="mixed"),
    project_id: str | None = Query(default=None),
    session_id: str | None = Query(default=None),
    cursor: str | None = Query(default=None),
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await AgentContextPicker(db).search(
        workspace_id=user.workspace_id,
        user_id=user.id,
        query=q,
        scope=scope,
        project_id=project_id,
        session_id=session_id,
        cursor=cursor,
    )
    return success_response(
        _dump(AgentContextSearchRead.model_validate(result)),
        request=request,
    )


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
        execution_target=(
            payload.execution_target.model_dump(mode="json", exclude_none=True)
            if payload.execution_target
            else None
        ),
        execution_scope=(
            payload.execution_scope.model_dump(mode="json", exclude_none=True)
            if payload.execution_scope
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


@router.post("/sessions/{session_id}/attachments")
async def upload_attachments(
    session_id: str,
    request: Request,
    kind: str = Form(...),
    source: str = Form(default="clipboard"),
    files: list[UploadFile] = File(...),
    relative_paths: list[str] | None = Form(default=None),
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await AgentCoreService(db).require_session(
        session_id=session_id,
        workspace_id=user.workspace_id,
        user_id=user.id,
    )
    service = AgentAttachmentService(db)
    if kind == "folder":
        attachment = await service.ingest_folder(
            agent_session=session,
            files=files,
            relative_paths=relative_paths or [],
        )
        attachments = [attachment]
    elif kind == "image":
        if len(files) != 1:
            raise BadRequestError("Image upload requires exactly one file")
        if source not in {"upload", "clipboard"}:
            raise BadRequestError("Unsupported image source")
        attachments = [
            await service.ingest_image(
                agent_session=session,
                file=files[0],
                source=source,
            )
        ]
    elif kind == "file":
        if relative_paths:
            raise BadRequestError("File uploads do not accept relative paths")
        attachments = await service.ingest_files(
            agent_session=session,
            files=files,
        )
    else:
        raise BadRequestError("Unsupported attachment kind")
    return success_response(
        [_dump(_attachment_read(attachment)) for attachment in attachments],
        request=request,
        status_code=201,
    )


@router.get("/attachments/{attachment_id}/preview")
async def preview_attachment(
    attachment_id: str,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    path, media_type = await AgentAttachmentService(db).preview_path(
        attachment_id=attachment_id,
        workspace_id=user.workspace_id,
        user_id=user.id,
    )
    return FileResponse(path, media_type=media_type)


@router.delete("/attachments/{attachment_id}")
async def delete_attachment(
    attachment_id: str,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await AgentAttachmentService(db).delete_pending(
        attachment_id=attachment_id,
        workspace_id=user.workspace_id,
        user_id=user.id,
    )
    return success_response({"deleted": True}, request=request)


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
        active_skill_names=payload.active_skill_names,
        model_profile_id=str(payload.model_profile_id)
        if payload.model_profile_id
        else None,
        model_selection=(
            payload.model_selection.model_dump(mode="json", exclude_none=True)
            if payload.model_selection
            else None
        ),
        execution_target=(
            payload.execution_target.model_dump(mode="json", exclude_none=True)
            if payload.execution_target
            else None
        ),
        execution_scope=(
            payload.execution_scope.model_dump(mode="json", exclude_none=True)
            if payload.execution_scope
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


@router.post("/turns/{turn_id}/steer")
async def steer_turn(
    turn_id: str,
    payload: AgentTurnSteer,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = AgentCoreService(db)
    result = await service.steer_turn(
        turn_id=turn_id,
        workspace_id=user.workspace_id,
        user_id=user.id,
        input_text=payload.input_text,
        input_parts=payload.input_parts,
        active_skill_names=payload.active_skill_names,
        metadata=payload.metadata,
    )
    return success_response(_dump(result), request=request)


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
    event_limit: int | None = Query(default=None, ge=1, le=5000),
    event_view: Literal["full", "transcript"] = Query(default="full"),
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
        limit=event_limit,
        transcript_view=event_view == "transcript",
    )
    token_usage_summary = await _token_usage_summary_for_turns(
        turns,
        db=db,
        workspace_id=user.workspace_id,
        user_id=user.id,
    )
    session_read = _session_read(session).model_copy(
        update={"token_usage_summary": token_usage_summary}
    )
    return success_response(
        {
            "session": _dump(session_read),
            "turns": [_dump(_turn_read(turn)) for turn in turns],
            "events": [_dump(_event_read(event)) for event in events],
        },
        request=request,
    )


@router.get("/metrics")
async def get_agent_metrics(request: Request):
    return success_response(agent_metrics.snapshot(), request=request)


async def _token_usage_summary_for_turns(
    turns: list,
    *,
    db: AsyncSession,
    workspace_id: str,
    user_id: str,
) -> AgentTokenUsageSummary:
    input_tokens = 0
    output_tokens = 0
    total_tokens = 0
    cached_input_tokens = 0
    reasoning_tokens = 0
    cached_input_tokens_reported = False
    reasoning_tokens_reported = False
    raw_totals: dict[str, int] = {}
    turns_with_usage = 0

    for turn in turns:
        usage = getattr(turn, "token_usage", None)
        if not isinstance(usage, dict) or not usage:
            continue
        turns_with_usage += 1
        for key, value in usage.items():
            numeric_value = _int_token_value(value)
            if numeric_value is not None:
                raw_totals[key] = raw_totals.get(key, 0) + numeric_value

        input_count = _first_int_token_value(usage, "prompt_tokens", "input_tokens")
        output_count = _first_int_token_value(
            usage, "completion_tokens", "output_tokens"
        )
        total_count = _first_int_token_value(usage, "total_tokens")
        if input_count is not None:
            input_tokens += input_count
        if output_count is not None:
            output_tokens += output_count
        if total_count is not None:
            total_tokens += total_count
        elif input_count is not None or output_count is not None:
            total_tokens += (input_count or 0) + (output_count or 0)

        cached_count = _first_int_token_value(usage, "cached_input_tokens")
        if cached_count is None:
            prompt_details = usage.get("prompt_tokens_details")
            if isinstance(prompt_details, dict):
                cached_count = _first_int_token_value(prompt_details, "cached_tokens")
        if cached_count is not None:
            cached_input_tokens += cached_count
            cached_input_tokens_reported = True

        reasoning_count = _first_int_token_value(usage, "reasoning_tokens")
        if reasoning_count is None:
            completion_details = usage.get("completion_tokens_details")
            if isinstance(completion_details, dict):
                reasoning_count = _first_int_token_value(
                    completion_details,
                    "reasoning_tokens",
                )
        if reasoning_count is not None:
            reasoning_tokens += reasoning_count
            reasoning_tokens_reported = True

    context_window = None
    max_output_tokens = None
    model_id = _latest_resolved_model_id(turns)
    if model_id:
        model = await LlmModelRepository(db).get_visible(
            model_id,
            workspace_id=workspace_id,
            user_id=user_id,
        )
        if model is not None:
            context_window = model.context_length
            max_output_tokens = model.max_output_tokens

    return AgentTokenUsageSummary(
        has_token_usage=turns_with_usage > 0,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        cached_input_tokens=(
            cached_input_tokens if cached_input_tokens_reported else None
        ),
        reasoning_tokens=reasoning_tokens if reasoning_tokens_reported else None,
        context_window=context_window,
        max_output_tokens=max_output_tokens,
        turns_with_usage=turns_with_usage,
        raw_totals=raw_totals,
    )


def _latest_resolved_model_id(turns: list) -> str | None:
    for turn in reversed(turns):
        snapshot = getattr(turn, "model_profile_snapshot", None)
        if isinstance(snapshot, dict) and isinstance(
            snapshot.get("resolved_model_id"), str
        ):
            return snapshot["resolved_model_id"]
    return None


def _first_int_token_value(data: dict, *keys: str) -> int | None:
    for key in keys:
        value = _int_token_value(data.get(key))
        if value is not None:
            return value
    return None


def _int_token_value(value) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value >= 0:
        return value
    return None


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
_FS_PREVIEWABLE_BINARY_SUFFIXES = {
    ".pdf",
    ".xlsx",
    ".xls",
    ".xlsm",
    ".ods",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".svg",
    ".bmp",
    ".ico",
    ".tif",
    ".tiff",
}
_FS_ACTIVE_PREVIEW_MIME_TYPES = {
    "application/xhtml+xml",
    "image/svg+xml",
    "text/html",
}
_FS_INLINE_ACTIVE_CONTENT_CSP = (
    "sandbox; default-src 'none'; img-src data: blob:; "
    "style-src 'unsafe-inline'; font-src data:; base-uri 'none'; form-action 'none'"
)


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
        if getattr(project, "storage_mode", None) == "remote":
            raise BadRequestError("Remote projects use SSH file browsing")
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
    """Return preview metadata and text contents when available."""
    target = FilesystemPolicy().require_allowed_path(
        path, must_exist=True, allow_directory=False
    )
    if _is_sensitive_fs_path(target):
        raise PermissionDeniedError(
            f"File is not available through agent file browsing: {target}"
        )
    size = _safe_size(target) or 0
    async with aiofiles.open(target, "rb") as handle:
        raw = await handle.read(_FS_FILE_MAX_BYTES + 1)
    truncated = len(raw) > _FS_FILE_MAX_BYTES or size > _FS_FILE_MAX_BYTES
    raw = raw[:_FS_FILE_MAX_BYTES]
    mime_type = _mime_type_for(target)
    binary = _is_previewable_binary(target, mime_type)
    content = ""
    if not binary:
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
            "mime_type": mime_type,
            "binary": binary,
        },
        request=request,
    )


@router.get("/fs/download")
async def download_fs_file(
    request: Request,
    path: str = Query(...),
    inline: bool = Query(default=False),
    user: AuthUser = Depends(get_current_user),
):
    """Stream a file inside the allowed roots for preview or download."""
    target = FilesystemPolicy().require_allowed_path(
        path, must_exist=True, allow_directory=False
    )
    if _is_sensitive_fs_path(target):
        raise PermissionDeniedError(
            f"File is not available through agent file browsing: {target}"
        )

    async def file_iterator():
        async with aiofiles.open(target, "rb") as handle:
            while True:
                chunk = await handle.read(1024 * 1024)
                if not chunk:
                    break
                yield chunk

    mime_type = _mime_type_for(target)
    disposition = "inline" if inline else "attachment"
    headers = {
        "Content-Disposition": _content_disposition(disposition, target.name),
        "X-Content-Type-Options": "nosniff",
    }
    if inline and _is_active_preview_mime_type(mime_type):
        headers["Content-Security-Policy"] = _FS_INLINE_ACTIVE_CONTENT_CSP
    return StreamingResponse(
        file_iterator(),
        media_type=mime_type,
        headers=headers,
    )


def _safe_size(path: Path) -> int | None:
    try:
        return path.stat().st_size
    except OSError:
        return None


def _content_disposition(disposition: str, filename: str) -> str:
    ascii_fallback = "".join(
        char if 32 <= ord(char) < 127 and char not in {'"', "\\", ";"} else "_"
        for char in filename
    ).strip()
    if not ascii_fallback:
        ascii_fallback = "download"
    return (
        f'{disposition}; filename="{ascii_fallback}"; '
        f"filename*=UTF-8''{quote(filename, safe='')}"
    )


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
        ".htm": "html",
        ".csv": "csv",
        ".tsv": "tsv",
        ".pdf": "pdf",
        ".xlsx": "spreadsheet",
        ".xls": "spreadsheet",
        ".xlsm": "spreadsheet",
        ".ods": "spreadsheet",
    }.get(path.suffix.lower())


def _mime_type_for(path: Path) -> str:
    guessed, _ = mimetypes.guess_type(path.name)
    return guessed or "application/octet-stream"


def _is_active_preview_mime_type(mime_type: str) -> bool:
    return mime_type.lower().split(";", 1)[0] in _FS_ACTIVE_PREVIEW_MIME_TYPES


def _is_previewable_binary(path: Path, mime_type: str) -> bool:
    suffix = path.suffix.lower()
    return (
        mime_type == "application/pdf"
        or mime_type.startswith("image/")
        or suffix in _FS_PREVIEWABLE_BINARY_SUFFIXES
    )


@router.get("/toolsets")
async def list_toolsets(request: Request):
    registry = build_default_tool_registry()
    exposure = ToolsetExposure(registry)
    return success_response(
        {
            "toolsets": [
                {
                    "name": "default",
                    "tools": [
                        spec.name
                        for spec in exposure.exposed_specs(policy={"name": "default"})
                    ],
                },
                {
                    "name": "execution",
                    "tools": [
                        spec.name
                        for spec in exposure.exposed_specs(policy={"name": "execution"})
                    ],
                },
                {
                    "name": "plan",
                    "tools": [
                        spec.name
                        for spec in exposure.exposed_specs(policy={"name": "plan"})
                    ],
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


@router.get("/actions/{action_id}")
async def get_action(
    action_id: str,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    action = await AgentCoreService(db).get_action(
        action_id=action_id,
        workspace_id=user.workspace_id,
        user_id=user.id,
    )
    return success_response(_dump_action(action), request=request)


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
    return success_response(_dump_action(action), request=request)


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
    return success_response(_dump_action(action), request=request)


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
