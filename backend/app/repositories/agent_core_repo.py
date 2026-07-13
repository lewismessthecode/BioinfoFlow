from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import desc, exists, func, insert, literal, or_, select, update

from app.models.agent_core import (
    AgentAction,
    AgentActionStatus,
    AgentArtifact,
    AgentEvent,
    AgentMessage,
    AgentMessageStatus,
    AgentMemory,
    AgentSession,
    AgentSessionStatus,
    AgentTurn,
    AgentTurnStatus,
)
from app.repositories.base import BaseRepository
from app.schemas.common import Pagination


def _owned_running_turn(turn_id: str, owner_token: str):
    return exists(
        select(1).where(
            AgentTurn.id == turn_id,
            AgentTurn.status == AgentTurnStatus.RUNNING,
            AgentTurn.owner_token == owner_token,
        )
    )


def _model_column(model: type, attribute_name: str):
    return getattr(model, attribute_name).property.columns[0]


def ensure_clean_owned_publication_session(session) -> None:
    """Reject unrelated ORM mutations before an owner-conditioned write.

    This must run before any SQL statement that could trigger autoflush. Once
    autoflush runs, SQLAlchemy removes the objects from ``dirty``/``new`` and a
    later guard can no longer prevent the publication commit from carrying
    those unrelated changes with it.
    """
    if session.new or session.dirty or session.deleted:
        raise RuntimeError(
            "Owner-conditioned publication requires a clean database session"
        )


async def _fence_owned_turn(
    session,
    *,
    turn_id: str,
    expected_owner_token: str,
) -> bool:
    result = await session.execute(
        update(AgentTurn)
        .where(
            AgentTurn.id == turn_id,
            AgentTurn.status == AgentTurnStatus.RUNNING,
            AgentTurn.owner_token == expected_owner_token,
        )
        .values(owner_token=expected_owner_token)
        .execution_options(synchronize_session=False)
    )
    return result.rowcount == 1


async def _create_for_owned_turn(
    session,
    model: type,
    *,
    turn_id: str,
    expected_owner_token: str,
    data: dict[str, Any],
    commit: bool = True,
):
    """Insert one publication only while the turn owner still matches.

    ``INSERT .. SELECT .. WHERE EXISTS`` keeps the owner predicate and the
    publication in one database statement on SQLite and PostgreSQL.  The
    generated id lets the caller load the ORM object without relying on
    backend-specific rowcount behavior.
    """
    ensure_clean_owned_publication_session(session)
    values = dict(data)
    values.setdefault("id", uuid4())
    columns = [_model_column(model, key) for key in values]
    selected_values = [
        literal(value, type_=column.type)
        for column, value in zip(columns, values.values())
    ]
    statement = (
        insert(model.__table__)
        .from_select(
            columns,
            select(*selected_values).where(
                _owned_running_turn(turn_id, expected_owner_token)
            ),
        )
        .returning(model.__table__.c.id)
    )
    try:
        result = await session.execute(statement)
        inserted_id = result.scalar_one_or_none()
        if inserted_id is None:
            await session.rollback()
            return None, False
        fenced = await _fence_owned_turn(
            session,
            turn_id=turn_id,
            expected_owner_token=expected_owner_token,
        )
        if not fenced:
            await session.rollback()
            return None, False
        if commit:
            await session.commit()
    except Exception:
        await session.rollback()
        raise
    obj = await session.scalar(
        select(model)
        .where(model.id == inserted_id)
        .execution_options(populate_existing=True)
    )
    return obj, obj is not None


class AgentSessionRepository(BaseRepository[AgentSession]):
    model = AgentSession

    async def list_for_user(
        self,
        *,
        workspace_id: str,
        user_id: str,
        project_id: str | None = None,
        parent_session_id: str | None = None,
        include_archived: bool = False,
        include_children: bool = False,
        limit: int = 50,
    ) -> tuple[list[AgentSession], Pagination]:
        stmt = select(self.model).where(
            self.model.workspace_id == workspace_id,
            self.model.user_id == user_id,
        )
        if project_id:
            stmt = stmt.where(self.model.project_id == project_id)
        if not include_archived:
            stmt = stmt.where(self.model.status == AgentSessionStatus.ACTIVE)
        if parent_session_id is not None:
            stmt = stmt.where(
                self.model.lineage["parent_session_id"].as_string() == parent_session_id
            )
        elif not include_children:
            stmt = stmt.where(
                or_(
                    self.model.lineage.is_(None),
                    self.model.lineage["parent_session_id"].as_string().is_(None),
                )
            )
        stmt = stmt.order_by(desc(self.model.updated_at), desc(self.model.id))
        result = await self.session.execute(stmt.limit(limit))
        items = list(result.scalars().all())
        count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
        total_count = await self.session.scalar(count_stmt)
        total = total_count or 0
        return items, Pagination(
            limit=limit, has_more=total > len(items), total_count=total
        )


