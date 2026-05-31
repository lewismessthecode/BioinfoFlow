from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from uuid import NAMESPACE_URL, uuid4, uuid5

import app.database as app_database
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import settings
from app.models.agent_approval_handle import AgentApprovalHandleStatus
from app.models.agent_response_handle import AgentResponseStatus
from app.models.conversation import Conversation, ConversationStorageBackend
from app.repositories.agent_approval_handle_repo import AgentApprovalHandleRepository
from app.repositories.agent_response_handle_repo import AgentResponseHandleRepository
from app.repositories.conversation_repo import ConversationRepository
from app.repositories.project_repo import ProjectRepository
from app.runtime.events import publish_event
from app.schemas.agent import (
    AgentConversationHistory,
    AgentMessageRead,
    AgentMessageRole,
    AgentMessageType,
)
from app.services.hermes_service.home import ensure_hermes_home_environment
from app.services.hermes_service.registry import hermes_response_registry
from app.services.hermes_service.runner import HermesRunResult, HermesRunner
from app.services.hermes_service.session_store import get_hermes_session_store
from app.services.hermes_service.tool_bridge import HermesToolRuntimeContext
from app.utils.exceptions import ConflictError, NotFoundError, PermissionDeniedError
from app.utils.logging import get_logger
from app.utils.authorization import can_access_workspace_resource

logger = get_logger(__name__)


async def reconcile_stale_hermes_responses(
    session,
    *,
    stale_before: datetime,
) -> int:
    response_repo = AgentResponseHandleRepository(session)
    responses = await response_repo.list_stale_in_flight(stale_before)

    updated = 0
    for response in responses:
        if await hermes_response_registry.get(str(response.id)) is not None:
            continue
        response.status = AgentResponseStatus.ERROR
        response.error_message = "backend_restart"
        response.completed_at = datetime.now(timezone.utc)
        updated += 1

    if updated:
        await session.commit()
        logger.warning("hermes.responses.reconciled", count=updated)

    return updated


