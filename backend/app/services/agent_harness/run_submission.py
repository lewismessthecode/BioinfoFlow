from __future__ import annotations

from app.repositories.agent_harness_repo import (
    AgentHarnessRepository,
    SessionMutationConflict,
)
from app.services.agent_session_title import derive_automatic_session_title
from app.services.agent_harness.contracts import MessageCommand
from app.services.agent_harness.message_payload import user_message_payload_builder
from app.services.agent_harness.turn_execution_config import (
    resolve_turn_execution_config,
)


_MAX_SESSION_REFRESH_ATTEMPTS = 3


class AgentRunSubmissionService:
    """Prepare mutable Conversation state before one atomic Run submission."""

    def __init__(self, repository: AgentHarnessRepository) -> None:
        self.repository = repository
        self._message_payload_builder = user_message_payload_builder(repository.db)

    async def submit_user_command(self, session_id: str, command: MessageCommand):
        automatic_title = derive_automatic_session_title(
            part.text for part in command.parts if part.type == "text"
        )
        for attempt in range(_MAX_SESSION_REFRESH_ATTEMPTS):
            session = await self.repository.get_session(session_id)
            if session is None or session.status != "active":
                raise LookupError(f"agent session not found: {session_id}")
            current = await self.repository.get_current_run(session_id)
            turn_execution_config = (
                None
                if current is not None
                else await resolve_turn_execution_config(
                    self.repository.db,
                    session,
                )
            )
            try:
                return await self.repository.submit_user_command(
                    session_id,
                    command,
                    message_payload_builder=self._message_payload_builder,
                    automatic_title=automatic_title,
                    turn_execution_config=turn_execution_config,
                    expected_settings_revision=int(session.settings_revision or 1),
                    expected_active_run_id=(str(current.id) if current else None),
                )
            except SessionMutationConflict:
                if attempt + 1 == _MAX_SESSION_REFRESH_ATTEMPTS:
                    raise
        raise AssertionError("unreachable")

    async def create_run_from_next_session_command(
        self,
        session_id: str,
        *,
        kind: str,
    ):
        for attempt in range(_MAX_SESSION_REFRESH_ATTEMPTS):
            session = await self.repository.get_session(session_id)
            if session is None:
                raise LookupError(f"agent session not found: {session_id}")
            if session.status != "active":
                return None
            turn_execution_config = await resolve_turn_execution_config(
                self.repository.db,
                session,
            )
            try:
                return await self.repository.create_run_from_next_session_command(
                    session_id,
                    kind=kind,
                    turn_execution_config=turn_execution_config,
                    message_payload_builder=self._message_payload_builder,
                    expected_settings_revision=int(session.settings_revision or 1),
                )
            except SessionMutationConflict:
                if attempt + 1 == _MAX_SESSION_REFRESH_ATTEMPTS:
                    raise
        raise AssertionError("unreachable")


__all__ = ["AgentRunSubmissionService"]
