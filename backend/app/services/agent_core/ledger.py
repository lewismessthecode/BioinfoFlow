from __future__ import annotations

import asyncio

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.agent_core_repo import (
    AgentEventRepository,
    ensure_clean_owned_publication_session,
)
from app.services.agent_core.observability import agent_event_log_fields
from app.services.agent_core.ownership import TurnOwnershipLostError
from app.utils.logging import get_logger


_session_seq_locks: dict[str, asyncio.Lock] = {}
logger = get_logger(__name__)


class AgentEventLedger:
    def __init__(
        self,
        session: AsyncSession,
        *,
        owned_turn_id: str | None = None,
        expected_owner_token: str | None = None,
    ):
        self.event_repo = AgentEventRepository(session)
        self.owned_turn_id = owned_turn_id
        self.expected_owner_token = expected_owner_token

    async def append(
        self,
        *,
        session_id: str,
        turn_id: str | None,
        type: str,
        payload: dict | None = None,
        visibility: str = "user",
        schema_version: int = 1,
        commit: bool = True,
        expected_owner_token: str | None = None,
        owner_fenced: bool = False,
        after_owner_fenced_transition: bool = False,
    ):
        if (
            not after_owner_fenced_transition
            and expected_owner_token is None
            and getattr(self, "expected_owner_token", None) is not None
            and turn_id == getattr(self, "owned_turn_id", None)
        ):
            expected_owner_token = self.expected_owner_token
        if expected_owner_token is not None and not owner_fenced:
            if turn_id is None:
                raise ValueError("turn_id is required for owner-conditioned events")
            ensure_clean_owned_publication_session(self.event_repo.session)
        lock = _session_seq_locks.setdefault(session_id, asyncio.Lock())
        for attempt in range(3):
            async with lock:
                seq = await self.event_repo.next_seq(session_id)
                try:
                    data = {
                        "session_id": session_id,
                        "seq": seq,
                        "type": type,
                        "payload": payload or {},
                        "visibility": visibility,
                        "schema_version": schema_version,
                    }
                    if expected_owner_token is not None:
                        if turn_id is None:
                            raise ValueError(
                                "turn_id is required for owner-conditioned events"
                            )
                        if commit:
                            event, owned = await self.event_repo.create_for_owned_turn(
                                turn_id=turn_id,
                                expected_owner_token=expected_owner_token,
                                owner_fenced=owner_fenced,
                                **data,
                            )
                        else:
                            async with self.event_repo.session.begin_nested():
                                event, owned = (
                                    await self.event_repo.create_for_owned_turn(
                                        turn_id=turn_id,
                                        expected_owner_token=expected_owner_token,
                                        commit=False,
                                        owner_fenced=owner_fenced,
                                        **data,
                                    )
                                )
                        if not owned or event is None:
                            raise TurnOwnershipLostError(
                                "Agent turn ownership was replaced"
                            )
                    elif commit:
                        event = await self.event_repo.create(turn_id=turn_id, **data)
                    else:
                        # A savepoint lets a cross-process sequence collision
                        # retry without rolling back the caller's surrounding
                        # CAS/update transaction.
                        async with self.event_repo.session.begin_nested():
                            event = await self.event_repo.add(turn_id=turn_id, **data)
                    logger.debug(
                        "agent_core.event.appended",
                        **agent_event_log_fields(
                            session_id=session_id,
                            turn_id=turn_id,
                            seq=seq,
                            event_type=type,
                            payload=payload,
                        ),
                    )
                    return event
                except IntegrityError:
                    if commit:
                        await self.event_repo.session.rollback()
                    if attempt == 2:
                        raise
                    continue
        raise RuntimeError("Unable to allocate agent event sequence")


__all__ = ["AgentEventLedger"]