class AgentTurnRepository(BaseRepository[AgentTurn]):
    model = AgentTurn

    def ensure_clean_resume_claim_session(self) -> None:
        """Require a resume worker to claim ownership from a clean unit of work."""
        if self.session.new or self.session.dirty or self.session.deleted:
            raise RuntimeError("Atomic turn resume claim requires a clean session")

    async def claim_action_resume(
        self,
        turn_id: str,
        *,
        owner_token: str,
        expected_resume_batch_token: str | None,
        claimed_at: datetime,
        lease_until: datetime,
    ) -> tuple[AgentTurn | None, bool]:
        """Atomically claim ownership of approval-resume side effects.

        A normal approval wait and a recovery-enqueued running turn are both
        claimable when they have no active lease. The conditional UPDATE is
        the cross-process ownership boundary and uses only portable SQL so it
        has the same compare-and-set semantics on SQLite and PostgreSQL.
        """
        self.ensure_clean_resume_claim_session()
        await self.session.commit()
        no_active_lease = or_(
            self.model.lease_until.is_(None),
            self.model.lease_until <= claimed_at,
        )
        batch_token_matches = (
            self.model.resume_batch_token.is_(None)
            if expected_resume_batch_token is None
            else self.model.resume_batch_token == expected_resume_batch_token
        )
        result = await self.session.execute(
            update(self.model)
            .where(
                self.model.id == turn_id,
                self.model.status.in_(
                    [
                        AgentTurnStatus.WAITING_APPROVAL,
                        AgentTurnStatus.RUNNING,
                    ]
                ),
                no_active_lease,
                batch_token_matches,
            )
            .values(
                status=AgentTurnStatus.RUNNING,
                started_at=func.coalesce(self.model.started_at, claimed_at),
                completed_at=None,
                error_code=None,
                error_message=None,
                claimed_at=claimed_at,
                lease_until=lease_until,
                owner_token=owner_token,
                resume_batch_token=None,
            )
            .execution_options(synchronize_session=False)
        )
        claimed = result.rowcount == 1
        await self.session.commit()
        turn = await self.session.scalar(
            select(self.model)
            .where(self.model.id == turn_id)
            .execution_options(populate_existing=True)
        )
        return turn, claimed

    async def claim_run(
        self,
        turn_id: str,
        *,
        owner_token: str,
        claimed_at: datetime,
        lease_until: datetime,
    ) -> tuple[AgentTurn | None, bool]:
        """Atomically claim queued work or take over an expired running turn."""
        self.ensure_clean_resume_claim_session()
        await self.session.commit()
        result = await self.session.execute(
            update(self.model)
            .where(
                self.model.id == turn_id,
                self.model.status.in_(
                    [AgentTurnStatus.QUEUED, AgentTurnStatus.RUNNING]
                ),
                or_(
                    self.model.lease_until.is_(None),
                    self.model.lease_until <= claimed_at,
                ),
            )
            .values(
                status=AgentTurnStatus.RUNNING,
                started_at=func.coalesce(self.model.started_at, claimed_at),
                completed_at=None,
                error_code=None,
                error_message=None,
                claimed_at=claimed_at,
                lease_until=lease_until,
                owner_token=owner_token,
                resume_batch_token=None,
            )
            .execution_options(synchronize_session=False)
        )
        claimed = result.rowcount == 1
        await self.session.commit()
        turn = await self.session.scalar(
            select(self.model)
            .where(self.model.id == turn_id)
            .execution_options(populate_existing=True)
        )
        return turn, claimed

    async def claim_recovery(
        self,
        turn_id: str,
        *,
        owner_token: str,
        claimed_at: datetime,
        lease_until: datetime,
    ) -> tuple[AgentTurn | None, bool]:
        """Fence startup recovery from live workers and competing processes."""
        self.ensure_clean_resume_claim_session()
        await self.session.commit()
        result = await self.session.execute(
            update(self.model)
            .where(
                self.model.id == turn_id,
                self.model.status.in_(
                    [
                        AgentTurnStatus.QUEUED,
                        AgentTurnStatus.RUNNING,
                        AgentTurnStatus.WAITING_APPROVAL,
                    ]
                ),
                or_(
                    self.model.lease_until.is_(None),
                    self.model.lease_until <= claimed_at,
                ),
            )
            .values(
                owner_token=owner_token,
                claimed_at=claimed_at,
                lease_until=lease_until,
            )
            .execution_options(synchronize_session=False)
        )
        claimed = result.rowcount == 1
        await self.session.commit()
        turn = await self.session.scalar(
            select(self.model)
            .where(self.model.id == turn_id)
            .execution_options(populate_existing=True)
        )
        return turn, claimed

    async def renew_owned_lease(
        self,
        turn_id: str,
        *,
        owner_token: str,
        lease_until: datetime,
    ) -> bool:
        result = await self.session.execute(
            update(self.model)
            .where(
                self.model.id == turn_id,
                self.model.status == AgentTurnStatus.RUNNING,
                self.model.owner_token == owner_token,
            )
            .values(lease_until=lease_until)
            .execution_options(synchronize_session=False)
        )
        renewed = result.rowcount == 1
        await self.session.commit()
        return renewed

    async def is_owned(self, turn_id: str, *, owner_token: str) -> bool:
        return bool(
            await self.session.scalar(
                select(func.count())
                .select_from(self.model)
                .where(
                    self.model.id == turn_id,
                    self.model.status == AgentTurnStatus.RUNNING,
                    self.model.owner_token == owner_token,
                )
            )
        )

    async def update_owned(
        self,
        turn_id: str,
        *,
        expected_owner_token: str,
        **data: object,
    ) -> tuple[AgentTurn | None, bool]:
        result = await self.session.execute(
            update(self.model)
            .where(
                self.model.id == turn_id,
                self.model.status == AgentTurnStatus.RUNNING,
                self.model.owner_token == expected_owner_token,
            )
            .values(**data)
            .execution_options(synchronize_session=False)
        )
        updated = result.rowcount == 1
        await self.session.commit()
        turn = await self.session.scalar(
            select(self.model)
            .where(self.model.id == turn_id)
            .execution_options(populate_existing=True)
        )
        return turn, updated

    async def list_for_session(self, session_id: str) -> list[AgentTurn]:
        stmt = (
            select(self.model)
            .where(self.model.session_id == session_id)
            .order_by(self.model.created_at, self.model.id)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_recoverable(self) -> list[AgentTurn]:
        stmt = (
            select(self.model)
            .where(
                self.model.status.in_(
                    [
                        AgentTurnStatus.QUEUED,
                        AgentTurnStatus.RUNNING,
                        AgentTurnStatus.WAITING_APPROVAL,
                    ]
                )
            )
            .order_by(self.model.created_at, self.model.id)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class AgentMessageRepository(BaseRepository[AgentMessage]):
    model = AgentMessage

    async def create_for_owned_turn(
        self,
        *,
        turn_id: str,
        expected_owner_token: str,
        **data: Any,
    ) -> tuple[AgentMessage | None, bool]:
        return await _create_for_owned_turn(
            self.session,
            self.model,
            turn_id=turn_id,
            expected_owner_token=expected_owner_token,
            data={"turn_id": turn_id, **data},
        )

    async def compact_for_owned_turn(
        self,
        *,
        session_id: str,
        turn_id: str,
        expected_owner_token: str,
        insert_before: int,
        summary_data: dict[str, Any],
        superseded_message_ids: list[str],
    ) -> tuple[AgentMessage | None, bool]:
        ensure_clean_owned_publication_session(self.session)
        try:
            await self.session.execute(
                update(self.model)
                .where(
                    self.model.session_id == session_id,
                    self.model.ordering_index >= insert_before,
                    _owned_running_turn(turn_id, expected_owner_token),
                )
                .values(ordering_index=self.model.ordering_index + 1)
                .execution_options(synchronize_session=False)
            )
            summary, owned = await _create_for_owned_turn(
                self.session,
                self.model,
                turn_id=turn_id,
                expected_owner_token=expected_owner_token,
                data={"turn_id": turn_id, **summary_data},
                commit=False,
            )
            if not owned or summary is None:
                return None, False
            if superseded_message_ids:
                await self.session.execute(
                    update(self.model)
                    .where(
                        self.model.id.in_(superseded_message_ids),
                        _owned_running_turn(turn_id, expected_owner_token),
                    )
                    .values(status=AgentMessageStatus.SUPERSEDED)
                    .execution_options(synchronize_session=False)
                )
            await self.session.commit()
            await self.session.refresh(summary)
            return summary, True
        except Exception:
            await self.session.rollback()
            raise

    async def next_ordering_index(self, session_id: str) -> int:
        stmt = select(func.max(self.model.ordering_index)).where(
            self.model.session_id == session_id
        )
        current = await self.session.scalar(stmt)
        return int(current or 0) + 1

    async def list_for_session(self, session_id: str) -> list[AgentMessage]:
        stmt = (
            select(self.model)
            .where(self.model.session_id == session_id)
            .order_by(self.model.ordering_index, self.model.created_at, self.model.id)
            .execution_options(populate_existing=True)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_committed_for_session(self, session_id: str) -> list[AgentMessage]:
        stmt = (
            select(self.model)
            .where(
                self.model.session_id == session_id,
                self.model.status == "committed",
            )
            .order_by(self.model.ordering_index, self.model.created_at, self.model.id)
            .execution_options(populate_existing=True)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def find_committed_tool_result(
        self,
        *,
        session_id: str,
        turn_id: str,
        tool_call_id: str | None,
    ) -> AgentMessage | None:
        if not tool_call_id:
            return None
        stmt = (
            select(self.model)
            .where(
                self.model.session_id == session_id,
                self.model.turn_id == turn_id,
                self.model.role == "tool",
                self.model.status == AgentMessageStatus.COMMITTED,
            )
            .order_by(desc(self.model.ordering_index), desc(self.model.id))
        )
        result = await self.session.execute(stmt)
        for message in result.scalars().all():
            metadata = message.message_metadata or {}
            if metadata.get("tool_call_id") == tool_call_id:
                return message
        return None

    async def shift_ordering_indices(
        self, session_id: str, *, starting_at: int, delta: int = 1
    ) -> None:
        if delta == 0:
            return
        await self.session.execute(
            update(self.model)
            .where(
                self.model.session_id == session_id,
                self.model.ordering_index >= starting_at,
            )
            .values(ordering_index=self.model.ordering_index + delta)
        )
        await self.session.commit()

    async def mark_superseded(self, message_ids: list[str]) -> None:
        if not message_ids:
            return
        stmt = select(self.model).where(self.model.id.in_(message_ids))
        result = await self.session.execute(stmt)
        for message in result.scalars().all():
            message.status = "superseded"
        await self.session.commit()

    async def update_message(
        self, message: AgentMessage, **data: object
    ) -> AgentMessage:
        for key, value in data.items():
            setattr(message, key, value)
        await self.session.commit()
        await self.session.refresh(message)
        return message

    async def create_replacing_turn_metadata(
        self,
        *,
        metadata_key: str,
        expected_owner_token: str | None = None,
        **data: object,
    ) -> AgentMessage | None:
        turn_id = str(data["turn_id"])
        if expected_owner_token is not None:
            ensure_clean_owned_publication_session(self.session)
        stmt = select(self.model).where(
            self.model.turn_id == turn_id,
            self.model.status == AgentMessageStatus.COMMITTED,
        )
        result = await self.session.execute(stmt)
        metadata_updates: list[tuple[str, dict | None]] = []
        for message in result.scalars().all():
            metadata = dict(message.message_metadata or {})
            if metadata_key not in metadata:
                continue
            metadata.pop(metadata_key)
            if expected_owner_token is None:
                message.message_metadata = metadata or None
            else:
                metadata_updates.append((str(message.id), metadata or None))
        if expected_owner_token is not None:
            message, owned = await _create_for_owned_turn(
                self.session,
                self.model,
                turn_id=turn_id,
                expected_owner_token=expected_owner_token,
                data=dict(data),
                commit=False,
            )
            if not owned or message is None:
                return None
            for message_id, metadata in metadata_updates:
                await self.session.execute(
                    update(self.model)
                    .where(
                        self.model.id == message_id,
                        _owned_running_turn(turn_id, expected_owner_token),
                    )
                    .values(message_metadata=metadata)
                    .execution_options(synchronize_session=False)
                )
            await self.session.commit()
            return message
        message = self.model(**data)
        self.session.add(message)
        try:
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise
        await self.session.refresh(message)
        return message

    async def create_replacing_session_metadata(
        self,
        *,
        metadata_key: str,
        expected_owner_token: str | None = None,
        **data: object,
    ) -> AgentMessage | None:
        session_id = str(data["session_id"])
        turn_id = str(data["turn_id"]) if data.get("turn_id") is not None else None
        if expected_owner_token is not None:
            if turn_id is None:
                raise ValueError("turn_id is required for owner-conditioned messages")
            ensure_clean_owned_publication_session(self.session)
        stmt = select(self.model).where(self.model.session_id == session_id)
        result = await self.session.execute(stmt)
        metadata_updates: list[tuple[str, dict | None]] = []
        for existing in result.scalars().all():
            metadata = dict(existing.message_metadata or {})
            if metadata_key not in metadata:
                continue
            metadata.pop(metadata_key)
            if expected_owner_token is None:
                existing.message_metadata = metadata or None
            else:
                metadata_updates.append((str(existing.id), metadata or None))
        if expected_owner_token is not None:
            message, owned = await _create_for_owned_turn(
                self.session,
                self.model,
                turn_id=turn_id,
                expected_owner_token=expected_owner_token,
                data=dict(data),
                commit=False,
            )
            if not owned or message is None:
                return None
            for message_id, metadata in metadata_updates:
                await self.session.execute(
                    update(self.model)
                    .where(
                        self.model.id == message_id,
                        _owned_running_turn(turn_id, expected_owner_token),
                    )
                    .values(message_metadata=metadata)
                    .execution_options(synchronize_session=False)
                )
            await self.session.commit()
            return message
        message = self.model(**data)
        self.session.add(message)
        try:
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise
        await self.session.refresh(message)
        return message

    async def clear_turn_metadata(
        self,
        *,
        turn_id: str,
        metadata_key: str,
        expected_owner_token: str | None = None,
    ) -> bool:
        if expected_owner_token is not None:
            ensure_clean_owned_publication_session(self.session)
        stmt = select(self.model).where(self.model.turn_id == turn_id)
        result = await self.session.execute(stmt)
        changed = False
        for message in result.scalars().all():
            metadata = dict(message.message_metadata or {})
            if metadata_key not in metadata:
                continue
            metadata.pop(metadata_key)
            if expected_owner_token is None:
                message.message_metadata = metadata or None
            else:
                await self.session.execute(
                    update(self.model)
                    .where(
                        self.model.id == str(message.id),
                        _owned_running_turn(turn_id, expected_owner_token),
                    )
                    .values(message_metadata=metadata or None)
                    .execution_options(synchronize_session=False)
                )
            changed = True
        if changed:
            if expected_owner_token is not None and not await _fence_owned_turn(
                self.session,
                turn_id=turn_id,
                expected_owner_token=expected_owner_token,
            ):
                await self.session.rollback()
                return False
            await self.session.commit()
        return True

    async def clear_session_metadata(
        self,
        *,
        session_id: str,
        metadata_key: str,
        turn_id: str | None = None,
        expected_owner_token: str | None = None,
    ) -> bool:
        if expected_owner_token is not None and turn_id is None:
            raise ValueError("turn_id is required for owner-conditioned metadata clear")
        if expected_owner_token is not None:
            ensure_clean_owned_publication_session(self.session)
        stmt = select(self.model).where(self.model.session_id == session_id)
        result = await self.session.execute(stmt)
        changed = False
        for message in result.scalars().all():
            metadata = dict(message.message_metadata or {})
            if metadata_key not in metadata:
                continue
            metadata.pop(metadata_key)
            if expected_owner_token is None:
                message.message_metadata = metadata or None
            else:
                await self.session.execute(
                    update(self.model)
                    .where(
                        self.model.id == str(message.id),
                        _owned_running_turn(str(turn_id), expected_owner_token),
                    )
                    .values(message_metadata=metadata or None)
                    .execution_options(synchronize_session=False)
                )
            changed = True
        if changed:
            if expected_owner_token is not None and not await _fence_owned_turn(
                self.session,
                turn_id=str(turn_id),
                expected_owner_token=expected_owner_token,
            ):
                await self.session.rollback()
                return False
            await self.session.commit()
        return True


class AgentEventRepository(BaseRepository[AgentEvent]):
    model = AgentEvent

    async def create_for_owned_turn(
        self,
        *,
        turn_id: str,
        expected_owner_token: str,
        **data: Any,
    ) -> tuple[AgentEvent | None, bool]:
        return await _create_for_owned_turn(
            self.session,
            self.model,
            turn_id=turn_id,
            expected_owner_token=expected_owner_token,
            data={"turn_id": turn_id, **data},
        )

    async def next_seq(self, session_id: str) -> int:
        stmt = select(func.max(self.model.seq)).where(
            self.model.session_id == session_id
        )
        current = await self.session.scalar(stmt)
        return int(current or 0) + 1

    async def list_for_turn(
        self,
        *,
        turn_id: str,
        after_seq: int = 0,
    ) -> list[AgentEvent]:
        stmt = (
            select(self.model)
            .where(self.model.turn_id == turn_id, self.model.seq > after_seq)
            .order_by(self.model.seq)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_session(
        self,
        *,
        session_id: str,
        after_seq: int = 0,
        limit: int | None = None,
    ) -> list[AgentEvent]:
        stmt = select(self.model).where(
            self.model.session_id == session_id,
            self.model.seq > after_seq,
        )
        if limit is not None:
            stmt = stmt.order_by(desc(self.model.seq)).limit(limit)
        else:
            stmt = stmt.order_by(self.model.seq)
        result = await self.session.execute(stmt)
        events = list(result.scalars().all())
        if limit is not None:
            events.sort(key=lambda event: event.seq)
        return events


class AgentActionRepository(BaseRepository[AgentAction]):
    model = AgentAction

    async def create_for_owned_turn(
        self,
        *,
        turn_id: str,
        expected_owner_token: str,
        **data: Any,
    ) -> tuple[AgentAction | None, bool]:
        return await _create_for_owned_turn(
            self.session,
            self.model,
            turn_id=turn_id,
            expected_owner_token=expected_owner_token,
            data={"turn_id": turn_id, **data},
        )

    async def update_all_owned(
        self,
        action: AgentAction,
        *,
        expected_owner_token: str,
        **data: Any,
    ) -> tuple[AgentAction | None, bool]:
        ensure_clean_owned_publication_session(self.session)
        result = await self.session.execute(
            update(self.model)
            .where(
                self.model.id == str(action.id),
                self.model.turn_id == str(action.turn_id),
                _owned_running_turn(str(action.turn_id), expected_owner_token),
            )
            .values(**data)
            .returning(self.model.id)
            .execution_options(synchronize_session=False)
        )
        updated_id = result.scalar_one_or_none()
        if updated_id is None:
            await self.session.rollback()
            return None, False
        fenced = await _fence_owned_turn(
            self.session,
            turn_id=str(action.turn_id),
            expected_owner_token=expected_owner_token,
        )
        if not fenced:
            await self.session.rollback()
            return None, False
        await self.session.commit()
        updated = await self.session.scalar(
            select(self.model)
            .where(self.model.id == updated_id)
            .execution_options(populate_existing=True)
        )
        return updated, updated is not None

    def ensure_clean_resume_claim_session(self) -> None:
        """Require the resume worker's unit of work to be read-only.

        The CAS deliberately commits its existing transaction before issuing
        the conditional UPDATE so two SQLite readers can safely become
        serialized writers. Resume workers use fresh sessions; rejecting a
        dirty unit of work here prevents that boundary from committing an
        unrelated caller mutation through autoflush.
        """
        if self.session.new or self.session.dirty or self.session.deleted:
            raise RuntimeError("Atomic action resume claim requires a clean session")

    async def claim_requested_resume(
        self,
        action_id: str,
        *,
        started_at: datetime,
        expected_owner_token: str | None = None,
    ) -> tuple[AgentAction | None, bool]:
        """Atomically claim one approved action for resume execution.

        Resume workers first inspect the action and its surrounding session
        policy. End that read transaction before the compare-and-set so SQLite
        can serialize concurrent writers without attempting to upgrade two
        stale read transactions. The conditional UPDATE remains the ownership
        boundary on every database: exactly one worker can change the durable
        ``requested + requires_resume`` state to ``running``.
        """
        self.ensure_clean_resume_claim_session()
        await self.session.commit()
        predicates = [
            self.model.id == action_id,
            self.model.status == AgentActionStatus.REQUESTED,
            self.model.requires_resume.is_(True),
        ]
        if expected_owner_token is not None:
            predicates.append(
                _owned_running_turn(self.model.turn_id, expected_owner_token)
            )
        result = await self.session.execute(
            update(self.model)
            .where(*predicates)
            .values(
                status=AgentActionStatus.RUNNING,
                requires_resume=False,
                started_at=started_at,
            )
            .execution_options(synchronize_session=False)
        )
        claimed = result.rowcount == 1
        if claimed and expected_owner_token is not None:
            action_turn_id = await self.session.scalar(
                select(self.model.turn_id).where(self.model.id == action_id)
            )
            if action_turn_id is None or not await _fence_owned_turn(
                self.session,
                turn_id=str(action_turn_id),
                expected_owner_token=expected_owner_token,
            ):
                await self.session.rollback()
                claimed = False
        await self.session.commit()
        action = await self.session.scalar(
            select(self.model)
            .where(self.model.id == action_id)
            .execution_options(populate_existing=True)
        )
        return action, claimed

    async def list_for_turn(self, turn_id: str) -> list[AgentAction]:
        stmt = (
            select(self.model)
            .where(self.model.turn_id == turn_id)
            .order_by(self.model.created_at, self.model.id)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_open_for_turn(self, turn_id: str) -> list[AgentAction]:
        stmt = (
            select(self.model)
            .where(
                self.model.turn_id == turn_id,
                self.model.status.in_(
                    [
                        AgentActionStatus.WAITING_DECISION,
                        AgentActionStatus.REQUESTED,
                        AgentActionStatus.RUNNING,
                    ]
                ),
            )
            .order_by(desc(self.model.created_at), desc(self.model.id))
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class AgentArtifactRepository(BaseRepository[AgentArtifact]):
    model = AgentArtifact

    async def create_for_owned_turn(
        self,
        *,
        turn_id: str,
        expected_owner_token: str,
        **data: Any,
    ) -> tuple[AgentArtifact | None, bool]:
        return await _create_for_owned_turn(
            self.session,
            self.model,
            turn_id=turn_id,
            expected_owner_token=expected_owner_token,
            data={"turn_id": turn_id, **data},
        )

    async def list_for_session(self, session_id: str) -> list[AgentArtifact]:
        stmt = (
            select(self.model)
            .where(self.model.session_id == session_id)
            .order_by(desc(self.model.created_at), desc(self.model.id))
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_turn(self, turn_id: str) -> list[AgentArtifact]:
        stmt = (
            select(self.model)
            .where(self.model.turn_id == turn_id)
            .order_by(desc(self.model.created_at), desc(self.model.id))
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class AgentMemoryRepository(BaseRepository[AgentMemory]):
    model = AgentMemory

    async def list_for_workspace(
        self,
        *,
        workspace_id: str,
        project_id: str | None = None,
        status: str | None = None,
        scope: str | None = None,
        type: str | None = None,
    ) -> list[AgentMemory]:
        stmt = select(self.model).where(self.model.workspace_id == workspace_id)
        if project_id:
            stmt = stmt.where(self.model.project_id == project_id)
        if status:
            stmt = stmt.where(self.model.status == status)
        if scope:
            stmt = stmt.where(self.model.scope == scope)
        if type:
            stmt = stmt.where(self.model.type == type)
        stmt = stmt.order_by(desc(self.model.updated_at), desc(self.model.id))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
