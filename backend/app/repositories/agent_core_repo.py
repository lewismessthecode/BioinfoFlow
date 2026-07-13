from __future__ import annotations

from datetime import datetime

from sqlalchemy import desc, func, or_, select, update

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
            )
            .values(
                status=AgentTurnStatus.RUNNING,
                started_at=func.coalesce(self.model.started_at, claimed_at),
                completed_at=None,
                error_code=None,
                error_message=None,
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
        **data: object,
    ) -> AgentMessage:
        turn_id = str(data["turn_id"])
        stmt = select(self.model).where(
            self.model.turn_id == turn_id,
            self.model.status == AgentMessageStatus.COMMITTED,
        )
        result = await self.session.execute(stmt)
        for message in result.scalars().all():
            metadata = dict(message.message_metadata or {})
            if metadata_key not in metadata:
                continue
            metadata.pop(metadata_key)
            message.message_metadata = metadata or None
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
        **data: object,
    ) -> AgentMessage:
        session_id = str(data["session_id"])
        stmt = select(self.model).where(self.model.session_id == session_id)
        result = await self.session.execute(stmt)
        for existing in result.scalars().all():
            metadata = dict(existing.message_metadata or {})
            if metadata_key not in metadata:
                continue
            metadata.pop(metadata_key)
            existing.message_metadata = metadata or None
        message = self.model(**data)
        self.session.add(message)
        try:
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise
        await self.session.refresh(message)
        return message

    async def clear_turn_metadata(self, *, turn_id: str, metadata_key: str) -> None:
        stmt = select(self.model).where(self.model.turn_id == turn_id)
        result = await self.session.execute(stmt)
        changed = False
        for message in result.scalars().all():
            metadata = dict(message.message_metadata or {})
            if metadata_key not in metadata:
                continue
            metadata.pop(metadata_key)
            message.message_metadata = metadata or None
            changed = True
        if changed:
            await self.session.commit()

    async def clear_session_metadata(
        self,
        *,
        session_id: str,
        metadata_key: str,
    ) -> None:
        stmt = select(self.model).where(self.model.session_id == session_id)
        result = await self.session.execute(stmt)
        changed = False
        for message in result.scalars().all():
            metadata = dict(message.message_metadata or {})
            if metadata_key not in metadata:
                continue
            metadata.pop(metadata_key)
            message.message_metadata = metadata or None
            changed = True
        if changed:
            await self.session.commit()


class AgentEventRepository(BaseRepository[AgentEvent]):
    model = AgentEvent

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
        result = await self.session.execute(
            update(self.model)
            .where(
                self.model.id == action_id,
                self.model.status == AgentActionStatus.REQUESTED,
                self.model.requires_resume.is_(True),
            )
            .values(
                status=AgentActionStatus.RUNNING,
                requires_resume=False,
                started_at=started_at,
            )
            .execution_options(synchronize_session=False)
        )
        claimed = result.rowcount == 1
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
