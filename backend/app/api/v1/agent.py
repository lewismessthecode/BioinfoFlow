from __future__ import annotations

import json

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse
from pydantic import TypeAdapter
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_current_user_for_stream, get_db
from app.auth.session import AuthUser
from app.repositories.agent_harness_repo import AgentHarnessRepository
from app.repositories.agent_user_settings_repo import AgentUserSettingsRepository
from app.repositories.remote_connection_repo import RemoteConnectionRepository
from app.services.agent_harness.assets import (
    AgentHarnessArtifactService,
    AgentHarnessAttachmentService,
)
from app.services.agent_harness.contracts import (
    AgentCommand,
    AgentEvent,
    EnvironmentScope,
    OpenSessionRequest,
    SessionSnapshot,
)
from app.services.agent_harness.command_authorization import authorize_command_parts
from app.services.agent_harness.context import build_session_prompt_snapshot
from app.services.agent_harness.context_search import (
    AgentContextSearch,
    ContextSearchResult,
)
from app.services.agent_harness.factory import (
    open_session_request_workspace,
    resolve_model_snapshot,
)
from app.services.agent_harness.environment_catalog import EnvironmentCatalog
from app.services.agent_harness.environment_scope import (
    EnvironmentScopeRequest,
    EnvironmentSelectionError,
    resolve_environment_scope,
)
from app.services.agent_harness.runtime import agent_runtime
from app.services.agent_harness.session_deletion import (
    delete_agent_session,
    session_mutation_lock,
)
from app.services.agent_harness.snapshot import AgentHarnessSnapshotService
from app.services.agent_harness.system_prompt import default_system_prompt_snapshot
from app.services.agent_trace.adapter import CompleteHarnessTraceAdapter
from app.services.agent_trace.contracts import (
    AgentTraceEventDetail,
    AgentTraceTimeline,
)
from app.api.v1.agent_schemas import (
    AgentArtifactView,
    AgentAttachmentView,
    AgentEnvironmentView,
    AgentSessionCreate,
    AgentSessionSummary,
    AgentSessionUpdate,
    AgentSettingsRead,
    AgentSettingsUpdate,
    DeletedResource,
    artifact_data,
    attachment_data,
    model_selection,
)
from app.schemas.common import SuccessEnvelope
from app.utils.exceptions import BadRequestError, ConflictError, NotFoundError
from app.utils.authorization import can_manage_external_roots
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


async def _environment_scope(
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
    return {
        "mode": "manual",
        "environment_ids": list(resolved.environment_ids),
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


@router.get(
    "/environments",
    response_model=SuccessEnvelope[list[AgentEnvironmentView]],
)
async def list_agent_environments(
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    environments = await EnvironmentCatalog(
        RemoteConnectionRepository(db)
    ).list_authorized(
        workspace_id=user.workspace_id,
        allow_remote=can_manage_external_roots(user.role),
    )
    return success_response(
        [
            {
                "id": environment.environment_id,
                "kind": environment.kind,
                "label": environment.display_name,
                "description": environment.description,
                "status": environment.status,
            }
            for environment in environments
        ],
        request=request,
    )


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
    model_snapshot = await resolve_model_snapshot(
        db,
        workspace_id=user.workspace_id,
        user_id=user.id,
        selection=model_selection(payload),
    )
    user_settings = await AgentUserSettingsRepository(db).get(
        user.workspace_id,
        user.id,
    )
    custom_instructions = (
        user_settings.custom_instructions if user_settings is not None else ""
    )
    environment_scope = await _environment_scope(
        db,
        workspace_id=user.workspace_id,
        requested=payload.environment_scope,
        allow_remote=can_manage_external_roots(user.role),
    )
    snapshot = await agent_runtime.open_session(
        OpenSessionRequest(
            user_id=user.id,
            workspace_id=user.workspace_id,
            project_id=payload.project_id,
            title=payload.title,
            model=model_snapshot,
            workspace=workspace,
            permission_mode=payload.permission_mode,
            workspace_access=payload.workspace_access,
            environment_scope=EnvironmentScope.model_validate(environment_scope),
            prompt_snapshot=build_session_prompt_snapshot(
                core_snapshot=default_system_prompt_snapshot(
                    custom_instructions
                ).as_dict(),
                workspace={**workspace, "project": project_id},
            ),
            metadata={
                **(payload.metadata or {}),
                "_allow_remote_environments": can_manage_external_roots(user.role),
            },
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
    async with session_mutation_lock(session_id):
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
        [attachment_data(attachment) for attachment in attachments],
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
    async with session_mutation_lock(session_id):
        db.expire_all()
        await _owned_session(repository, session_id=session_id, user=user)
        values = {
            field_name: getattr(payload, field_name)
            for field_name in payload.model_fields_set
        }
        if "environment_scope" in payload.model_fields_set:
            assert payload.environment_scope is not None
            values["environment_scope"] = await _environment_scope(
                db,
                workspace_id=user.workspace_id,
                requested=payload.environment_scope,
                allow_remote=can_manage_external_roots(user.role),
            )
        selector_fields = {"model_id", "profile_id", "provider", "model"}
        if selector_fields & payload.model_fields_set:
            values = {
                key: value
                for key, value in values.items()
                if key not in selector_fields
            }
            values["model_snapshot"] = await resolve_model_snapshot(
                db,
                workspace_id=user.workspace_id,
                user_id=user.id,
                selection=model_selection(payload),
            )
        try:
            await repository.update_session_settings(session_id, **values)
        except ValueError as exc:
            raise ConflictError(str(exc)) from exc
        snapshot = await AgentHarnessSnapshotService(repository).build(session_id)
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
        _dump(await AgentHarnessSnapshotService(repository).build(session_id)),
        request=request,
    )


@router.get(
    "/sessions/{session_id}/trace",
    response_model=SuccessEnvelope[AgentTraceTimeline],
)
async def get_trace(
    session_id: str,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    repository = AgentHarnessRepository(db)
    await _owned_session(repository, session_id=session_id, user=user)
    timeline = await CompleteHarnessTraceAdapter(db).timeline(session_id)
    return success_response(
        timeline.model_dump(mode="json", by_alias=True),
        request=request,
    )


@router.get(
    "/sessions/{session_id}/trace/events/{event_id}",
    response_model=SuccessEnvelope[AgentTraceEventDetail],
)
async def get_trace_event_detail(
    session_id: str,
    event_id: str,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    repository = AgentHarnessRepository(db)
    await _owned_session(repository, session_id=session_id, user=user)
    detail = await CompleteHarnessTraceAdapter(db).detail(session_id, event_id)
    if detail is None:
        raise NotFoundError(f"Agent trace event not found: {event_id}")
    return success_response(
        detail.model_dump(mode="json", by_alias=True),
        request=request,
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
    async with session_mutation_lock(session_id):
        db.expire_all()
        agent_session = await _mutable_owned_session(
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
            await agent_runtime.dispatch(session_id, command)
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
    await delete_agent_session(session_id, db=db, runtime=agent_runtime)
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
        [artifact_data(artifact) for artifact in artifacts],
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
    return success_response(artifact_data(artifact), request=request)


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