class HermesConversationService:
    def __init__(self, session):
        self.session = session
        self.project_repo = ProjectRepository(session)
        self.conversation_repo = ConversationRepository(session)
        self.response_repo = AgentResponseHandleRepository(session)
        self.approval_repo = AgentApprovalHandleRepository(session)
        ensure_hermes_home_environment(state_db_path=settings.agent_hermes_state_db)
        self.session_store = get_hermes_session_store(settings.agent_hermes_state_db)
        self.runner = HermesRunner()

    async def create_conversation(
        self,
        *,
        project_id: str,
        user_id: str,
        workspace_id: str | None = None,
        title: str | None = None,
        execution_policy: str | None = None,
    ) -> Conversation:
        project = await self._require_project_access(
            project_id,
            user_id=user_id,
            workspace_id=workspace_id,
        )

        conversation = await self.conversation_repo.create(
            project_id=project_id,
            user_id=user_id,
            created_by_user_id=user_id,
            title=title,
            execution_policy=execution_policy,
            storage_backend=ConversationStorageBackend.HERMES,
            hermes_session_id=str(uuid4()),
            workspace_binding_id=getattr(project, "workspace_id", None),
        )
        return conversation

    async def send_message(
        self,
        *,
        project_id: str,
        content: str,
        user_id: str,
        workspace_id: str | None = None,
        conversation_id: str | None = None,
        model_override: str | None = None,
        execution_policy: str | None = None,
    ) -> dict[str, str | None]:
        if conversation_id is None:
            conversation = await self.create_conversation(
                project_id=project_id,
                user_id=user_id,
                workspace_id=workspace_id,
                execution_policy=execution_policy,
            )
        else:
            conversation = await self._require_conversation(
                conversation_id,
                user_id=user_id,
                workspace_id=workspace_id,
            )
            if conversation.storage_backend != ConversationStorageBackend.HERMES:
                raise ConflictError("conversation is not backed by Hermes")

        response = await self.response_repo.create(
            conversation_id=str(conversation.id),
            runtime_instance_id="local-hermes",
            status=AgentResponseStatus.PENDING,
            started_at=datetime.now(timezone.utc),
        )
        response_id = str(response.id)
        await hermes_response_registry.register(
            response_id=response_id,
            conversation_id=str(conversation.id),
            project_id=project_id,
        )

        task = asyncio.create_task(
            self._run_response_task(
                response_id=response_id,
                conversation_id=str(conversation.id),
                project_id=project_id,
                user_id=user_id,
                workspace_id=workspace_id,
                session_id=conversation.hermes_session_id or response_id,
                prompt=content,
                cwd=await self._resolve_workspace_root(project_id),
                model_override=model_override,
            )
        )
        await hermes_response_registry.set_task(response_id, task)

        return {
            "conversation_id": str(conversation.id),
            "response_id": response_id,
            "status": "processing",
        }

    async def get_conversation_history(
        self,
        *,
        conversation_id: str,
        user_id: str,
        workspace_id: str | None = None,
        limit: int = 50,
        before: str | None = None,
    ) -> AgentConversationHistory:
        conversation = await self._require_conversation(
            conversation_id,
            user_id=user_id,
            workspace_id=workspace_id,
        )
        session_id = conversation.hermes_session_id
        if not session_id:
            raise ConflictError("conversation is missing Hermes session binding")

        messages = self.session_store.get_messages(session_id)
        normalized = self._normalize_history(session_id=session_id, rows=messages)
        approval_messages = await self._build_approval_history(
            conversation_id=str(conversation.id)
        )
        normalized = sorted(
            [*normalized, *approval_messages],
            key=lambda message: (message.created_at, str(message.id)),
        )

        if before:
            before_idx = next(
                (
                    idx
                    for idx, message in enumerate(normalized)
                    if str(message.id) == before
                ),
                None,
            )
            if before_idx is not None:
                normalized = normalized[:before_idx]

        normalized = normalized[-limit:]
        return AgentConversationHistory(
            conversation_id=conversation.id,
            project_id=conversation.project_id,
            title=conversation.title,
            pinned=conversation.pinned,
            storage_backend=conversation.storage_backend,
            execution_policy=getattr(conversation, "execution_policy", None),
            messages=normalized,
        )

    async def get_conversation_status(
        self,
        conversation_id: str,
        *,
        user_id: str,
        workspace_id: str | None = None,
    ) -> dict[str, str | bool | None]:
        conversation = await self._require_conversation(
            conversation_id,
            user_id=user_id,
            workspace_id=workspace_id,
        )
        response = await self.response_repo.get_latest_for_conversation(
            str(conversation.id)
        )
        running = False
        if response is not None and response.status in {
            AgentResponseStatus.PENDING,
            AgentResponseStatus.RUNNING,
        }:
            running = True
        return {
            "conversation_id": conversation_id,
            "is_running": running,
            "assistant_message_id": None,
            "response_id": str(response.id) if response else None,
            "last_event_at": response.updated_at.isoformat() if response else None,
        }

    async def cancel_conversation(
        self,
        *,
        conversation_id: str,
        user_id: str,
        workspace_id: str | None = None,
    ) -> dict[str, str | bool | None]:
        conversation = await self._require_conversation(
            conversation_id,
            user_id=user_id,
            workspace_id=workspace_id,
        )
        response = await self.response_repo.get_latest_for_conversation(
            str(conversation.id)
        )
        if response is None:
            return {
                "conversation_id": conversation_id,
                "response_id": None,
                "cancelled": False,
            }

        cancelled = await hermes_response_registry.cancel(str(response.id))
        if cancelled and response.status not in {
            AgentResponseStatus.COMPLETED,
            AgentResponseStatus.ERROR,
        }:
            await self.response_repo.update(
                response,
                status=AgentResponseStatus.CANCELLED,
                completed_at=datetime.now(timezone.utc),
            )
        return {
            "conversation_id": conversation_id,
            "response_id": str(response.id),
            "cancelled": cancelled,
        }

    async def resolve_approval(
        self,
        approval_id: str,
        *,
        action: str,
        user_id: str,
        workspace_id: str | None = None,
    ) -> dict[str, str | datetime | None]:
        approval = await self.approval_repo.get(approval_id)
        if approval is None:
            raise NotFoundError(f"Approval not found: {approval_id}")
        conversation = await self._require_conversation(
            str(approval.conversation_id),
            user_id=user_id,
            workspace_id=workspace_id,
        )

        status = (
            AgentApprovalHandleStatus.APPROVED
            if action == "approve"
            else AgentApprovalHandleStatus.REJECTED
        )
        resolved = await self.approval_repo.update(
            approval,
            status=status,
            resolved_by=user_id,
            resolved_at=datetime.now(timezone.utc),
        )
        await publish_event(
            event="agent.approval.resolved",
            project_id=str(conversation.project_id),
            conversation_id=str(conversation.id),
            data={
                "approval_id": str(resolved.id),
                "response_id": str(resolved.response_id),
                "step_id": approval.call_id,
                "status": resolved.status,
                "resolved_by": user_id,
            },
        )
        payload = resolved.payload or {}
        tool_name = str(payload.get("tool") or "clarify")
        status_label = "approved" if action == "approve" else "rejected"
        preview = (
            f"Approval received, resuming {tool_name}"
            if action == "approve"
            else f"Approval denied for {tool_name}"
        )
        await self._publish_tool_progress(
            project_id=str(conversation.project_id),
            conversation_id=str(conversation.id),
            response_id=str(resolved.response_id),
            tool_name=tool_name,
            status=status_label,
            preview=preview,
            approval_id=str(resolved.id),
            approval_type=str(payload.get("approval_type") or "clarify"),
            risk=str(payload.get("risk") or ""),
        )
        return {
            "approval_id": str(resolved.id),
            "status": resolved.status,
            "resolved_at": resolved.resolved_at,
        }

    async def get_approval(
        self,
        approval_id: str,
        *,
        user_id: str,
        workspace_id: str | None = None,
    ):
        approval = await self.approval_repo.get(approval_id)
        if approval is None:
            raise NotFoundError(f"Approval not found: {approval_id}")
        await self._require_conversation(
            str(approval.conversation_id),
            user_id=user_id,
            workspace_id=workspace_id,
        )
        return approval

    async def list_approvals(
        self,
        *,
        conversation_id: str,
        user_id: str,
        workspace_id: str | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ):
        await self._require_conversation(
            conversation_id,
            user_id=user_id,
            workspace_id=workspace_id,
        )
        return await self.approval_repo.list_for_conversation(
            conversation_id,
            limit=limit,
            cursor=cursor,
        )

    async def list_pending_approvals(
        self,
        *,
        conversation_id: str,
        user_id: str,
        workspace_id: str | None = None,
    ):
        await self._require_conversation(
            conversation_id,
            user_id=user_id,
            workspace_id=workspace_id,
        )
        return await self.approval_repo.get_pending_for_conversation(conversation_id)

    async def request_clarification(
        self,
        *,
        response_id: str,
        conversation_id: str,
        project_id: str,
        question: str,
        choices: list[str] | None = None,
        poll_interval: float = 0.25,
        timeout: float = 300.0,
    ) -> str:
        normalized_choices = [
            choice for choice in (choices or []) if isinstance(choice, str) and choice
        ]
        return await self._request_approval(
            response_id=response_id,
            conversation_id=conversation_id,
            project_id=project_id,
            tool_name="clarify",
            tool_input={"question": question, "choices": normalized_choices},
            description=question,
            approval_type="clarify",
            risk="read",
            choices=normalized_choices,
            poll_interval=poll_interval,
            timeout=timeout,
        )

    async def request_tool_approval(
        self,
        *,
        response_id: str,
        conversation_id: str,
        project_id: str,
        tool_name: str,
        tool_input: dict | None,
        risk: str,
        description: str,
        choices: list[str] | None = None,
        poll_interval: float = 0.25,
        timeout: float = 300.0,
    ) -> str:
        normalized_choices = [
            choice
            for choice in (choices or ["once", "deny"])
            if isinstance(choice, str) and choice
        ]
        return await self._request_approval(
            response_id=response_id,
            conversation_id=conversation_id,
            project_id=project_id,
            tool_name=tool_name,
            tool_input=tool_input or {},
            description=description,
            approval_type="tool_risk",
            risk=risk,
            choices=normalized_choices,
            poll_interval=poll_interval,
            timeout=timeout,
        )

    async def _request_approval(
        self,
        *,
        response_id: str,
        conversation_id: str,
        project_id: str,
        tool_name: str,
        tool_input: dict,
        description: str,
        approval_type: str,
        risk: str,
        choices: list[str],
        poll_interval: float,
        timeout: float,
    ) -> str:
        call_id = f"{approval_type}:{uuid4()}"
        approval = await self.approval_repo.create(
            conversation_id=conversation_id,
            response_id=response_id,
            call_id=call_id,
            status=AgentApprovalHandleStatus.PENDING,
            payload={
                "question": description,
                "choices": choices,
                "tool": tool_name,
                "approval_type": approval_type,
                "risk": risk,
                "step_id": call_id,
                "input": tool_input,
            },
        )

        await publish_event(
            event="agent.approval.requested",
            project_id=project_id,
            conversation_id=conversation_id,
            data={
                "approval_id": str(approval.id),
                "response_id": response_id,
                "step_id": call_id,
                "approval_type": approval_type,
                "tool": tool_name,
                "description": description,
                "risk": risk,
                "payload": approval.payload or {},
            },
        )
        await self._publish_tool_progress(
            project_id=project_id,
            conversation_id=conversation_id,
            response_id=response_id,
            tool_name=tool_name,
            status="requires_approval",
            preview=f"Waiting for approval to continue {tool_name}",
            approval_id=str(approval.id),
            approval_type=approval_type,
            risk=risk,
        )

        deadline = asyncio.get_running_loop().time() + timeout
        while asyncio.get_running_loop().time() < deadline:
            registry_entry = await hermes_response_registry.get(response_id)
            if registry_entry and registry_entry.cancelled:
                await self._expire_approval(str(approval.id), reason="cancelled")
                raise RuntimeError("clarification cancelled")

            async with self._new_session() as session:
                repo = AgentApprovalHandleRepository(session)
                current = await repo.get(str(approval.id))
                if current is None:
                    raise NotFoundError(f"Approval not found: {approval.id}")
                if current.status == AgentApprovalHandleStatus.APPROVED:
                    return self._select_approval_choice("approve", choices)
                if current.status == AgentApprovalHandleStatus.REJECTED:
                    return self._select_approval_choice("reject", choices)
                if current.status == AgentApprovalHandleStatus.EXPIRED:
                    raise RuntimeError("approval expired")

            await asyncio.sleep(poll_interval)

        await self._expire_approval(str(approval.id), reason="timeout")
        raise TimeoutError(f"Timed out waiting for approval {approval.id}")

    async def _run_response_task(
        self,
        *,
        response_id: str,
        conversation_id: str,
        project_id: str,
        user_id: str,
        workspace_id: str | None,
        session_id: str,
        prompt: str,
        cwd: str | None,
        model_override: str | None,
    ) -> None:
        async with app_database.async_session_maker() as session:
            response_repo = AgentResponseHandleRepository(session)
            conversation_repo = ConversationRepository(session)
            service = HermesConversationService(session)
            response = await response_repo.get(response_id)
            if response is None:
                return
            await response_repo.update(response, status=AgentResponseStatus.RUNNING)

            sequence = 0
            loop = asyncio.get_running_loop()

            async def on_event(event: dict) -> None:
                nonlocal sequence
                sequence += 1
                await hermes_response_registry.touch(response_id)
                if event["type"] == "text_delta":
                    await publish_event(
                        event="agent.text_delta",
                        project_id=project_id,
                        conversation_id=conversation_id,
                        data={
                            "id": response_id,
                            "type": "text_delta",
                            "content": event.get("content", ""),
                            "metadata": {"response_id": response_id},
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "sequence": sequence,
                            "stream": True,
                        },
                    )
                elif event["type"] == "thinking_delta":
                    await publish_event(
                        event="agent.thinking_delta",
                        project_id=project_id,
                        conversation_id=conversation_id,
                        data={
                            "id": response_id,
                            "type": "thinking_delta",
                            "content": event.get("content", ""),
                            "metadata": {"response_id": response_id},
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "sequence": sequence,
                            "stream": True,
                        },
                    )
                elif event["type"] == "tool_call_start":
                    meta = {"response_id": response_id, **(event.get("metadata") or {})}
                    await publish_event(
                        event="agent.tool_call_start",
                        project_id=project_id,
                        conversation_id=conversation_id,
                        data={
                            "id": response_id,
                            "type": "tool_call_start",
                            "content": meta.get("name", ""),
                            "metadata": meta,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "sequence": sequence,
                            "stream": True,
                        },
                    )
                elif event["type"] == "tool_call_progress":
                    meta = {"response_id": response_id, **(event.get("metadata") or {})}
                    await publish_event(
                        event="agent.tool_call_progress",
                        project_id=project_id,
                        conversation_id=conversation_id,
                        data={
                            "id": response_id,
                            "type": "tool_call_progress",
                            "content": event.get("content", ""),
                            "metadata": meta,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "sequence": sequence,
                            "stream": True,
                        },
                    )
                elif event["type"] == "tool_call_end":
                    meta = {"response_id": response_id, **(event.get("metadata") or {})}
                    await publish_event(
                        event="agent.tool_call_end",
                        project_id=project_id,
                        conversation_id=conversation_id,
                        data={
                            "id": response_id,
                            "type": "tool_call_end",
                            "content": meta.get("name", ""),
                            "metadata": meta,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "sequence": sequence,
                            "stream": True,
                        },
                    )

            def clarify_callback(
                question: str, choices: list[str] | None = None
            ) -> str:
                future = asyncio.run_coroutine_threadsafe(
                    service.request_clarification(
                        response_id=response_id,
                        conversation_id=conversation_id,
                        project_id=project_id,
                        question=question,
                        choices=choices,
                    ),
                    loop,
                )
                return future.result()

            def approval_callback(*args, **kwargs) -> str:
                if args and not kwargs:
                    command = str(args[0]) if len(args) > 0 else ""
                    description = str(args[1]) if len(args) > 1 else command
                    tool_name = "terminal"
                    tool_input = {"command": command}
                else:
                    tool_name = str(
                        kwargs.get("tool_name") or kwargs.get("tool") or "tool"
                    )
                    tool_input = kwargs.get("tool_input") or kwargs.get("input") or {}
                    description = str(
                        kwargs.get("description") or kwargs.get("message") or tool_name
                    )

                risk = str(kwargs.get("risk") or "act_high")
                future = asyncio.run_coroutine_threadsafe(
                    service.request_tool_approval(
                        response_id=response_id,
                        conversation_id=conversation_id,
                        project_id=project_id,
                        tool_name=tool_name,
                        tool_input=tool_input
                        if isinstance(tool_input, dict)
                        else {"value": tool_input},
                        risk=risk,
                        description=description,
                    ),
                    loop,
                )
                return future.result()

            try:
                tool_context = HermesToolRuntimeContext(
                    session_factory=service._session_factory(),
                    project_id=project_id,
                    user_id=user_id,
                    workspace_root=cwd,
                    workspace_id=workspace_id,
                    approval_callback=approval_callback,
                )
                result = await service.runner.run_response(
                    session_id=session_id,
                    prompt=prompt,
                    model=model_override or settings.agent_model,
                    cwd=cwd,
                    session_store=service.session_store,
                    clarify_callback=clarify_callback,
                    approval_callback=approval_callback,
                    tool_context=tool_context,
                    on_event=on_event,
                )
                await self._publish_completion(
                    conversation_id=conversation_id,
                    project_id=project_id,
                    response_id=response_id,
                    result=result,
                )
                response = await response_repo.get(response_id)
                if response is not None:
                    await response_repo.update(
                        response,
                        status=AgentResponseStatus.COMPLETED,
                        completed_at=datetime.now(timezone.utc),
                        last_event_seq=sequence + 1,
                    )
                conversation = await conversation_repo.get(conversation_id)
                if conversation and not conversation.title and prompt.strip():
                    fallback = " ".join(prompt.strip().split())
                    await conversation_repo.update(
                        conversation,
                        title=(fallback[:60] + ("..." if len(fallback) > 60 else "")),
                    )
            except asyncio.CancelledError:
                response = await response_repo.get(response_id)
                if response is not None:
                    await response_repo.update(
                        response,
                        status=AgentResponseStatus.CANCELLED,
                        completed_at=datetime.now(timezone.utc),
                    )
                await publish_event(
                    event="agent.cancelled",
                    project_id=project_id,
                    conversation_id=conversation_id,
                    data={
                        "id": response_id,
                        "response_id": response_id,
                    },
                )
                raise
            except Exception as exc:
                logger.error(
                    "hermes.run_response.error", response_id=response_id, error=str(exc)
                )
                response = await response_repo.get(response_id)
                if response is not None:
                    await response_repo.update(
                        response,
                        status=AgentResponseStatus.ERROR,
                        completed_at=datetime.now(timezone.utc),
                        error_message=str(exc),
                    )
                await publish_event(
                    event="agent.error",
                    project_id=project_id,
                    conversation_id=conversation_id,
                    data={
                        "id": response_id,
                        "type": "error",
                        "content": str(exc),
                        "metadata": {"response_id": response_id},
                    },
                )
            finally:
                await hermes_response_registry.unregister(response_id)

    async def _publish_completion(
        self,
        *,
        conversation_id: str,
        project_id: str,
        response_id: str,
        result: HermesRunResult,
    ) -> None:
        metadata = {
            "response_id": response_id,
            "usage": result.usage,
            "parts": (
                [{"type": "text", "text": result.final_text}]
                if result.final_text
                else []
            ),
        }
        await publish_event(
            event="agent.message",
            project_id=project_id,
            conversation_id=conversation_id,
            data={
                "id": response_id,
                "type": "text",
                "content": result.final_text,
                "metadata": metadata,
            },
        )
        await publish_event(
            event="agent.done",
            project_id=project_id,
            conversation_id=conversation_id,
            data={
                "id": response_id,
                "response_id": response_id,
                "metadata": result.usage,
            },
        )

    async def _require_conversation(
        self,
        conversation_id: str,
        *,
        user_id: str,
        workspace_id: str | None = None,
    ) -> Conversation:
        conversation = await self.conversation_repo.get(conversation_id)
        if conversation is None:
            raise NotFoundError("conversation not found")
        project = await self.project_repo.get(str(conversation.project_id))
        if not can_access_workspace_resource(
            resource_workspace_id=(
                str(getattr(project, "workspace_id", "") or "") if project else None
            ),
            user_workspace_id=workspace_id,
            resource_owner_user_id=(
                str(getattr(project, "user_id", "") or "") if project else None
            ),
            user_id=user_id,
        ):
            raise PermissionDeniedError("conversation does not belong to workspace")
        return conversation

    async def _require_project_access(
        self,
        project_id: str,
        *,
        user_id: str,
        workspace_id: str | None = None,
    ):
        project = await self.project_repo.get(project_id)
        if not project:
            raise NotFoundError("project not found")
        if not can_access_workspace_resource(
            resource_workspace_id=str(getattr(project, "workspace_id", "") or ""),
            user_workspace_id=workspace_id,
            resource_owner_user_id=str(getattr(project, "user_id", "") or ""),
            user_id=user_id,
        ):
            raise PermissionDeniedError("project does not belong to workspace")
        return project

    async def _resolve_workspace_root(self, project_id: str) -> str | None:
        project = await self.project_repo.get(project_id)
        if not project:
            return None
        from app.path_layout import project_home

        try:
            return str(project_home(project))
        except ValueError:
            return None

    def _normalize_history(
        self,
        *,
        session_id: str,
        rows: list[dict],
    ) -> list[AgentMessageRead]:
        normalized: list[AgentMessageRead] = []
        tool_parts_by_call_id: dict[str, dict] = {}

        for row in rows:
            role = str(row.get("role") or "")
            if role == "tool":
                tool_call_id = str(row.get("tool_call_id") or "")
                tool_part = tool_parts_by_call_id.get(tool_call_id)
                if tool_part is not None:
                    tool_part["status"] = "done"
                    tool_part["result"] = self._stringify_tool_result(
                        row.get("content")
                    )
                    tool_part["resultData"] = self._parse_tool_result_json(
                        row.get("content")
                    )
                continue

            if role == "user":
                content = str(row.get("content") or "")
                normalized.append(
                    AgentMessageRead(
                        id=uuid5(NAMESPACE_URL, f"hermes:{session_id}:{row.get('id')}"),
                        role=AgentMessageRole.USER,
                        type=AgentMessageType.TEXT,
                        content=content,
                        metadata={
                            "parts": [{"type": "text", "text": content}],
                            "response_id": None,
                        },
                        created_at=self._coerce_timestamp(row.get("timestamp")),
                    )
                )
                continue

            if role != "assistant":
                continue

            parts: list[dict] = []
            reasoning = row.get("reasoning")
            if isinstance(reasoning, str) and reasoning.strip():
                parts.append(
                    {
                        "type": "thinking",
                        "text": reasoning,
                        "isStreaming": False,
                    }
                )

            content = str(row.get("content") or "")
            if content:
                parts.append({"type": "text", "text": content})

            raw_tool_calls = row.get("tool_calls") or []
            if isinstance(raw_tool_calls, str):
                try:
                    raw_tool_calls = json.loads(raw_tool_calls)
                except json.JSONDecodeError:
                    raw_tool_calls = []

            for tool_call in raw_tool_calls:
                if not isinstance(tool_call, dict):
                    continue
                function_payload = tool_call.get("function") or {}
                tool_name = function_payload.get("name") or tool_call.get("name") or ""
                tool_args = function_payload.get("arguments") or tool_call.get(
                    "arguments"
                )
                part = {
                    "type": "tool-call",
                    "id": str(tool_call.get("id") or ""),
                    "toolName": str(tool_name),
                    "args": self._parse_tool_args(tool_args),
                    "status": "running",
                }
                parts.append(part)
                if part["id"]:
                    tool_parts_by_call_id[part["id"]] = part

            normalized.append(
                AgentMessageRead(
                    id=uuid5(NAMESPACE_URL, f"hermes:{session_id}:{row.get('id')}"),
                    role=AgentMessageRole.AGENT,
                    type=AgentMessageType.TEXT,
                    content=content or None,
                    metadata={"parts": parts, "response_id": None},
                    created_at=self._coerce_timestamp(row.get("timestamp")),
                )
            )

        return normalized

    async def _build_approval_history(
        self, conversation_id: str
    ) -> list[AgentMessageRead]:
        approvals = await self.approval_repo.get_for_conversation(conversation_id)
        messages: list[AgentMessageRead] = []
        for approval in approvals:
            payload = approval.payload or {}
            created_at = self._coerce_timestamp(approval.created_at)
            part = {
                "type": "approval",
                "approvalId": str(approval.id),
                "toolName": str(payload.get("tool") or "clarify"),
                "toolInput": payload.get("input")
                or {
                    "question": payload.get("question"),
                    "choices": payload.get("choices") or [],
                },
                "approvalType": str(payload.get("approval_type") or "clarify"),
                "status": approval.status,
                "createdAt": created_at.isoformat(),
                "risk": payload.get("risk"),
            }
            messages.append(
                AgentMessageRead(
                    id=uuid5(NAMESPACE_URL, f"hermes-approval:{approval.id}"),
                    role=AgentMessageRole.AGENT,
                    type=AgentMessageType.TEXT,
                    content=None,
                    metadata={
                        "response_id": str(approval.response_id),
                        "parts": [part],
                    },
                    created_at=created_at,
                )
            )
        return messages

    async def _expire_approval(self, approval_id: str, *, reason: str) -> None:
        async with self._new_session() as session:
            repo = AgentApprovalHandleRepository(session)
            approval = await repo.get(approval_id)
            if approval is None or approval.status != AgentApprovalHandleStatus.PENDING:
                return
            await repo.update(
                approval,
                status=AgentApprovalHandleStatus.EXPIRED,
                resolved_by=f"system:{reason}",
                resolved_at=datetime.now(timezone.utc),
            )

    async def _publish_tool_progress(
        self,
        *,
        project_id: str,
        conversation_id: str,
        response_id: str | None,
        tool_name: str,
        status: str,
        preview: str,
        approval_id: str | None = None,
        approval_type: str | None = None,
        risk: str | None = None,
    ) -> None:
        await publish_event(
            event="agent.tool_call_progress",
            project_id=project_id,
            conversation_id=conversation_id,
            data={
                "id": response_id or "",
                "type": "tool_call_progress",
                "content": preview,
                "metadata": {
                    "response_id": response_id or "",
                    "id": "",
                    "name": tool_name,
                    "status": status,
                    "preview": preview,
                    "approval_id": approval_id or "",
                    "approval_type": approval_type or "",
                    "risk": risk or "",
                },
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "stream": True,
            },
        )

    def _select_approval_choice(self, action: str, choices: list[str]) -> str:
        if not choices:
            return action
        lowered = {choice.lower(): choice for choice in choices}
        if action in lowered:
            return lowered[action]
        if action == "approve":
            return choices[0]
        if len(choices) > 1:
            return choices[1]
        return choices[0]

    def _new_session(self):
        return self._session_factory()()

    def _session_factory(self):
        bind = self.session.bind
        if bind is None:
            return app_database.async_session_maker
        return async_sessionmaker(
            bind=bind,
            expire_on_commit=False,
        )

    def _parse_tool_args(self, raw_args):
        if isinstance(raw_args, dict):
            return raw_args
        if isinstance(raw_args, str):
            try:
                parsed = json.loads(raw_args)
            except json.JSONDecodeError:
                return {"raw": raw_args}
            return parsed if isinstance(parsed, dict) else {"value": parsed}
        return {}

    def _stringify_tool_result(self, value) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        try:
            return json.dumps(value, ensure_ascii=True)
        except TypeError:
            return str(value)

    def _parse_tool_result_json(self, value):
        if isinstance(value, (dict, list)):
            return value
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return None
        return None

    def _coerce_timestamp(self, value) -> datetime:
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value, tz=timezone.utc)
        if isinstance(value, str):
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return datetime.now(timezone.utc)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc)
