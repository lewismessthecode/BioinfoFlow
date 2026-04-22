"""Assistant message metadata formatting and serialization.

Extracted from agent_service.py — handles the structured 'parts' metadata
that tracks thinking blocks, tool calls, and text segments within a single
assistant message.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from app.models.message import MessageType
from app.utils.exceptions import NotFoundError


class AgentMetadataMixin:
    """Mixin providing assistant-message metadata helpers.

    Expects the host class to supply:
      - self.message_repo  (MessageRepository)
    """

    # ------------------------------------------------------------------
    # Default metadata
    # ------------------------------------------------------------------

    @staticmethod
    def _default_assistant_metadata() -> dict[str, Any]:
        return {
            "parts": [],
            "status": "streaming",
            "streaming": True,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    # ------------------------------------------------------------------
    # Update / finalise an assistant message
    # ------------------------------------------------------------------

    async def _update_assistant_message(
        self,
        *,
        assistant_message_id: str,
        message_type: str,
        content: str,
        metadata: dict[str, Any] | None,
        is_stream: bool,
    ):
        message = await self.message_repo.get(assistant_message_id)  # type: ignore[attr-defined]
        if message is None:
            raise NotFoundError("assistant message not found")

        next_metadata = self._merge_assistant_event(
            current_metadata=message.message_metadata,
            current_content=message.content,
            message_type=message_type,
            content=content,
            metadata=metadata or {},
            is_stream=is_stream,
        )
        next_content = self._assistant_text_from_parts(
            next_metadata.get("parts", [])
        )
        return await self.message_repo.update(  # type: ignore[attr-defined]
            message,
            content=next_content,
            message_metadata=next_metadata,
            type=MessageType.TEXT.value,
        )

    async def _finalize_assistant_message(
        self,
        *,
        assistant_message_id: str,
        status: str,
    ) -> None:
        message = await self.message_repo.get(assistant_message_id)  # type: ignore[attr-defined]
        if message is None:
            return
        next_metadata = deepcopy(
            message.message_metadata or self._default_assistant_metadata()
        )
        next_metadata["streaming"] = False
        next_metadata["status"] = status
        next_metadata["updated_at"] = datetime.now(timezone.utc).isoformat()

        parts = next_metadata.get("parts", [])
        for index, part in enumerate(parts):
            if part.get("type") == "thinking":
                parts[index] = {**part, "isStreaming": False}
        next_metadata["parts"] = parts

        await self.message_repo.update(message, message_metadata=next_metadata)  # type: ignore[attr-defined]

    # ------------------------------------------------------------------
    # Merge a new event into the assistant's parts list
    # ------------------------------------------------------------------

    def _merge_assistant_event(
        self,
        *,
        current_metadata: dict[str, Any] | None,
        current_content: str,
        message_type: str,
        content: str,
        metadata: dict[str, Any],
        is_stream: bool,
    ) -> dict[str, Any]:
        next_metadata = deepcopy(
            current_metadata or self._default_assistant_metadata()
        )
        parts = deepcopy(next_metadata.get("parts") or [])
        if not parts and current_content:
            parts.append({"type": "text", "text": current_content})

        if message_type == MessageType.TEXT_DELTA.value:
            if parts and parts[-1].get("type") == "text":
                parts[-1]["text"] = f"{parts[-1].get('text', '')}{content}"
            else:
                parts.append({"type": "text", "text": content})
        elif message_type in (
            MessageType.THINKING.value,
            MessageType.THINKING_CONTENT.value,
            MessageType.THINKING_DELTA.value,
        ):
            think_index = next(
                (
                    idx
                    for idx, part in enumerate(parts)
                    if part.get("type") == "thinking"
                ),
                None,
            )
            next_text = content
            if (
                message_type == MessageType.THINKING_DELTA.value
                and think_index is not None
            ):
                next_text = f"{parts[think_index].get('text', '')}{content}"
            if think_index is None:
                parts.insert(
                    0,
                    {
                        "type": "thinking",
                        "text": next_text,
                        "isStreaming": is_stream,
                    },
                )
            else:
                parts[think_index] = {
                    **parts[think_index],
                    "type": "thinking",
                    "text": next_text,
                    "isStreaming": is_stream,
                }
        elif message_type == MessageType.TOOL_CALL_START.value:
            parts.append(
                {
                    "type": "tool-call",
                    "id": metadata.get("id", ""),
                    "toolName": metadata.get("name", ""),
                    "args": metadata.get("args") or {},
                    "status": "running",
                }
            )
        elif message_type == MessageType.TOOL_CALL_END.value:
            tool_id = metadata.get("id", "")
            updated = False
            for index, part in enumerate(parts):
                if (
                    part.get("type") == "tool-call"
                    and part.get("id") == tool_id
                ):
                    parts[index] = {
                        **part,
                        "status": "error"
                        if metadata.get("is_error")
                        else "done",
                        "result": metadata.get("result"),
                        "durationMs": metadata.get("duration_ms"),
                    }
                    updated = True
                    break
            if not updated:
                parts.append(
                    {
                        "type": "tool-call",
                        "id": tool_id,
                        "toolName": metadata.get("name", ""),
                        "args": {},
                        "status": "error"
                        if metadata.get("is_error")
                        else "done",
                        "result": metadata.get("result"),
                        "durationMs": metadata.get("duration_ms"),
                    }
                )
        elif message_type == MessageType.TEXT.value:
            text_part = {"type": "text", "text": content}
            last_text_index = next(
                (
                    idx
                    for idx in range(len(parts) - 1, -1, -1)
                    if parts[idx].get("type") == "text"
                ),
                None,
            )
            if last_text_index is None:
                parts.append(text_part)
            else:
                parts[last_text_index] = text_part
            parts = [
                {**part, "isStreaming": False}
                if part.get("type") == "thinking"
                else part
                for part in parts
            ]
        elif message_type == MessageType.ERROR.value:
            parts.append({"type": "text", "text": content})
            next_metadata["status"] = "error"
            next_metadata["streaming"] = False
        elif message_type == MessageType.STATUS.value:
            # Persist inline approval cards so a page reload still renders the
            # pending approval. Frontend chat-utils.ts expects the camelCase
            # shape below for type="approval" parts.
            if metadata.get("requires_approval"):
                parts.append(
                    {
                        "type": "approval",
                        "approvalId": metadata.get("approval_id", ""),
                        "toolName": metadata.get("tool", ""),
                        "toolInput": metadata.get("input") or {},
                        "approvalType": metadata.get("approval_type", ""),
                        "status": "pending",
                        "risk": metadata.get("risk"),
                    }
                )

        if message_type == MessageType.TEXT.value and not is_stream:
            next_metadata["status"] = "completed"
            next_metadata["streaming"] = False
            if usage := metadata.get("usage"):
                next_metadata["usage"] = usage
        elif is_stream:
            next_metadata["status"] = "streaming"
            next_metadata["streaming"] = True

        next_metadata["parts"] = parts
        next_metadata["updated_at"] = datetime.now(timezone.utc).isoformat()
        return next_metadata

    # ------------------------------------------------------------------
    # Extract final text content from parts
    # ------------------------------------------------------------------

    @staticmethod
    def _assistant_text_from_parts(parts: list[dict[str, Any]]) -> str:
        texts = [
            part.get("text", "") for part in parts if part.get("type") == "text"
        ]
        return texts[-1] if texts else ""
