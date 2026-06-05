from __future__ import annotations

import json
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.auth.session import AuthUser
from app.schemas.agent_core import (
    AgentActionDecisionRequest,
    AgentActionRead,
    AgentArtifactRead,
    AgentEventRead,
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
from app.utils.responses import success_response


router = APIRouter(prefix="/agent", tags=["agent"])


def _dump(model) -> dict:
    return model.model_dump(mode="json")


def _session_read(session) -> AgentSessionRead:
    return AgentSessionRead.model_validate(session)


def _turn_read(turn) -> AgentTurnRead:
    return AgentTurnRead.model_validate(turn)


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
        project_id=str(payload.project_id),
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
        metadata=payload.metadata,
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
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = AgentCoreService(db)
    sessions, pagination = await service.list_sessions(
        workspace_id=user.workspace_id,
        user_id=user.id,
        project_id=project_id,
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
        updates=payload.model_dump(exclude_unset=True),
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
    session_id: str,
    after_seq: int = Query(default=0, ge=0),
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = AgentCoreService(db)
    events = await service.list_events_for_session(
        session_id=session_id,
        workspace_id=user.workspace_id,
        user_id=user.id,
        after_seq=after_seq,
    )

    async def event_generator() -> AsyncGenerator[str, None]:
        for event in events:
            payload = _dump(_event_read(event))
            yield f"id: {payload['id']}\n"
            yield f"event: {payload['type']}\n"
            yield f"data: {json.dumps(payload, separators=(',', ':'))}\n\n"
        yield "event: ready\n"
        yield 'data: {"status":"replayed"}\n\n'

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
