from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

import app.database as app_database
from app.config import settings
from app.models.message import MessageRole, MessageType
from app.repositories.conversation_repo import ConversationRepository
from app.repositories.message_repo import MessageRepository
from app.repositories.project_repo import ProjectRepository
from app.runtime.events import publish_event
from app.services.agent.agent_metadata import AgentMetadataMixin
from app.services.agent.agent_streaming import AgentStreamingMixin
from app.services.agent.conversation_manager import conversation_manager
from app.services.agent.trace import AgentTraceRecorder
from app.utils.exceptions import BadRequestError, NotFoundError, PermissionDeniedError
from app.utils.logging import get_logger

# Re-export so existing ``from agent_service import EVENT_MAP`` keeps working.
from app.services.agent.agent_streaming import EVENT_MAP  # noqa: F401


class AgentService(AgentStreamingMixin, AgentMetadataMixin):
    def __init__(self, session: AsyncSession):
        self.session = session
        self.project_repo = ProjectRepository(session)
        self.conversation_repo = ConversationRepository(session)
        self.message_repo = MessageRepository(session)
        self.logger = get_logger(__name__)
        self._sequence_counter: int = 0

    async def send_message(
        self,
        *,
        project_id: str,
        content: str,
        user_id: str,
        workspace_id: str | None = None,
        conversation_id: str | None = None,
        message_type: str = MessageType.TEXT.value,
        model_override: str | None = None,
        execution_policy: str | None = None,
    ):
        if not project_id:
            raise BadRequestError("project_id is required")
        project = await self._require_project_access(
            project_id,
            user_id=user_id,
            workspace_id=workspace_id,
        )

        conversation = await self._get_or_create_conversation(
            project_id=str(project.id),
            conversation_id=conversation_id,
            user_id=user_id,
            workspace_id=workspace_id,
            execution_policy=execution_policy,
        )

        user_message = await self.message_repo.create(
            conversation_id=str(conversation.id),
            project_id=str(project.id),
            role=MessageRole.USER.value,
            type=message_type,
            content=content,
            message_metadata=None,
        )
        await self.conversation_repo.update(
            conversation, updated_at=datetime.now(timezone.utc)
        )

        if not getattr(conversation, "title", None):
            title = content.strip().replace("\n", " ")
            if title:
                title = title[:60] + ("..." if len(title) > 60 else "")
                await self.conversation_repo.update(conversation, title=title)

        assistant_message = await self.message_repo.create(
            conversation_id=str(conversation.id),
            project_id=str(project.id),
            role=MessageRole.AGENT.value,
            type=MessageType.TEXT.value,
            content="",
            message_metadata=self._default_assistant_metadata(),
        )

        conv_id = str(conversation.id)
        proj_id = str(project.id)
        session_factory = app_database.async_session_maker
        await conversation_manager.register(
            conv_id,
            proj_id,
            assistant_message_id=str(assistant_message.id),
        )

        task = asyncio.create_task(
            self._run_message_task(
                content=content,
                project_id=proj_id,
                conversation_id=conv_id,
                current_user_message_id=str(user_message.id),
                assistant_message_id=str(assistant_message.id),
                session_factory=session_factory,
                user_id=user_id,
                workspace_id=workspace_id,
                model_override=model_override,
                should_generate_title=not getattr(conversation, "title", None)
                or (
                    conversation.title
                    and conversation.title
                    == content[:60].strip().replace("\n", " ")
                    + ("..." if len(content) > 60 else "")
                ),
            )
        )
        await conversation_manager.set_task(conv_id, task)
        return user_message, conversation

    async def _run_message_task(
        self,
        *,
        content: str,
        project_id: str,
        conversation_id: str,
        current_user_message_id: str,
        assistant_message_id: str,
        session_factory,
        user_id: str,
        workspace_id: str | None,
        model_override: str | None,
        should_generate_title: bool,
    ) -> None:
        was_cancelled = False

        async with session_factory() as session:
            service = AgentService(session)
            trace_recorder = (
                AgentTraceRecorder(
                    session,
                    project_id=project_id,
                    conversation_id=conversation_id,
                    message_id=current_user_message_id,
                )
                if settings.agent_observability
                else None
            )

            try:
                usage_summary = await service._run_v2(
                    content=content,
                    project_id=project_id,
                    conversation_id=conversation_id,
                    current_user_message_id=current_user_message_id,
                    assistant_message_id=assistant_message_id,
                    trace_recorder=trace_recorder,
                    user_id=user_id,
                    workspace_id=workspace_id,
                    model_override=model_override,
                )
                was_cancelled = await conversation_manager.is_cancelled(conversation_id)
            except asyncio.CancelledError:
                was_cancelled = True
                service.logger.info(
                    "agent.task_cancelled", conversation_id=conversation_id
                )
                await session.rollback()
                await service._finalize_assistant_message(
                    assistant_message_id=assistant_message_id,
                    status="cancelled",
                )
                await publish_event(
                    event="agent.cancelled",
                    project_id=project_id,
                    conversation_id=conversation_id,
                    data={
                        "id": assistant_message_id,
                        "message_id": current_user_message_id,
                        "reason": "task_cancelled",
                    },
                )
            except Exception as exc:
                service.logger.error(
                    "agent.runtime_error",
                    conversation_id=conversation_id,
                    error=str(exc),
                    error_type=type(exc).__name__,
                )
                await session.rollback()
                await service._persist_and_publish_agent_event(
                    conversation_id=conversation_id,
                    project_id=project_id,
                    assistant_message_id=assistant_message_id,
                    event={
                        "type": "error",
                        "content": str(exc),
                        "metadata": {"error_type": type(exc).__name__},
                    },
                )
            else:
                if not was_cancelled:
                    await service._finalize_assistant_message(
                        assistant_message_id=assistant_message_id,
                        status="completed",
                    )
                    await publish_event(
                        event="agent.done",
                        project_id=project_id,
                        conversation_id=conversation_id,
                        data={
                            "id": assistant_message_id,
                            "message_id": current_user_message_id,
                            "metadata": usage_summary,
                        },
                    )
                    if should_generate_title:
                        await service._generate_title(
                            conversation_id,
                            content,
                            user_id,
                            model_override,
                        )
            finally:
                await conversation_manager.unregister(conversation_id)

    async def _run_v2(
        self,
        *,
        content: str,
        project_id: str,
        conversation_id: str,
        current_user_message_id: str,
        assistant_message_id: str,
        trace_recorder: AgentTraceRecorder | None,
        user_id: str = "",
        workspace_id: str | None = None,
        model_override: str | None = None,
    ) -> dict[str, int]:
        """Run the new agent runtime loop. Returns token usage summary."""
        from pathlib import Path

        from app.services.agent.runtime import (
            BackgroundManager,
            LLMClient,
            SessionState,
            SkillLoader,
            TaskManager,
            agent_loop,
            build_dispatch_map,
            build_system_prompt,
            register_task_tool,
        )
        from app.services.agent.runtime.messages import estimate_tokens
        from app.path_layout import project_home

        # Resolve workspace root from project (if available)
        project = await self.project_repo.get(project_id)
        allow_workspace_tools = bool(
            project and not getattr(project, "is_default", False)
        )
        workspace_root = (
            project_home(project) if allow_workspace_tools and project else None
        )

        # Create Phase 2 managers
        skill_loader = SkillLoader(Path("agent-skills"))
        task_manager = TaskManager(workspace_root) if workspace_root else None
        background_manager = (
            BackgroundManager(workspace_root) if allow_workspace_tools else None
        )

        session_state = SessionState(
            project_id=project_id,
            conversation_id=conversation_id,
            workspace_root=workspace_root,
            task_manager=task_manager,
            background_manager=background_manager,
        )

        # Load prior conversation history into session state
        prior_messages = await self._load_conversation_history(
            conversation_id,
            exclude_message_id=current_user_message_id,
        )
        session_state.messages = prior_messages

        dispatch_map = build_dispatch_map(
            self.session,
            project_id=project_id,
            workspace_root=workspace_root,
            allow_workspace_tools=allow_workspace_tools,
            todo_manager=session_state.todo,
            skill_loader=skill_loader,
            task_manager=task_manager,
            background_manager=background_manager,
            user_id=user_id,
            workspace_id=workspace_id,
        )

        llm = LLMClient(
            user_id=user_id, model_override=model_override, db_session=self.session
        )

        # Dynamic system prompt factory (refreshes task state each round)
        def make_system_prompt() -> str:
            return build_system_prompt(
                todo_manager=session_state.todo,
                skill_descriptions=skill_loader.get_descriptions(),
                task_state=task_manager.render() if task_manager else "",
            )

        # Register task tool (needs dispatch_map + llm + session — must be after build_dispatch_map)
        register_task_tool(
            dispatch_map,
            session_state=session_state,
            llm=llm,
            system_prompt_factory=make_system_prompt,
            db_session=self.session,
            conversation_id=conversation_id,
        )

        async def on_event(event: dict) -> None:
            await self._persist_and_publish_agent_event(
                conversation_id=conversation_id,
                project_id=project_id,
                assistant_message_id=assistant_message_id,
                event=event,
            )

        async def _is_conversation_cancelled() -> bool:
            return await conversation_manager.is_cancelled(conversation_id)

        # Per-conversation execution policy override. Falls back to
        # settings.agent_execution_policy inside agent_loop when this is None.
        conversation = await self.conversation_repo.get(conversation_id)
        execution_policy = (
            getattr(conversation, "execution_policy", None) if conversation else None
        )

        try:
            await agent_loop(
                user_message=content,
                session_state=session_state,
                dispatch_map=dispatch_map,
                llm=llm,
                system_prompt=make_system_prompt,
                on_event=on_event,
                is_cancelled=_is_conversation_cancelled,
                trace_recorder=trace_recorder,
                db_session=self.session,
                conversation_id=conversation_id,
                execution_policy=execution_policy,
            )
        finally:
            if background_manager is not None:
                background_manager.shutdown()

        return {
            "input_tokens": session_state.total_input_tokens,
            "output_tokens": session_state.total_output_tokens,
            "context_tokens": estimate_tokens(session_state.messages),
            "rounds": session_state.current_round,
        }

    async def cancel_conversation(
        self,
        *,
        conversation_id: str,
        user_id: str,
        workspace_id: str | None = None,
    ) -> bool:
        """Cancel a running conversation."""
        await self._require_conversation(
            conversation_id,
            user_id=user_id,
            workspace_id=workspace_id,
        )
        return await conversation_manager.cancel(conversation_id)

    async def is_conversation_running(
        self,
        conversation_id: str,
        *,
        user_id: str,
        workspace_id: str | None = None,
    ) -> bool:
        """Check if a conversation is currently running."""
        await self._require_conversation(
            conversation_id,
            user_id=user_id,
            workspace_id=workspace_id,
        )
        return await conversation_manager.is_running(conversation_id)

    async def get_conversation_status(
        self,
        conversation_id: str,
        *,
        user_id: str,
        workspace_id: str | None = None,
    ) -> dict[str, Any]:
        """Return running state plus recovery metadata for a conversation."""
        await self._require_conversation(
            conversation_id,
            user_id=user_id,
            workspace_id=workspace_id,
        )
        entry = await conversation_manager.get(conversation_id)
        return {
            "conversation_id": conversation_id,
            "is_running": bool(entry and not entry.cancelled),
            "assistant_message_id": entry.assistant_message_id if entry else None,
            "last_event_at": entry.last_event_at.isoformat() if entry else None,
        }

    async def create_conversation(
        self,
        *,
        project_id: str,
        user_id: str,
        workspace_id: str | None = None,
        title: str | None = None,
        execution_policy: str | None = None,
    ):
        await self._require_project_access(
            project_id,
            user_id=user_id,
            workspace_id=workspace_id,
        )
        return await self.conversation_repo.create(
            project_id=project_id,
            title=title,
            pinned=False,
            user_id=user_id,
            created_by_user_id=user_id,
            execution_policy=execution_policy,
        )

    async def update_conversation(
        self,
        *,
        conversation_id: str,
        user_id: str,
        workspace_id: str | None = None,
        project_id: str | None = None,
        title: str | None = None,
        pinned: bool | None = None,
        execution_policy: str | None = None,
    ):
        conversation = await self._require_conversation(
            conversation_id,
            user_id=user_id,
            workspace_id=workspace_id,
        )
        if project_id and str(conversation.project_id) != project_id:
            raise PermissionDeniedError("conversation does not belong to project")
        updates: dict = {}
        if title is not None:
            updates["title"] = title
        if pinned is not None:
            updates["pinned"] = pinned
        if execution_policy is not None:
            if execution_policy not in {"auto", "approve_all", "bypass"}:
                raise BadRequestError(f"invalid execution_policy: {execution_policy!r}")
            updates["execution_policy"] = execution_policy
            self.logger.info(
                "agent.execution_policy_changed",
                conversation_id=conversation_id,
                policy=execution_policy,
            )
        if not updates:
            return conversation
        return await self.conversation_repo.update(conversation, **updates)

    async def move_conversation(
        self,
        *,
        conversation_id: str,
        target_project_id: str,
        user_id: str,
        workspace_id: str | None = None,
    ):
        """Move a conversation to a different project."""
        conversation = await self._require_conversation(
            conversation_id,
            user_id=user_id,
            workspace_id=workspace_id,
        )
        if str(conversation.project_id) == target_project_id:
            return conversation
        target_project = await self._require_project_access(
            target_project_id,
            user_id=user_id,
            workspace_id=workspace_id,
        )
        if (
            getattr(conversation, "storage_backend", "") == "hermes"
            and getattr(conversation, "workspace_binding_id", None)
            and getattr(target_project, "workspace_id", None)
            and str(conversation.workspace_binding_id)
            != str(target_project.workspace_id)
        ):
            raise PermissionDeniedError(
                "cross-workspace move requires creating a new Hermes conversation"
            )
        return await self.conversation_repo.update(
            conversation, project_id=target_project_id
        )

    async def delete_conversation(
        self,
        *,
        conversation_id: str,
        user_id: str,
        workspace_id: str | None = None,
        project_id: str | None = None,
    ) -> None:
        conversation = await self._require_conversation(
            conversation_id,
            user_id=user_id,
            workspace_id=workspace_id,
        )
        if project_id and str(conversation.project_id) != project_id:
            raise PermissionDeniedError("conversation does not belong to project")
        await self.conversation_repo.delete(conversation)

    async def list_conversations(
        self,
        *,
        user_id: str,
        workspace_id: str | None = None,
        project_id: str | None = None,
        limit: int = 20,
        cursor: str | None = None,
    ):
        if project_id:
            await self._require_project_access(
                project_id,
                user_id=user_id,
                workspace_id=workspace_id,
            )
        return await self.conversation_repo.list(
            limit=limit,
            cursor=cursor,
            project_id=project_id,
            user_id=None if workspace_id else user_id,
        )

    async def get_conversation_history(
        self,
        *,
        conversation_id: str,
        user_id: str,
        workspace_id: str | None = None,
        limit: int = 50,
        before: str | None = None,
    ):
        conversation = await self._require_conversation(
            conversation_id,
            user_id=user_id,
            workspace_id=workspace_id,
        )

        messages = await self.message_repo.get_conversation_messages(conversation_id)
        messages.sort(
            key=lambda msg: (
                msg.created_at,
                0 if msg.role == MessageRole.USER.value else 1,
                str(msg.id),
            )
        )
        if before:
            try:
                cutoff_index = next(
                    index for index, msg in enumerate(messages) if str(msg.id) == before
                )
                messages = messages[:cutoff_index]
            except StopIteration:
                pass

        visible = messages[-limit:] if limit else messages
        if visible and visible[0].role != MessageRole.USER.value:
            first_id = str(visible[0].id)
            try:
                first_index = next(
                    index
                    for index, msg in enumerate(messages)
                    if str(msg.id) == first_id
                )
            except StopIteration:
                first_index = None
            if first_index is not None and first_index > 0:
                for idx in range(first_index - 1, -1, -1):
                    if messages[idx].role == MessageRole.USER.value:
                        anchor = messages[idx]
                        if all(str(msg.id) != str(anchor.id) for msg in visible):
                            visible = [anchor, *visible]
                        break

        return conversation, visible

    async def _require_conversation(
        self,
        conversation_id: str,
        *,
        user_id: str,
        workspace_id: str | None = None,
    ):
        conversation = await self.conversation_repo.get(conversation_id)
        if not conversation:
            raise NotFoundError("conversation not found")
        if workspace_id:
            project = await self.project_repo.get(str(conversation.project_id))
            if not project or str(getattr(project, "workspace_id", "")) != workspace_id:
                raise PermissionDeniedError("conversation does not belong to workspace")
            return conversation
        if str(getattr(conversation, "user_id", "")) != user_id:
            raise PermissionDeniedError("conversation does not belong to user")
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
        if workspace_id:
            if str(getattr(project, "workspace_id", "")) != workspace_id:
                raise PermissionDeniedError("project does not belong to workspace")
            return project
        if str(getattr(project, "user_id", "")) not in {"", user_id}:
            raise PermissionDeniedError("project does not belong to user")
        return project

    async def _load_conversation_history(
        self,
        conversation_id: str,
        *,
        exclude_message_id: str | None = None,
    ) -> list[dict]:
        """Load prior messages from DB and convert to OpenAI format.

        Only text-type user and agent messages are included — thinking,
        tool calls, and status messages are internal and not part of the LLM
        conversation history.

        Trailing user messages are dropped: a conversation that crashed
        mid-tool-use leaves an orphaned user message with no agent reply,
        and appending the new user turn would create two consecutive
        user messages (Anthropic rejects this with 400).
        """
        db_messages = await self.message_repo.get_conversation_messages(conversation_id)

        history: list[dict] = []
        for msg in db_messages:
            if exclude_message_id and str(msg.id) == exclude_message_id:
                continue
            if msg.type not in (MessageType.TEXT.value, "text"):
                continue
            if msg.role == MessageRole.USER.value:
                history.append({"role": "user", "content": msg.content})
            elif msg.role == MessageRole.AGENT.value:
                history.append({"role": "assistant", "content": msg.content})

        while history and history[-1]["role"] == "user":
            history.pop()
        return history

    async def _get_or_create_conversation(
        self,
        *,
        project_id: str,
        conversation_id: str | None,
        user_id: str,
        workspace_id: str | None = None,
        execution_policy: str | None = None,
    ):
        if not conversation_id:
            return await self.conversation_repo.create(
                project_id=project_id,
                user_id=user_id,
                created_by_user_id=user_id,
                execution_policy=execution_policy,
            )
        conversation = await self.conversation_repo.get(conversation_id)
        if not conversation:
            raise NotFoundError("conversation not found")
        if str(conversation.project_id) != project_id:
            raise PermissionDeniedError("conversation does not belong to project")
        if workspace_id:
            await self._require_conversation(
                conversation_id,
                user_id=user_id,
                workspace_id=workspace_id,
            )
            return conversation
        if str(getattr(conversation, "user_id", "")) != user_id:
            raise PermissionDeniedError("conversation does not belong to user")
        return conversation

    async def _generate_title(
        self,
        conversation_id: str,
        user_message: str,
        user_id: str = "",
        model_override: str | None = None,
    ) -> None:
        """Generate a concise conversation title using the LLM."""
        compact_message = " ".join(user_message.strip().split())
        if len(compact_message) <= 60:
            fallback_title = compact_message
        else:
            snippet = compact_message[:61]
            trimmed = snippet.rsplit(" ", 1)[0].strip() or compact_message[:60]
            fallback_title = f"{trimmed}..."
        try:
            from app.services.agent.runtime.llm_client import LLMClient

            llm = LLMClient(
                user_id=user_id,
                model_override=model_override,
                db_session=self.session,
            )
            response = await llm.create(
                system="Generate a concise title (max 6 words) for this conversation. Reply with ONLY the title, no quotes or punctuation.",
                messages=[{"role": "user", "content": user_message}],
                max_tokens=30,
            )
            title = response.content.strip().strip('"').strip("'")
            final_title = title if title and len(title) < 80 else fallback_title
            if final_title:
                conversation = await self.conversation_repo.get(conversation_id)
                if conversation:
                    await self.conversation_repo.update(conversation, title=final_title)
                    self.logger.info("agent.title_generated", title=final_title)
                    await publish_event(
                        event="conversation.title_updated",
                        project_id=str(conversation.project_id),
                        conversation_id=conversation_id,
                        data={"title": final_title},
                    )
        except Exception as exc:
            self.logger.warning("agent.title_generation_failed", error=str(exc))
            if fallback_title:
                conversation = await self.conversation_repo.get(conversation_id)
                if conversation:
                    await self.conversation_repo.update(
                        conversation, title=fallback_title
                    )
                    await publish_event(
                        event="conversation.title_updated",
                        project_id=str(conversation.project_id),
                        conversation_id=conversation_id,
                        data={"title": fallback_title},
                    )
