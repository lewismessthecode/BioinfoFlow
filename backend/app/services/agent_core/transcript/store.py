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
        commit: bool = True,
    ):
        return await self.append_parts(
            session_id=session_id,
            turn_id=turn_id,
            role=role,
            parts=[text_part(text)],
            metadata=metadata,
            ordering_index=ordering_index,
            commit=commit,
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
        commit: bool = True,
    ):
        if ordering_index is None:
            ordering_index = await self.messages.next_ordering_index(session_id)
        create = self.messages.create if commit else self.messages.add
        return await create(
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

        preserve_start = len(committed) - preserve_recent_messages
        while preserve_start > 0 and committed[preserve_start].role == "tool":
            preserve_start -= 1
        summary_candidates = committed[:preserve_start]
        if not summary_candidates:
            return None
        if len(summary_candidates) == 1 and self._is_compaction_summary(summary_candidates[0]):
            return None

        insert_before = committed[preserve_start].ordering_index
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
