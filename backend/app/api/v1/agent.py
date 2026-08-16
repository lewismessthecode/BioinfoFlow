from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
import json
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_current_user_for_stream, get_db
from app.auth.session import AuthUser
from app.repositories.agent_harness_repo import (
    AgentHarnessAttachmentRepository,
    AgentHarnessRepository,
)
from app.repositories.agent_user_settings_repo import AgentUserSettingsRepository
from app.repositories.project_repo import ProjectRepository
from app.repositories.project_workflow_binding_repo import (
    ProjectWorkflowBindingRepository,
)
from app.services.agent_harness.assets import (
    AgentHarnessArtifactService,
    AgentHarnessAttachmentService,
    stage_agent_session_files_for_delete,
)
from app.services.agent_harness.contracts import (
    AgentCommand,
    AgentEvent,
    ExecutionScopeSelection,
    InputAttachmentRefPart,
    InputDirectoryRefPart,
    InputFileRefPart,
    InputRunRefPart,
    InputWorkflowRefPart,
    MessageCommand,
    OpenSessionRequest,
    PermissionMode,
    SessionSnapshot,
    SteerCommand,
    WorkspaceAccess,
)
from app.services.agent_harness.context import build_session_prompt_snapshot
from app.services.agent_harness.context_search import (
    AgentContextSearch,
    ContextSearchResult,
)
from app.services.agent_harness.factory import (
    open_session_request_workspace,
    resolve_model_snapshot,
)
from app.services.agent_harness.runtime import agent_runtime
from app.services.agent_harness.system_prompt import default_system_prompt_snapshot
from app.services.agent_ui.bootstrap import build_agent_ui_bootstrap
from app.services.agent_ui.contracts import AgentUiBootstrap
from app.services.agent_ui.execution_targets import (
    execution_target_catalog,
    normalize_execution_scope,
    selected_execution_targets,
)
from app.services.file_service import FileService
from app.services.run_service import RunService
from app.services.workflow_service import WorkflowService
from app.schemas.common import SuccessEnvelope
from app.utils.exceptions import (
    BadRequestError,
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
)
from app.utils.authorization import can_access_project
from app.utils.responses import success_response


router = APIRouter(prefix="/agent", tags=["agent"])


class _AgentEventStreamResponse(StreamingResponse):
    media_type = "text/event-stream"


_agent_event_data_schema = TypeAdapter(AgentEvent).json_schema()
_agent_event_data_schema["$id"] = "urn:bioinfoflow:schema:agent-event"
_agent_event_stream_schema = {
    "type": "string",
    "description": (
        "UTF-8 Server-Sent Events. Each frame is `event: <AgentEvent.type>`, "
        "followed by `data: <JSON AgentEvent>` and a blank line. The decoded "
        "JSON data conforms to `x-sse-data-schema`."
    ),
    "x-sse-data-schema": _agent_event_data_schema,
}


@dataclass
class _SessionMutationLockEntry:
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    users: int = 0


_session_mutation_locks: dict[str, _SessionMutationLockEntry] = {}


@asynccontextmanager
async def _session_mutation_lock(session_id: str):
    entry = _session_mutation_locks.setdefault(session_id, _SessionMutationLockEntry())
    entry.users += 1
    try:
        async with entry.lock:
            yield
    finally:
        entry.users -= 1
        if entry.users == 0 and _session_mutation_locks.get(session_id) is entry:
            _session_mutation_locks.pop(session_id, None)


class AgentSessionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    project_id: UUID | None = None
    title: str | None = Field(default=None, max_length=200)
    execution_scope: ExecutionScopeSelection | None = None
    permission_mode: PermissionMode = "ask_dangerous"
    workspace_access: WorkspaceAccess = "read_write"
    model_id: UUID | None = None
    profile_id: UUID | None = None
    provider: str | None = Field(default=None, min_length=1, max_length=200)
    model: str | None = Field(default=None, min_length=1, max_length=500)
    metadata: dict | None = None

    @model_validator(mode="after")
    def validate_model_selector(self) -> AgentSessionCreate:
        provider_selected = self.provider is not None or self.model is not None
        if provider_selected and (self.provider is None or self.model is None):
            raise ValueError("provider and model must be supplied together")
        selector_count = sum(
            (
                self.model_id is not None,
                self.profile_id is not None,
                provider_selected,
            )
        )
        if selector_count > 1:
            raise ValueError(
                "choose only one model selector: model_id, profile_id, or provider and model"
            )
        return self


class AgentSessionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str | None = Field(default=None, max_length=200)
    permission_mode: PermissionMode | None = None
    workspace_access: WorkspaceAccess | None = None
    status: Literal["active", "archived"] | None = None

    @model_validator(mode="after")
    def validate_update(self) -> AgentSessionUpdate:
        if not self.model_fields_set:
            raise ValueError("at least one session setting is required")
        for field_name in ("permission_mode", "workspace_access", "status"):
            if field_name in self.model_fields_set and getattr(self, field_name) is None:
                raise ValueError(f"{field_name} cannot be null")
        return self


class AgentSettingsRead(BaseModel):
    custom_instructions: str = ""


class AgentSettingsUpdate(BaseModel):
    custom_instructions: str = Field(default="", max_length=20_000)


class AgentSessionSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    title: str | None = None
    project_id: UUID | None = None
    permission_mode: PermissionMode
    workspace_access: WorkspaceAccess
    status: Literal["active", "archived", "closing", "deleted"]
    created_at: datetime
    updated_at: datetime


class AgentAttachmentView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    session_id: UUID
    workspace_id: UUID
    user_id: str
    kind: str
    source: str
    filename: str
    mime_type: str | None = None
    size_bytes: int = Field(ge=0)
    file_count: int | None = Field(default=None, ge=0)
    image_width: int | None = Field(default=None, ge=0)
    image_height: int | None = Field(default=None, ge=0)
    status: str
    metadata: dict | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class AgentArtifactView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    session_id: UUID
    run_id: UUID | None = None
    type: str
    title: str
    summary: str | None = None
    payload: dict | None = None
    resource_ref: dict | None = None
    created_at: datetime
    updated_at: datetime


class DeletedResource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    deleted: Literal[True]


def _selection(payload: AgentSessionCreate) -> dict[str, str] | None:
    if payload.model_id:
        return {"model_id": str(payload.model_id)}
    if payload.profile_id:
        return {"profile_id": str(payload.profile_id)}
    if payload.provider and payload.model:
        return {"provider": payload.provider, "model": payload.model}
    return None


def _message_model_selection(command: MessageCommand) -> dict[str, str] | None:
    selection = command.run_settings.model if command.run_settings else None
    if selection is None:
        return None
    if selection.model_id:
        return {"model_id": str(selection.model_id)}
    if selection.profile_id:
        return {"profile_id": str(selection.profile_id)}
    if selection.provider and selection.model:
        return {"provider": selection.provider, "model": selection.model}
    return None


async def _message_run_settings_snapshot(
    db: AsyncSession,
    *,
    user: AuthUser,
    session,
    command: MessageCommand,
) -> dict:
    requested = command.run_settings
    model_selection = _message_model_selection(command)
    model_snapshot = (
        await resolve_model_snapshot(
            db,
            workspace_id=user.workspace_id,
            user_id=user.id,
            selection=model_selection,
        )
        if model_selection is not None
        else session.model_snapshot
    )
    if not isinstance(model_snapshot, dict):
        raise BadRequestError("Agent model selection is unavailable")

    project_id = str(session.project_id) if session.project_id else None
    targets, default_scope = await execution_target_catalog(
        db,
        workspace_id=user.workspace_id,
        user_id=user.id,
        project_id=project_id,
    )
    current_scope = session.execution_scope or default_scope.model_dump(mode="json")
    scope = normalize_execution_scope(
        requested.execution_scope if requested else current_scope,
        targets=targets,
        default=default_scope,
    )
    allowed_targets = selected_execution_targets(scope, targets)
    permission_mode = (
        requested.permission_mode
        if requested and requested.permission_mode is not None
        else session.permission_mode
    )
    return {
        "model_snapshot": model_snapshot,
        "permission_mode": permission_mode,
        "execution_scope": scope.model_dump(mode="json"),
        "allowed_targets": [target.model_dump(mode="json") for target in allowed_targets],
    }


def _dump(model) -> dict:
    return model.model_dump(mode="json")


