from __future__ import annotations

import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.agent_core_repo import (
    AgentMessageRepository,
    ensure_clean_owned_publication_session,
)
from app.services.agent_core.ownership import TurnOwnershipLostError
from app.services.agent_core.events import AgentEventType
from app.services.agent_core.transcript.messages import parts_to_text, text_part


class AgentTranscriptStore:
    def __init__(
        self,
        session: AsyncSession,
        *,
        owned_turn_id: str | None = None,
        expected_owner_token: str | None = None,
    ):
        self.messages = AgentMessageRepository(session)
        self.owned_turn_id = owned_turn_id
        self.expected_owner_token = expected_owner_token

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
        expected_owner_token: str | None = None,
        owner_fence_held: bool = False,
    ):
        return await self.append_parts(
            session_id=session_id,
            turn_id=turn_id,
            role=role,
            parts=[text_part(text)],
            metadata=metadata,
            ordering_index=ordering_index,
            commit=commit,
            expected_owner_token=expected_owner_token,
            owner_fence_held=owner_fence_held,
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
        replace_turn_metadata_key: str | None = None,
        replace_session_metadata_key: str | None = None,
        expected_owner_token: str | None = None,
        owner_fence_held: bool = False,
    ):
        if (
            replace_turn_metadata_key is not None
            and replace_session_metadata_key is not None
        ):
            raise ValueError(
                "turn- and session-scoped metadata replacement are exclusive"
            )
        expected_owner_token = self._default_owner_token(
            turn_id,
            expected_owner_token,
        )
        if expected_owner_token is not None and not owner_fence_held:
            if turn_id is None:
                raise ValueError("turn_id is required for owner-conditioned messages")
            ensure_clean_owned_publication_session(self.messages.session)
        if owner_fence_held and (expected_owner_token is None or commit):
            raise ValueError(
                "owner_fence_held requires an owner token and commit=False"
            )
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
            if not commit:
                raise ValueError("metadata replacement requires commit=True")
            if turn_id is None:
                raise ValueError(
                    "turn_id is required when replacing turn-scoped metadata"
                )
            message = await self.messages.create_replacing_turn_metadata(
                metadata_key=replace_turn_metadata_key,
                expected_owner_token=expected_owner_token,
                **data,
            )
            if expected_owner_token is not None and message is None:
                raise TurnOwnershipLostError("Agent turn ownership was replaced")
            return message
        if replace_session_metadata_key is not None:
            if not commit:
                raise ValueError("metadata replacement requires commit=True")
            message = await self.messages.create_replacing_session_metadata(
                metadata_key=replace_session_metadata_key,
                expected_owner_token=expected_owner_token,
                **data,
            )
            if expected_owner_token is not None and message is None:
                raise TurnOwnershipLostError("Agent turn ownership was replaced")
            return message
        if expected_owner_token is not None and not owner_fence_held:
            message, owned = await self.messages.create_for_owned_turn(
                turn_id=turn_id,
                expected_owner_token=expected_owner_token,
                **{key: value for key, value in data.items() if key != "turn_id"},
            )
            if not owned or message is None:
                raise TurnOwnershipLostError("Agent turn ownership was replaced")
            return message
        create = self.messages.create if commit else self.messages.add
        return await create(**data)

    async def list_messages(self, session_id: str):
        return await self.messages.list_for_session(session_id)

    async def deliver_pending_steers(
        self,
        *,
        session_id: str,
        turn_id: str,
        expected_owner_token: str,
    ):
        delivered, owned = await self.messages.deliver_pending_steers(
            session_id=session_id,
            turn_id=turn_id,
            expected_owner_token=expected_owner_token,
            received_event_type=AgentEventType.TURN_STEER_RECEIVED,
            delivered_event_type=AgentEventType.TURN_STEER_DELIVERED,
        )
        if not owned:
            raise TurnOwnershipLostError("Agent turn ownership was replaced")
        return delivered

    async def cancel_pending_steers(
        self,
        *,
        session_id: str,
        turn_id: str,
        reason: str,
    ):
        return await self.messages.cancel_pending_steers(
            session_id=session_id,
            turn_id=turn_id,
            received_event_type=AgentEventType.TURN_STEER_RECEIVED,
            cancelled_event_type=AgentEventType.TURN_STEER_CANCELLED,
            reason=reason,
        )

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

    async def tool_call_batch_ids(
        self,
        *,
        session_id: str,
        turn_id: str,
        tool_call_id: str | None,
    ) -> list[str]:
        if not tool_call_id:
            return []
        messages = await self.messages.list_for_session(session_id)
        for message in reversed(messages):
            if (
                message.role != "assistant"
                or str(message.turn_id or "") != turn_id
                or message.status != "committed"
            ):
                continue
            call_ids: list[str] = []
            for part in message.content_parts or []:
                if part.get("type") != "tool_calls":
                    continue
                for call in part.get("tool_calls") or []:
                    if isinstance(call, dict) and call.get("id"):
                        call_ids.append(str(call["id"]))
            if tool_call_id in call_ids:
                return call_ids
        return [tool_call_id]

    async def latest_unresolved_tool_call_batch_ids(
        self,
        *,
        session_id: str,
        turn_id: str,
    ) -> list[str]:
        messages = await self.messages.list_for_session(session_id)
        for message in reversed(messages):
            if (
                message.role != "assistant"
                or str(message.turn_id or "") != turn_id
                or message.status != "committed"
            ):
                continue
            call_ids: list[str] = []
            for part in message.content_parts or []:
                if part.get("type") != "tool_calls":
                    continue
                call_ids.extend(
                    str(call["id"])
                    for call in part.get("tool_calls") or []
                    if isinstance(call, dict) and call.get("id")
                )
            if call_ids:
                return call_ids
        return []

    async def clear_turn_metadata(
        self,
        *,
        turn_id: str,
        metadata_key: str,
        expected_owner_token: str | None = None,
    ) -> None:
        expected_owner_token = self._default_owner_token(
            turn_id,
            expected_owner_token,
        )
        if expected_owner_token is not None:
            ensure_clean_owned_publication_session(self.messages.session)
        owned = await self.messages.clear_turn_metadata(
            turn_id=turn_id,
            metadata_key=metadata_key,
            expected_owner_token=expected_owner_token,
        )
        if not owned:
            raise TurnOwnershipLostError("Agent turn ownership was replaced")

    async def clear_session_metadata(
        self,
        *,
        session_id: str,
        metadata_key: str,
        turn_id: str | None = None,
        expected_owner_token: str | None = None,
    ) -> None:
        effective_turn_id = turn_id or self.owned_turn_id
        expected_owner_token = self._default_owner_token(
            effective_turn_id,
            expected_owner_token,
        )
        if expected_owner_token is not None:
            ensure_clean_owned_publication_session(self.messages.session)
        owned = await self.messages.clear_session_metadata(
            session_id=session_id,
            metadata_key=metadata_key,
            turn_id=effective_turn_id,
            expected_owner_token=expected_owner_token,
        )
        if not owned:
            raise TurnOwnershipLostError("Agent turn ownership was replaced")

    async def compact_session(
        self,
        *,
        session_id: str,
        turn_id: str | None,
        threshold_chars: int,
        preserve_recent_messages: int = 12,
        expected_owner_token: str | None = None,
    ) -> dict[str, Any] | None:
        expected_owner_token = self._default_owner_token(
            turn_id,
            expected_owner_token,
        )
        if expected_owner_token is not None:
            if turn_id is None:
                raise ValueError("turn_id is required for owner-conditioned compaction")
            ensure_clean_owned_publication_session(self.messages.session)
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
        if len(summary_candidates) == 1 and self._is_compaction_summary(
            summary_candidates[0]
        ):
            return None

        insert_before = committed[preserve_start].ordering_index
        summary_text = self._build_summary(summary_candidates)
        superseded_message_ids = [str(message.id) for message in summary_candidates]
        if expected_owner_token is None:
            await self.messages.shift_ordering_indices(
                session_id,
                starting_at=insert_before,
            )
            summary_message = await self.append_text(
                session_id=session_id,
                turn_id=turn_id,
                role="assistant",
                text=summary_text,
                metadata={
                    "kind": "compaction_summary",
                    "supersedes": superseded_message_ids,
                },
                ordering_index=insert_before,
            )
            await self.messages.mark_superseded(superseded_message_ids)
        else:
            summary_message, owned = await self.messages.compact_for_owned_turn(
                session_id=session_id,
                turn_id=turn_id,
                expected_owner_token=expected_owner_token,
                insert_before=insert_before,
                summary_data={
                    "session_id": session_id,
                    "role": "assistant",
                    "content_parts": [text_part(summary_text)],
                    "message_metadata": {
                        "kind": "compaction_summary",
                        "supersedes": superseded_message_ids,
                    },
                    "status": "committed",
                    "ordering_index": insert_before,
                },
                superseded_message_ids=superseded_message_ids,
            )
            if not owned or summary_message is None:
                raise TurnOwnershipLostError("Agent turn ownership was replaced")
        return {
            "summary_message_id": str(summary_message.id),
            "superseded_message_ids": superseded_message_ids,
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

    def _default_owner_token(
        self,
        turn_id: str | None,
        expected_owner_token: str | None,
    ) -> str | None:
        if (
            expected_owner_token is None
            and self.expected_owner_token is not None
            and turn_id == self.owned_turn_id
        ):
            return self.expected_owner_token
        return expected_owner_token
