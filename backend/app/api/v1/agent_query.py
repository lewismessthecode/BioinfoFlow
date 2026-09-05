from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import FileResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import get_current_user, get_db
from app.api.v1.agent_api_common import dump_model, owned_session
from app.api.v1.agent_schemas import (
    AgentArtifactView,
    AgentEnvironmentView,
    artifact_data,
)
from app.auth.session import AuthUser
from app.repositories.agent_harness_repo import AgentHarnessRepository
from app.repositories.remote_connection_repo import RemoteConnectionRepository
from app.schemas.common import SuccessEnvelope
from app.services.agent_harness.assets import AgentHarnessArtifactService
from app.services.agent_harness.context_search import (
    AgentContextSearch,
    ContextSearchResult,
)
from app.services.agent_harness.contracts import SessionSnapshot
from app.services.agent_harness.environment_catalog import EnvironmentCatalog
from app.services.agent_harness.snapshot import AgentHarnessSnapshotService
from app.services.agent_trace.adapter import CompleteHarnessTraceAdapter
from app.services.agent_trace.contracts import AgentTraceEventDetail, AgentTraceTimeline
from app.utils.authorization import can_manage_external_roots
from app.utils.exceptions import NotFoundError
from app.utils.responses import success_response


router = APIRouter()


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
    await owned_session(repository, session_id=session_id, user=user)
    return success_response(
        dump_model(await AgentHarnessSnapshotService(repository).build(session_id)),
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
    await owned_session(repository, session_id=session_id, user=user)
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
    await owned_session(repository, session_id=session_id, user=user)
    detail = await CompleteHarnessTraceAdapter(db).detail(session_id, event_id)
    if detail is None:
        raise NotFoundError(f"Agent trace event not found: {event_id}")
    return success_response(
        detail.model_dump(mode="json", by_alias=True),
        request=request,
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


__all__ = [
    "search_context",
    "list_agent_environments",
    "get_snapshot",
    "get_trace",
    "get_trace_event_detail",
    "list_session_artifacts",
    "get_artifact",
    "download_artifact",
    "router",
]