async def _owned_session(
    repository: AgentHarnessRepository,
    *,
    session_id: str,
    user: AuthUser,
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


async def _mutable_owned_session(
    repository: AgentHarnessRepository,
    *,
    session_id: str,
    user: AuthUser,
):
    session = await _owned_session(
        repository,
        session_id=session_id,
        user=user,
    )
    if session.status != "active":
        raise ConflictError("Agent session is closing")
    return session


async def _authorize_command_parts(
    db: AsyncSession,
    *,
    session_id: str,
    project_id: str | None,
    command: AgentCommand,
    user: AuthUser,
) -> None:
    if not isinstance(command, (MessageCommand, SteerCommand)):
        return

    attachment_ids = []
    for part in command.parts:
        if isinstance(part, InputAttachmentRefPart):
            attachment_ids.append(str(part.attachment_id))
        elif isinstance(part, (InputFileRefPart, InputDirectoryRefPart)):
            if part.attachment_id is not None:
                attachment_ids.append(str(part.attachment_id))
    attachments_by_id = {}
    if attachment_ids:
        try:
            attachments = await AgentHarnessAttachmentRepository(
                db
            ).require_ids_for_session(
                attachment_ids,
                session_id=session_id,
                workspace_id=user.workspace_id,
                user_id=user.id,
            )
        except LookupError as exc:
            raise NotFoundError("One or more attachments were not found") from exc
        attachments_by_id = {str(item.id): item for item in attachments}

    file_service = FileService(db)
    for part in command.parts:
        if isinstance(part, (InputFileRefPart, InputDirectoryRefPart)):
            if part.attachment_id is not None:
                attachment = attachments_by_id[str(part.attachment_id)]
                is_directory = attachment.kind == "folder"
                if isinstance(part, InputFileRefPart) and is_directory:
                    raise BadRequestError("file_ref must reference a file")
                if isinstance(part, InputDirectoryRefPart) and not is_directory:
                    raise BadRequestError("directory_ref must reference a directory")
                continue
            assert part.project_id is not None
            assert part.path is not None
            try:
                target, root = await file_service.resolve_path(
                    project_id=str(part.project_id),
                    path=part.path,
                    user_id=user.id,
                    workspace_id=user.workspace_id,
                )
            except (FileNotFoundError, PermissionError, PermissionDeniedError) as exc:
                raise NotFoundError("Referenced path was not found") from exc
            if isinstance(part, InputFileRefPart) and not target.is_file():
                raise BadRequestError("file_ref must reference a file")
            if isinstance(part, InputDirectoryRefPart) and not target.is_dir():
                raise BadRequestError("directory_ref must reference a directory")
            part.path = target.relative_to(root).as_posix()
        elif isinstance(part, InputWorkflowRefPart):
            workflow_id = str(part.workflow_id)
            workflow = await WorkflowService(db).get_workflow(workflow_id)
            if workflow is None:
                raise NotFoundError("Referenced workflow was not found")
            if part.scope == "project":
                assert part.project_id is not None
                referenced_project_id = str(part.project_id)
                project = await ProjectRepository(db).get(referenced_project_id)
                if project is None or not can_access_project(
                    project,
                    user_id=user.id,
                    workspace_id=user.workspace_id,
                ):
                    raise NotFoundError("Referenced workflow was not found")
                if not await ProjectWorkflowBindingRepository(db).is_enabled(
                    project_id=referenced_project_id,
                    workflow_id=workflow_id,
                ):
                    raise NotFoundError("Referenced workflow was not found")
        elif isinstance(part, InputRunRefPart):
            try:
                run = await RunService(db).get_run(
                    part.run_id,
                    user_id=user.id,
                    workspace_id=user.workspace_id,
                )
            except PermissionDeniedError as exc:
                raise NotFoundError("Referenced run was not found") from exc
            if run is None or str(run.project_id) != project_id:
                raise NotFoundError("Referenced run was not found")
            part.run_id = str(run.run_id)


def _attachment_data(attachment) -> dict:
    return {
        "id": str(attachment.id),
        "session_id": str(attachment.session_id),
        "workspace_id": str(attachment.workspace_id),
        "user_id": attachment.user_id,
        "kind": attachment.kind,
        "source": attachment.source,
        "filename": attachment.filename,
        "mime_type": attachment.mime_type,
        "size_bytes": attachment.size_bytes,
        "file_count": attachment.file_count,
        "image_width": attachment.image_width,
        "image_height": attachment.image_height,
        "status": attachment.status,
        "metadata": attachment.attachment_metadata,
        "error_message": attachment.error_message,
        "created_at": attachment.created_at.isoformat(),
        "updated_at": attachment.updated_at.isoformat(),
    }


def _artifact_data(artifact) -> dict:
    run_id = str(artifact.run_id) if artifact.run_id else None
    return {
        "id": str(artifact.id),
        "session_id": str(artifact.session_id),
        "run_id": run_id,
        "type": artifact.type,
        "title": artifact.title,
        "summary": artifact.summary,
        "payload": artifact.payload,
        "resource_ref": artifact.resource_ref,
        "created_at": artifact.created_at.isoformat(),
        "updated_at": artifact.updated_at.isoformat(),
    }


@router.get("/settings", response_model=SuccessEnvelope[AgentSettingsRead])
async def get_settings(
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_settings = await AgentUserSettingsRepository(db).get(
        user.workspace_id,
        user.id,
    )
    return success_response(
        AgentSettingsRead(
            custom_instructions=(
                user_settings.custom_instructions if user_settings is not None else ""
            )
        ).model_dump(mode="json"),
        request=request,
    )


@router.put("/settings", response_model=SuccessEnvelope[AgentSettingsRead])
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
        AgentSettingsRead(
            custom_instructions=user_settings.custom_instructions
        ).model_dump(mode="json"),
        request=request,
    )


@router.get(
    "/ui/bootstrap",
    response_model=SuccessEnvelope[AgentUiBootstrap],
)
async def get_agent_ui_bootstrap(
    request: Request,
    project_id: str | None = Query(default=None),
    locale: str = Query(default="en", max_length=32),
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    bootstrap = await build_agent_ui_bootstrap(
        db,
        workspace_id=user.workspace_id,
        user_id=user.id,
        project_id=project_id,
        locale=locale,
    )
    return success_response(bootstrap.model_dump(mode="json"), request=request)


@router.get(
    "/context/search",
    response_model=SuccessEnvelope[ContextSearchResult],
)
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
    result = await AgentContextSearch(db).search(
        workspace_id=user.workspace_id,
        user_id=user.id,
        query=q,
        scope=scope,
        project_id=project_id,
        session_id=session_id,
        cursor=cursor,
    )
    return success_response(result.model_dump(mode="json"), request=request)


@router.post(
    "/sessions",
    status_code=201,
    response_model=SuccessEnvelope[SessionSnapshot],
)
async def create_session(
    payload: AgentSessionCreate,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project_id = str(payload.project_id) if payload.project_id else None
    workspace = await open_session_request_workspace(
        db,
        project_id=project_id,
        workspace_id=user.workspace_id,
        user_id=user.id,
    )
    execution_targets, default_execution_scope = await execution_target_catalog(
        db,
        workspace_id=user.workspace_id,
        user_id=user.id,
        project_id=project_id,
    )
    execution_scope = normalize_execution_scope(
        payload.execution_scope,
        targets=execution_targets,
        default=default_execution_scope,
    )
    model_snapshot = await resolve_model_snapshot(
        db,
        workspace_id=user.workspace_id,
        user_id=user.id,
        selection=_selection(payload),
    )
    user_settings = await AgentUserSettingsRepository(db).get(
        user.workspace_id,
        user.id,
    )
    custom_instructions = (
        user_settings.custom_instructions if user_settings is not None else ""
    )
    snapshot = await agent_runtime.open_session(
        OpenSessionRequest(
            user_id=user.id,
            workspace_id=user.workspace_id,
            project_id=payload.project_id,
            title=payload.title,
            model=model_snapshot,
            workspace=workspace,
            execution_scope=execution_scope,
            permission_mode=payload.permission_mode,
            workspace_access=payload.workspace_access,
            prompt_snapshot=build_session_prompt_snapshot(
                core_snapshot=default_system_prompt_snapshot(
                    custom_instructions
                ).as_dict(),
                workspace={**workspace, "project": project_id},
            ),
            metadata=payload.metadata,
        )
    )
    return success_response(_dump(snapshot), request=request, status_code=201)


@router.get(
    "/sessions",
    response_model=SuccessEnvelope[list[AgentSessionSummary]],
)
async def list_sessions(
    request: Request,
    include_archived: bool = False,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    sessions = await AgentHarnessRepository(db).list_sessions(
        user_id=user.id,
        workspace_id=user.workspace_id,
        include_archived=include_archived,
    )
    return success_response(
        [
            {
                "id": str(item.id),
                "title": item.title,
                "project_id": str(item.project_id) if item.project_id else None,
                "permission_mode": item.permission_mode,
                "workspace_access": item.workspace_access,
                "status": item.status,
                "created_at": item.created_at.isoformat(),
                "updated_at": item.updated_at.isoformat(),
            }
            for item in sessions
        ],
        request=request,
    )


@router.post(
    "/sessions/{session_id}/attachments",
    status_code=201,
    response_model=SuccessEnvelope[list[AgentAttachmentView]],
)
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
    repository = AgentHarnessRepository(db)
    await _owned_session(repository, session_id=session_id, user=user)
    async with _session_mutation_lock(session_id):
        db.expire_all()
        session = await _mutable_owned_session(
            repository, session_id=session_id, user=user
        )
        service = AgentHarnessAttachmentService(db)
        await service.cleanup_orphans()
        if kind == "folder":
            attachments = [
                await service.ingest_folder(
                    agent_session=session,
                    files=files,
                    relative_paths=relative_paths or [],
                )
            ]
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
            attachments = await service.ingest_files(agent_session=session, files=files)
        else:
            raise BadRequestError("Unsupported attachment kind")
    return success_response(
        [_attachment_data(attachment) for attachment in attachments],
        request=request,
        status_code=201,
    )


@router.get(
    "/attachments/{attachment_id}/preview",
    response_class=Response,
    responses={
        200: {
            "description": "Attachment preview bytes",
            "content": {
                "application/octet-stream": {
                    "schema": {"type": "string", "format": "binary"}
                }
            },
        }
    },
)
async def preview_attachment(
    attachment_id: str,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    path, media_type = await AgentHarnessAttachmentService(db).preview_path(
        attachment_id=attachment_id,
        workspace_id=user.workspace_id,
        user_id=user.id,
    )
    return FileResponse(path, media_type=media_type)


@router.delete(
    "/attachments/{attachment_id}",
    response_model=SuccessEnvelope[DeletedResource],
)
async def delete_attachment(
    attachment_id: str,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await AgentHarnessAttachmentService(db).delete(
        attachment_id=attachment_id,
        workspace_id=user.workspace_id,
        user_id=user.id,
    )
    return success_response({"deleted": True}, request=request)


@router.patch(
    "/sessions/{session_id}",
    response_model=SuccessEnvelope[SessionSnapshot],
)
async def update_session(
    session_id: str,
    payload: AgentSessionUpdate,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    repository = AgentHarnessRepository(db)
    await _owned_session(repository, session_id=session_id, user=user)
    async with _session_mutation_lock(session_id):
        db.expire_all()
        await _owned_session(repository, session_id=session_id, user=user)
        values = {
            field_name: getattr(payload, field_name)
            for field_name in payload.model_fields_set
        }
        try:
            await repository.update_session_settings(session_id, **values)
        except ValueError as exc:
            raise ConflictError(str(exc)) from exc
        snapshot = await repository.snapshot(session_id)
        await agent_runtime.publish_snapshot(session_id, snapshot)
    return success_response(_dump(snapshot), request=request)


@router.get(
    "/sessions/{session_id}/snapshot",
    response_model=SuccessEnvelope[SessionSnapshot],
)
async def get_snapshot(
    session_id: str,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    repository = AgentHarnessRepository(db)
    await _owned_session(repository, session_id=session_id, user=user)
    return success_response(
        _dump(await repository.snapshot(session_id)), request=request
    )


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
    await _owned_session(repository, session_id=session_id, user=user)
    async with _session_mutation_lock(session_id):
        db.expire_all()
        agent_session = await _mutable_owned_session(
            repository, session_id=session_id, user=user
        )
        command = payload
        await _authorize_command_parts(
            db,
            session_id=str(agent_session.id),
            project_id=(
                str(agent_session.project_id) if agent_session.project_id else None
            ),
            command=command,
            user=user,
        )
        run_settings_snapshot = None
        if isinstance(command, MessageCommand):
            run_settings_snapshot = await _message_run_settings_snapshot(
                db,
                user=user,
                session=agent_session,
                command=command,
            )
            await repository.update_session_settings(
                session_id,
                model_snapshot=run_settings_snapshot["model_snapshot"],
                permission_mode=run_settings_snapshot["permission_mode"],
                execution_scope=run_settings_snapshot["execution_scope"],
            )
            command = command.model_copy(update={"run_settings": None})
        try:
            await agent_runtime.dispatch(
                session_id,
                command,
                run_settings_snapshot=run_settings_snapshot,
            )
        except ValueError as exc:
            raise ConflictError(str(exc)) from exc
        return success_response(
            _dump(await agent_runtime.snapshot(session_id)),
            request=request,
            status_code=202,
        )


@router.delete(
    "/sessions/{session_id}",
    status_code=204,
    response_class=Response,
)
async def delete_session(
    session_id: str,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    repository = AgentHarnessRepository(db)
    await _owned_session(repository, session_id=session_id, user=user)
    async with _session_mutation_lock(session_id):
        db.expire_all()
        await _owned_session(repository, session_id=session_id, user=user)
        try:
            await agent_runtime.quiesce_session(session_id)
        except TimeoutError as exc:
            raise ConflictError(
                "Agent session is still stopping; retry deletion later"
            ) from exc
        tombstone = stage_agent_session_files_for_delete(session_id)
        try:
            await agent_runtime.delete_session(session_id)
        except Exception:
            await db.rollback()
            db.expire_all()
            if await repository.get_session(session_id) is None:
                tombstone.purge()
            else:
                tombstone.restore()
            raise
        tombstone.purge_deleted_session_files()
        return success_response({}, request=request, status_code=204)


@router.get(
    "/sessions/{session_id}/events",
    response_class=_AgentEventStreamResponse,
    responses={
        200: {
            "description": "Server-sent Agent Harness events",
            "content": {"text/event-stream": {"schema": _agent_event_stream_schema}},
        }
    },
)
async def stream_events(
    session_id: str,
    user: AuthUser = Depends(get_current_user_for_stream, scope="function"),
    db: AsyncSession = Depends(get_db, scope="function"),
):
    repository = AgentHarnessRepository(db)
    await _owned_session(repository, session_id=session_id, user=user)

    async def generate():
        async for event in agent_runtime.events(session_id):
            payload = json.dumps(
                _dump(event), ensure_ascii=False, separators=(",", ":")
            )
            yield f"event: {event.type}\ndata: {payload}\n\n"

    return _AgentEventStreamResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get(
    "/sessions/{session_id}/artifacts",
    response_model=SuccessEnvelope[list[AgentArtifactView]],
)
async def list_session_artifacts(
    session_id: str,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    artifacts = await AgentHarnessArtifactService(db).list_for_session(
        session_id=session_id,
        workspace_id=user.workspace_id,
        user_id=user.id,
    )
    return success_response(
        [_artifact_data(artifact) for artifact in artifacts],
        request=request,
    )


@router.get(
    "/artifacts/{artifact_id}",
    response_model=SuccessEnvelope[AgentArtifactView],
)
async def get_artifact(
    artifact_id: str,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    artifact = await AgentHarnessArtifactService(db).get(
        artifact_id=artifact_id,
        workspace_id=user.workspace_id,
        user_id=user.id,
    )
    return success_response(_artifact_data(artifact), request=request)


@router.get(
    "/artifacts/{artifact_id}/download",
    response_class=Response,
    responses={
        200: {
            "description": "Artifact download bytes",
            "content": {
                "application/octet-stream": {
                    "schema": {"type": "string", "format": "binary"}
                }
            },
        }
    },
)
async def download_artifact(
    artifact_id: str,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    path, filename, media_type = await AgentHarnessArtifactService(db).download_path(
        artifact_id=artifact_id,
        workspace_id=user.workspace_id,
        user_id=user.id,
    )
    return FileResponse(path, media_type=media_type, filename=filename)


__all__ = ["resolve_model_snapshot", "router"]
