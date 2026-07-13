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
        replace_turn_metadata_key: str | None = None,
        replace_session_metadata_key: str | None = None,
    ):
        if (
            replace_turn_metadata_key is not None
            and replace_session_metadata_key is not None
        ):
            raise ValueError("turn- and session-scoped metadata replacement are exclusive")
        if ordering_index is None:
            ordering_index = await self.messages.next_ordering_index(session_id)
        data = {
            "session_id": session_id,
            "turn_id": turn_id,
            "role": role,
            "content_parts": parts,
            "message_metadata": metadata,
            "status": status,
            "ordering_index": ordering_index,
        }
        if replace_turn_metadata_key is not None:
            if turn_id is None:
                raise ValueError(
                    "turn_id is required when replacing turn-scoped metadata"
                )
            return await self.messages.create_replacing_turn_metadata(
                metadata_key=replace_turn_metadata_key,
                **data,
            )
        if replace_session_metadata_key is not None:
            return await self.messages.create_replacing_session_metadata(
                metadata_key=replace_session_metadata_key,
                **data,
            )
        return await self.messages.create(
            **data,
        )

    async def list_messages(self, session_id: str):
        return await self.messages.list_for_session(session_id)

    async def find_committed_tool_result(
        self,
        *,
        session_id: str,
        turn_id: str,
        tool_call_id: str | None,
    ):
        return await self.messages.find_committed_tool_result(
            session_id=session_id,
            turn_id=turn_id,
            tool_call_id=tool_call_id,
        )

    async def clear_turn_metadata(self, *, turn_id: str, metadata_key: str) -> None:
        await self.messages.clear_turn_metadata(
            turn_id=turn_id,
            metadata_key=metadata_key,
        )

    async def clear_session_metadata(
        self,
        *,
        session_id: str,
        metadata_key: str,
    ) -> None:
        await self.messages.clear_session_metadata(
            session_id=session_id,
            metadata_key=metadata_key,
        )

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

        summary_candidates = committed[:-preserve_recent_messages]
        if not summary_candidates:
            return None
        if len(summary_candidates) == 1 and self._is_compaction_summary(summary_candidates[0]):
            return None

        insert_before = committed[-preserve_recent_messages].ordering_index
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

    def _truncate_text(self, text: str, limit: int) -> str:
        if len(text) <= limit:
            return text
        return text[:limit] + "…"
