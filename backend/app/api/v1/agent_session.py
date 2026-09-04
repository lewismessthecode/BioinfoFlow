from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_current_user, get_db
from app.api.v1.agent_api_common import (
    dump_model,
    mutable_owned_session,
    owned_session,
    resolve_environment_scope_payload,
)
from app.api.v1.agent_schemas import (
    AgentAttachmentView,
    AgentSessionCreate,
    AgentSessionSummary,
    AgentSessionUpdate,
    DeletedResource,
    attachment_data,
    model_selection,
)
from app.auth.session import AuthUser
from app.repositories.agent_harness_repo import AgentHarnessRepository
from app.repositories.agent_user_settings_repo import AgentUserSettingsRepository
from app.schemas.common import SuccessEnvelope
from app.services.agent_harness.assets import AgentHarnessAttachmentService
from app.services.agent_harness.context import build_session_prompt_snapshot
from app.services.agent_harness.contracts import (
    EnvironmentScope,
    OpenSessionRequest,
    SessionSnapshot,
)
from app.services.agent_harness.snapshot import AgentHarnessSnapshotService
from app.services.agent_harness.session_deletion import delete_agent_session
from app.services.agent_harness.system_prompt import default_system_prompt_snapshot
from app.utils.authorization import can_manage_external_roots
from app.utils.exceptions import BadRequestError, ConflictError
from app.utils.responses import success_response

from app.api.v1 import agent as agent_api


router = APIRouter()


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
    workspace = await agent_api.open_session_request_workspace(
        db,
        project_id=project_id,
        workspace_id=user.workspace_id,
        user_id=user.id,
    )
    model_snapshot = await agent_api.resolve_model_snapshot(
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
    resolved_environment_scope = await resolve_environment_scope_payload(
        db,
        workspace_id=user.workspace_id,
        requested=payload.environment_scope,
        allow_remote=can_manage_external_roots(user.role),
    )
    snapshot = await agent_api.agent_runtime.open_session(
        OpenSessionRequest(
            user_id=user.id,
            workspace_id=user.workspace_id,
            project_id=payload.project_id,
            title=payload.title,
            model=model_snapshot,
            workspace=workspace,
            permission_mode=payload.permission_mode,
            workspace_access=payload.workspace_access,
            environment_scope=EnvironmentScope.model_validate(
                resolved_environment_scope
            ),
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
    return success_response(dump_model(snapshot), request=request, status_code=201)


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
    await owned_session(repository, session_id=session_id, user=user)
    async with agent_api.session_mutation_lock(session_id):
        db.expire_all()
        session = await mutable_owned_session(
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
    await owned_session(repository, session_id=session_id, user=user)
    async with agent_api.session_mutation_lock(session_id):
        db.expire_all()
        await owned_session(repository, session_id=session_id, user=user)
        values = {
            field_name: getattr(payload, field_name)
            for field_name in payload.model_fields_set
        }
        if "environment_scope" in payload.model_fields_set:
            assert payload.environment_scope is not None
            values["environment_scope"] = await resolve_environment_scope_payload(
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
            values["model_snapshot"] = await agent_api.resolve_model_snapshot(
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
        await agent_api.agent_runtime.publish_snapshot(session_id, snapshot)
    return success_response(dump_model(snapshot), request=request)


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
    await owned_session(repository, session_id=session_id, user=user)
    await delete_agent_session(session_id, db=db, runtime=agent_api.agent_runtime)
    return success_response({}, request=request, status_code=204)


__all__ = [
    "create_session",
    "list_sessions",
    "upload_attachments",
    "preview_attachment",
    "delete_attachment",
    "update_session",
    "delete_session",
    "router",
]
