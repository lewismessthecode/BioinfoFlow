from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.auth.session import AuthUser
from app.config import settings
from app.enums import ApprovalStatus
from app.repositories.conversation_repo import ConversationRepository
from app.schemas.agent import (
    AgentConversationCreate,
    AgentConversationHistory,
    AgentConversationMove,
    AgentConversationRead,
    AgentConversationUpdate,
    AgentMessage,
    AgentMessageRead,
    AgentMessageResponse,
    AgentTraceRead,
    AgentTraceResponse,
    ApprovalAction,
    ApprovalListResponse,
    ApprovalRead,
    ApprovalResolveRequest,
    ApprovalResolveResponse,
)
from app.models.conversation import ConversationStorageBackend
from app.services.agent.agent_service import AgentService
from app.services.agent.approval_service import ApprovalService
from app.services.agent.trace_service import AgentTraceService
from app.services.hermes_service.service import HermesConversationService
from app.services.project_service import ProjectService
from app.utils.exceptions import BadRequestError, NotFoundError
from app.utils.rate_limit import agent_rate_limiter
from app.utils.responses import error_response, success_response


router = APIRouter(prefix="/agent", tags=["agent"])


def _serialize_conversation(conversation) -> dict:
    return AgentConversationRead.model_validate(
        conversation, from_attributes=True
    ).model_dump(mode="json", by_alias=True)


def _serialize_message(message) -> AgentMessageRead:
    payload = {
        "id": message.id,
        "role": message.role,
        "type": message.type,
        "content": message.content,
        "metadata": message.message_metadata,
        "created_at": message.created_at,
    }
    return AgentMessageRead.model_validate(payload)


async def _get_conversation_backend(
    db: AsyncSession, conversation_id: str | None
) -> str | None:
    if not conversation_id:
        return None
    conversation = await ConversationRepository(db).get(conversation_id)
    if conversation is None:
        return None
    return getattr(conversation, "storage_backend", ConversationStorageBackend.LEGACY)


def _should_use_hermes(*, conversation_backend: str | None = None) -> bool:
    return conversation_backend == ConversationStorageBackend.HERMES or (
        conversation_backend is None and settings.agent_engine == "hermes_service"
    )


