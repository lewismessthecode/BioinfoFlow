"""SSE event publishing and stream handling for the agent service.

Extracted from agent_service.py — centralises EVENT_MAP, the persist-and-publish
pipeline, and the low-level SSE publish helper.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.models.message import MessageRole, MessageType
from app.runtime.events import publish_event
from app.services.agent.conversation_manager import conversation_manager

EVENT_MAP: dict[str, str] = {
    MessageType.THINKING.value: "agent.thinking",
    MessageType.THINKING_CONTENT.value: "agent.thinking_content",
    MessageType.PLAN.value: "agent.plan",
    MessageType.ARTIFACT.value: "agent.artifact",
    MessageType.TEXT.value: "agent.message",
    MessageType.STATUS.value: "agent.message",
    MessageType.COMPLETION.value: "agent.message",
    # Stream-only event types
    MessageType.TEXT_DELTA.value: "agent.text_delta",
    MessageType.THINKING_DELTA.value: "agent.thinking_delta",
    MessageType.TOOL_CALL_START.value: "agent.tool_call_start",
    MessageType.TOOL_CALL_END.value: "agent.tool_call_end",
    MessageType.ERROR.value: "agent.error",
}


class AgentStreamingMixin:
    """Mixin providing SSE event persistence and publishing helpers.

    Expects the host class to supply:
      - self.message_repo   (MessageRepository)
      - self.logger         (structlog logger)
      - self._sequence_counter (int)
      - self._normalize_message_type()  (from this mixin)
      - self._update_assistant_message() (from AgentMetadataMixin)
    """

    # ------------------------------------------------------------------
    # Normalise event type strings
    # ------------------------------------------------------------------

    def _normalize_message_type(self, event_type: str) -> str:
        try:
            return MessageType(event_type).value
        except ValueError:
            self.logger.warning(  # type: ignore[attr-defined]
                "agent.unknown_message_type", event_type=event_type
            )
            return MessageType.TEXT.value

    # ------------------------------------------------------------------
    # Persist-and-publish pipeline
    # ------------------------------------------------------------------

    async def _persist_and_publish_agent_event(
        self,
        *,
        conversation_id: str,
        project_id: str,
        assistant_message_id: str | None = None,
        event: dict,
    ) -> None:
        is_stream = bool(event.get("stream"))
        event_type = event.get("type") or MessageType.TEXT.value
        message_type = self._normalize_message_type(event_type)
        content = event.get("content") or ""
        metadata = event.get("metadata")

        if assistant_message_id:
            message = await self._update_assistant_message(  # type: ignore[attr-defined]
                assistant_message_id=assistant_message_id,
                message_type=message_type,
                content=content,
                metadata=metadata,
                is_stream=is_stream,
            )
            await self._publish_agent_event(
                message_type=message_type,
                message_id=str(message.id),
                project_id=project_id,
                conversation_id=conversation_id,
                content=content if is_stream else message.content,
                metadata=metadata if is_stream else message.message_metadata,
                stream=is_stream,
            )
            return

        if is_stream:
            # Streaming events: publish via SSE but do NOT persist to DB
            await self._publish_agent_event(
                message_type=message_type,
                message_id="",
                project_id=project_id,
                conversation_id=conversation_id,
                content=content,
                metadata=metadata,
                stream=True,
            )
        else:
            message = await self._persist_agent_event(
                conversation_id=conversation_id,
                project_id=project_id,
                event=event,
            )
            await self._publish_agent_event(
                message_type=message.type,
                message_id=str(message.id),
                project_id=project_id,
                conversation_id=conversation_id,
                content=message.content,
                metadata=message.message_metadata,
            )

    # ------------------------------------------------------------------
    # Persist a single agent event to DB
    # ------------------------------------------------------------------

    async def _persist_agent_event(
        self,
        *,
        conversation_id: str,
        project_id: str,
        event: dict,
    ):
        event_type = event.get("type") or MessageType.TEXT.value
        message_type = self._normalize_message_type(event_type)
        content = event.get("content") or ""
        metadata = event.get("metadata")
        return await self.message_repo.create(  # type: ignore[attr-defined]
            conversation_id=conversation_id,
            project_id=project_id,
            role=MessageRole.AGENT.value,
            type=message_type,
            content=content,
            message_metadata=metadata,
        )

    # ------------------------------------------------------------------
    # Publish an SSE event
    # ------------------------------------------------------------------

    async def _publish_agent_event(
        self,
        *,
        message_type: str,
        message_id: str,
        project_id: str,
        conversation_id: str,
        content: str,
        metadata: dict[str, Any] | None,
        stream: bool = False,
    ) -> None:
        self._sequence_counter += 1  # type: ignore[attr-defined]
        event_name = EVENT_MAP.get(message_type, "agent.message")
        await conversation_manager.touch(
            conversation_id,
            assistant_message_id=message_id or None,
        )
        await publish_event(
            event=event_name,
            project_id=project_id,
            conversation_id=conversation_id,
            data={
                "id": message_id,
                "type": message_type,
                "content": content,
                "metadata": metadata,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "sequence": self._sequence_counter,  # type: ignore[attr-defined]
                "stream": stream,
            },
        )
