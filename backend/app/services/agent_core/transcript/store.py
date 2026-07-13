from __future__ import annotations

import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.agent_core_repo import AgentMessageRepository
from app.services.agent_core.transcript.messages import parts_to_text, text_part


class AgentTranscriptStore:
    def __init__(self, session: AsyncSession):
        self.messages = AgentMessageRepository(session)

    async def append_text(
        self,
        *,
        session_id: str,
        turn_id: str | None,
        role: str,
        text: str,
        metadata: dict[str, Any] | None = None,
        ordering_index: int | None = None,
    ):
        return await self.append_parts(
            session_id=session_id,
            turn_id=turn_id,
            role=role,
            parts=[text_part(text)],
            metadata=metadata,
            ordering_index=ordering_index,
        )

    async def append_parts(
        self,
        *,
        session_id: str,
        turn_id: str | None,
        role: str,
        parts: list[dict[str, Any]],
        metadata: dict[str, Any] | None = None,
        status: str = "committed",
        ordering_index: int | None = None,
    ):
        if ordering_index is None:
            ordering_index = await self.messages.next_ordering_index(session_id)
        return await self.messages.create(
            session_id=session_id,
            turn_id=turn_id,
            role=role,
            content_parts=parts,
            message_metadata=metadata,
            status=status,
            ordering_index=ordering_index,
        )

    async def list_messages(self, session_id: str):
        return await self.messages.list_for_session(session_id)

    async def append_tool_result_once(
        self,
        *,
        session_id: str,
        turn_id: str,
        tool_call_id: str | None,
        tool_name: str,
        status: str,
        result: dict[str, Any] | None = None,
        error: dict[str, Any] | None = None,
    ) -> bool:
        call_id = str(tool_call_id or "")
        for message in await self.messages.list_for_session(session_id):
            metadata = message.message_metadata or {}
            if message.role == "tool" and str(metadata.get("tool_call_id") or "") == call_id:
                return False
        await self.append_text(
            session_id=session_id,
            turn_id=turn_id,
            role="tool",
            text=json.dumps(
                {
                    "tool": tool_name,
                    "status": status,
                    "result": result,
                    "error": error,
                },
                separators=(",", ":"),
                default=str,
            ),
            metadata={"tool_call_id": tool_call_id, "tool": tool_name},
        )
        return True

    async def unresolved_tool_calls(
        self,
        session_id: str,
        *,
        turn_id: str | None = None,
    ) -> list[dict[str, str]]:
        unresolved: dict[str, dict[str, str]] = {}
        for message in await self.messages.list_for_session(session_id):
            if message.status != "committed":
                continue
            if turn_id is not None and str(message.turn_id or "") != turn_id:
                continue
            if message.role == "assistant":
                for part in message.content_parts or []:
                    if part.get("type") != "tool_calls":
                        continue
                    for call in part.get("tool_calls") or []:
                        if not isinstance(call, dict) or not call.get("id"):
                            continue
                        function = call.get("function") or {}
                        call_id = str(call["id"])
                        unresolved[call_id] = {
                            "tool_call_id": call_id,
                            "tool_name": str(function.get("name") or "unknown"),
                            "turn_id": str(message.turn_id or ""),
                        }
            elif message.role == "tool":
                call_id = str((message.message_metadata or {}).get("tool_call_id") or "")
                unresolved.pop(call_id, None)
        return list(unresolved.values())

    async def compact_session(
        self,
        *,
        session_id: str,
        turn_id: str | None,
        threshold_chars: int,
        preserve_recent_messages: int = 12,
    ) -> dict[str, Any] | None:
        committed = await self.messages.list_committed_for_session(session_id)
        if len(committed) <= preserve_recent_messages:
            return None
        transcript_chars = sum(self._message_size(message) for message in committed)
        if transcript_chars <= threshold_chars:
            return None

        cut = self._safe_compaction_cut(
            committed,
            len(committed) - preserve_recent_messages,
        )
        summary_candidates = committed[:cut]
        if not summary_candidates:
            return None
        if len(summary_candidates) == 1 and self._is_compaction_summary(summary_candidates[0]):
            return None

        insert_before = committed[cut].ordering_index
        await self.messages.shift_ordering_indices(session_id, starting_at=insert_before)
        summary_text = self._build_summary(summary_candidates)
        summary_message = await self.append_text(
            session_id=session_id,
            turn_id=turn_id,
            role="assistant",
            text=summary_text,
            metadata={
                "kind": "compaction_summary",
                "supersedes": [str(message.id) for message in summary_candidates],
            },
            ordering_index=insert_before,
        )
        await self.messages.mark_superseded([str(message.id) for message in summary_candidates])
        return {
            "summary_message_id": str(summary_message.id),
            "superseded_message_ids": [str(message.id) for message in summary_candidates],
            "transcript_chars": transcript_chars,
        }

    def _build_summary(self, messages: list[Any]) -> str:
        lines = ["Conversation summary for continuity:"]
        for message in messages:
            text = parts_to_text(message.content_parts or [])
            if message.role == "tool":
                lines.append(f"- tool: {self._truncate_text(text, 240)}")
            else:
                lines.append(f"- {message.role}: {self._truncate_text(text, 240)}")
        return "\n".join(lines)

    def _message_size(self, message: Any) -> int:
        return len(json.dumps(message.content_parts or [], default=str))

    def _is_compaction_summary(self, message: Any) -> bool:
        metadata = getattr(message, "message_metadata", None) or {}
        return metadata.get("kind") == "compaction_summary"

    def _safe_compaction_cut(self, messages: list[Any], cut: int) -> int:
        """Keep an assistant tool-call message contiguous with all tool results."""
        if cut <= 0 or cut >= len(messages) or messages[cut].role != "tool":
            return cut
        first_tool = cut
        while first_tool > 0 and messages[first_tool - 1].role == "tool":
            first_tool -= 1
        assistant_index = first_tool - 1
        if assistant_index < 0 or messages[assistant_index].role != "assistant":
            return cut
        call_ids = self._assistant_tool_call_ids(messages[assistant_index])
        if not call_ids:
            return cut
        tool_index = first_tool
        while tool_index < len(messages) and messages[tool_index].role == "tool":
            result_id = str(
                (messages[tool_index].message_metadata or {}).get("tool_call_id") or ""
            )
            if result_id not in call_ids:
                return cut
            tool_index += 1
        return assistant_index

    def _assistant_tool_call_ids(self, message: Any) -> set[str]:
        call_ids: set[str] = set()
        for part in message.content_parts or []:
            if part.get("type") != "tool_calls":
                continue
            for call in part.get("tool_calls") or []:
                if isinstance(call, dict) and call.get("id"):
                    call_ids.add(str(call["id"]))
        return call_ids

    def _truncate_text(self, text: str, limit: int) -> str:
        if len(text) <= limit:
            return text
        return text[:limit] + "…"