@router.post("/message")
async def send_message(
    payload: AgentMessage,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    allowed, retry_after = agent_rate_limiter.allow(user.id)
    if not allowed:
        response = error_response(
            code="RATE_LIMITED",
            message=f"Rate limited. Try again in {retry_after:.0f}s.",
            status_code=429,
            request=request,
        )
        response.headers["Retry-After"] = str(int(retry_after))
        return response

    conversation_backend = await _get_conversation_backend(db, payload.conversation_id)
    if _should_use_hermes(conversation_backend=conversation_backend):
        service = HermesConversationService(db)
        result = await service.send_message(
            project_id=payload.project_id,
            content=payload.content,
            user_id=user.id,
            workspace_id=user.workspace_id,
            conversation_id=payload.conversation_id,
            model_override=payload.model,
            execution_policy=payload.execution_policy,
        )
        await db.close()
        response = AgentMessageResponse(
            message_id=None,
            conversation_id=result["conversation_id"],
            response_id=result["response_id"],
            status=result["status"],
        )
    else:
        service = AgentService(db)
        user_message, conversation = await service.send_message(
            project_id=payload.project_id,
            content=payload.content,
            user_id=user.id,
            workspace_id=user.workspace_id,
            conversation_id=payload.conversation_id,
            message_type=payload.type.value,
            model_override=payload.model,
            execution_policy=payload.execution_policy,
        )
        await db.close()
        response = AgentMessageResponse(
            message_id=user_message.id,
            conversation_id=conversation.id,
            status="processing",
        )
    return success_response(
        response.model_dump(mode="json", by_alias=True),
        request=request,
        status_code=202,
    )


@router.post("/conversations/{conversation_id}/cancel")
async def cancel_conversation(
    conversation_id: str,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Cancel a running agent conversation."""
    conversation_backend = await _get_conversation_backend(db, conversation_id)
    if conversation_backend == ConversationStorageBackend.HERMES:
        service = HermesConversationService(db)
        cancelled = await service.cancel_conversation(
            conversation_id=conversation_id,
            user_id=user.id,
            workspace_id=user.workspace_id,
        )
    else:
        service = AgentService(db)
        cancelled = await service.cancel_conversation(
            conversation_id=conversation_id,
            user_id=user.id,
            workspace_id=user.workspace_id,
        )
        cancelled = {
            "conversation_id": conversation_id,
            "cancelled": cancelled,
        }
    return success_response(
        cancelled,
        request=request,
    )


@router.get("/conversations/{conversation_id}/status")
async def get_conversation_status(
    conversation_id: str,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Check if a conversation is currently running."""
    conversation_backend = await _get_conversation_backend(db, conversation_id)
    if conversation_backend == ConversationStorageBackend.HERMES:
        service = HermesConversationService(db)
        status = await service.get_conversation_status(
            conversation_id,
            user_id=user.id,
            workspace_id=user.workspace_id,
        )
    else:
        service = AgentService(db)
        status = await service.get_conversation_status(
            conversation_id,
            user_id=user.id,
            workspace_id=user.workspace_id,
        )
    return success_response(status, request=request)


@router.post("/conversations")
async def create_conversation(
    payload: AgentConversationCreate,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    project_id = str(payload.project_id) if payload.project_id else None
    if project_id is None:
        project = await ProjectService(db).get_or_create_default(
            workspace_id=user.workspace_id,
            workspace_slug="bioinfoflow-team",
            user_id=user.id,
        )
        project_id = str(project.id)
    if settings.agent_engine == "hermes_service":
        conversation = await HermesConversationService(db).create_conversation(
            project_id=project_id,
            user_id=user.id,
            workspace_id=user.workspace_id,
            title=payload.title,
            execution_policy=payload.execution_policy,
        )
    else:
        conversation = await AgentService(db).create_conversation(
            project_id=project_id,
            user_id=user.id,
            workspace_id=user.workspace_id,
            title=payload.title,
            execution_policy=payload.execution_policy,
        )
    return success_response(
        _serialize_conversation(conversation), request=request, status_code=201
    )


@router.patch("/conversations/{conversation_id}")
async def update_conversation(
    conversation_id: str,
    payload: AgentConversationUpdate,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = AgentService(db)
    conversation = await service.update_conversation(
        conversation_id=conversation_id,
        user_id=user.id,
        workspace_id=user.workspace_id,
        title=payload.title,
        pinned=payload.pinned,
        execution_policy=payload.execution_policy,
    )
    return success_response(_serialize_conversation(conversation), request=request)


@router.patch("/conversations/{conversation_id}/move")
async def move_conversation(
    conversation_id: str,
    payload: AgentConversationMove,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Move a conversation to a different project."""
    service = AgentService(db)
    conversation = await service.move_conversation(
        conversation_id=conversation_id,
        target_project_id=str(payload.target_project_id),
        user_id=user.id,
        workspace_id=user.workspace_id,
    )
    return success_response(_serialize_conversation(conversation), request=request)


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = AgentService(db)
    await service.delete_conversation(
        conversation_id=conversation_id,
        user_id=user.id,
        workspace_id=user.workspace_id,
        user_role=user.role,
    )
    return success_response(None, request=request, status_code=204)


@router.get("/conversations/{conversation_id}/trace")
async def get_trace(
    conversation_id: str,
    request: Request,
    message_id: str | None = None,
    include_prompt: bool = False,
    limit: int = 200,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await AgentService(db)._require_conversation(
        conversation_id,
        user_id=user.id,
        workspace_id=user.workspace_id,
    )
    service = AgentTraceService(db)
    events = await service.list_trace(
        conversation_id=conversation_id,
        message_id=message_id,
        include_prompt=include_prompt,
        limit=limit,
    )
    payload = AgentTraceResponse(
        conversation_id=conversation_id,
        events=[
            AgentTraceRead.model_validate(event, from_attributes=True)
            for event in events
        ],
    )
    return success_response(
        payload.model_dump(mode="json", by_alias=True), request=request
    )


@router.get("/conversations")
async def list_conversations(
    request: Request,
    project_id: str | None = None,
    limit: int = 20,
    cursor: str | None = None,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = AgentService(db)
    conversations, pagination = await service.list_conversations(
        user_id=user.id,
        workspace_id=user.workspace_id,
        project_id=project_id,
        limit=limit,
        cursor=cursor,
    )
    data = [_serialize_conversation(item) for item in conversations]
    return success_response(data, request=request, pagination=pagination)


@router.get("/conversations/{conversation_id}")
async def get_conversation_history(
    conversation_id: str,
    request: Request,
    limit: int = 50,
    before: str | None = None,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    conversation_backend = await _get_conversation_backend(db, conversation_id)
    if conversation_backend == ConversationStorageBackend.HERMES:
        payload = await HermesConversationService(db).get_conversation_history(
            conversation_id=conversation_id,
            user_id=user.id,
            workspace_id=user.workspace_id,
            limit=limit,
            before=before,
        )
    else:
        service = AgentService(db)
        conversation, messages = await service.get_conversation_history(
            conversation_id=conversation_id,
            user_id=user.id,
            workspace_id=user.workspace_id,
            limit=limit,
            before=before,
        )
        payload = AgentConversationHistory(
            conversation_id=conversation.id,
            project_id=conversation.project_id,
            title=conversation.title,
            pinned=conversation.pinned,
            storage_backend=getattr(conversation, "storage_backend", None),
            execution_policy=getattr(conversation, "execution_policy", None),
            messages=[_serialize_message(msg) for msg in messages],
        )
    return success_response(
        payload.model_dump(mode="json", by_alias=True), request=request
    )


# ========== Approval endpoints ==========


def _serialize_approval(approval) -> dict:
    """Serialize an approval model to a dictionary."""
    if hasattr(approval, "call_id") and not hasattr(approval, "step_id"):
        payload = approval.payload or {}
        return ApprovalRead.model_validate(
            {
                "id": approval.id,
                "conversation_id": approval.conversation_id,
                "step_id": payload.get("step_id") or approval.call_id,
                "approval_type": payload.get("approval_type") or "clarify",
                "payload": payload,
                "status": approval.status,
                "resolved_by": approval.resolved_by,
                "resolved_at": approval.resolved_at,
                "created_at": approval.created_at,
                "updated_at": approval.updated_at,
            }
        ).model_dump(mode="json", by_alias=True)
    return ApprovalRead.model_validate(approval, from_attributes=True).model_dump(
        mode="json", by_alias=True
    )


async def _require_conversation_accessed(
    db: AsyncSession, conversation_id: str, user: AuthUser
):
    return await AgentService(db)._require_conversation(
        conversation_id,
        user_id=user.id,
        workspace_id=user.workspace_id,
    )


@router.post("/approvals/{approval_id}/resolve")
async def resolve_approval(
    approval_id: str,
    payload: ApprovalResolveRequest,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Resolve an approval request (approve or reject).

    Args:
        approval_id: The approval ID to resolve
        payload: Action to take (approve or reject)
    """
    action = "approve" if payload.action == ApprovalAction.APPROVE else "reject"
    hermes_service = HermesConversationService(db)
    try:
        resolved_payload = await hermes_service.resolve_approval(
            approval_id,
            action=action,
            user_id=user.id,
            workspace_id=user.workspace_id,
        )
        response = ApprovalResolveResponse(
            approval_id=resolved_payload["approval_id"],
            status=resolved_payload["status"],
            resolved_at=resolved_payload["resolved_at"],
        )
    except NotFoundError:
        service = ApprovalService(db)

        approval = await service.get(approval_id)
        if approval is None:
            raise NotFoundError(f"Approval not found: {approval_id}")

        # Enforce workspace/user ownership on the legacy fallback —
        # otherwise any authenticated user could resolve any approval by ID.
        agent_service = AgentService(db)
        await agent_service._require_conversation(
            str(approval.conversation_id),
            user_id=user.id,
            workspace_id=user.workspace_id,
        )

        if approval.status != ApprovalStatus.PENDING:
            raise BadRequestError(
                f"Approval already resolved with status: {approval.status}"
            )

        resolved = await service.resolve(
            approval_id,
            action=action,
            resolved_by=user.id,
        )

        response = ApprovalResolveResponse(
            approval_id=resolved.id,
            status=resolved.status,
            resolved_at=resolved.resolved_at,
        )

    return success_response(
        response.model_dump(mode="json", by_alias=True),
        request=request,
    )


@router.get("/approvals/{approval_id}")
async def get_approval(
    approval_id: str,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get an approval by ID."""
    hermes_service = HermesConversationService(db)
    try:
        approval = await hermes_service.get_approval(
            approval_id,
            user_id=user.id,
            workspace_id=user.workspace_id,
        )
    except NotFoundError:
        service = ApprovalService(db)
        approval = await service.get(approval_id)
        if approval is None:
            raise NotFoundError(f"Approval not found: {approval_id}")

        # Same ownership check as the resolve fallback — don't leak approvals
        # across workspaces through the legacy lookup path.
        agent_service = AgentService(db)
        await agent_service._require_conversation(
            str(approval.conversation_id),
            user_id=user.id,
            workspace_id=user.workspace_id,
        )

    return success_response(_serialize_approval(approval), request=request)


@router.get("/conversations/{conversation_id}/approvals")
async def list_conversation_approvals(
    conversation_id: str,
    request: Request,
    limit: int = 50,
    cursor: str | None = None,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all approvals for a conversation."""
    conversation_backend = await _get_conversation_backend(db, conversation_id)
    if conversation_backend == ConversationStorageBackend.HERMES:
        service = HermesConversationService(db)
        approvals, pagination = await service.list_approvals(
            conversation_id=conversation_id,
            user_id=user.id,
            workspace_id=user.workspace_id,
            limit=limit,
            cursor=cursor,
        )
    else:
        await _require_conversation_accessed(db, conversation_id, user)
        service = ApprovalService(db)
        approvals, pagination = await service.list_for_conversation(
            conversation_id,
            limit=limit,
            cursor=cursor,
        )

    response = ApprovalListResponse(
        conversation_id=conversation_id,
        approvals=[
            ApprovalRead.model_validate(_serialize_approval(a)) for a in approvals
        ],
    )

    return success_response(
        response.model_dump(mode="json", by_alias=True),
        request=request,
        pagination=pagination,
    )


@router.get("/conversations/{conversation_id}/approvals/pending")
async def list_pending_approvals(
    conversation_id: str,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all pending approvals for a conversation."""
    conversation_backend = await _get_conversation_backend(db, conversation_id)
    if conversation_backend == ConversationStorageBackend.HERMES:
        service = HermesConversationService(db)
        approvals = await service.list_pending_approvals(
            conversation_id=conversation_id,
            user_id=user.id,
            workspace_id=user.workspace_id,
        )
    else:
        await _require_conversation_accessed(db, conversation_id, user)
        service = ApprovalService(db)
        approvals = await service.get_pending_for_conversation(conversation_id)

    response = ApprovalListResponse(
        conversation_id=conversation_id,
        approvals=[
            ApprovalRead.model_validate(_serialize_approval(a)) for a in approvals
        ],
    )

    return success_response(
        response.model_dump(mode="json", by_alias=True),
        request=request,
    )
