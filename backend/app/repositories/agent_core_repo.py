from __future__ import annotations

from sqlalchemy import desc, func, or_, select, update

from app.models.agent_core import (
    AgentAction,
    AgentActionStatus,
    AgentArtifact,
    AgentEvent,
    AgentMessage,
    AgentMemory,
    AgentSession,
    AgentSessionStatus,
    AgentToolCallBatch,
    AgentTurn,
    AgentTurnStatus,
)
from app.repositories.base import BaseRepository
from app.schemas.common import Pagination


class AgentSessionRepository(BaseRepository[AgentSession]):
    model = AgentSession

    async def get_fresh(self, session_id: str) -> AgentSession | None:
        stmt = (
            select(self.model)
            .where(self.model.id == session_id)
            .execution_options(populate_existing=True)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def update_with_policy_version(
        self,
        session: AgentSession,
        *,
        increment_policy_version: bool,
        **data: object,
    ) -> AgentSession:
        values = dict(data)
        if increment_policy_version:
            values["permission_policy_version"] = self.model.permission_policy_version + 1
        stmt = (
            update(self.model)
            .where(self.model.id == session.id)
            .values(**values)
            .returning(self.model)
            .execution_options(populate_existing=True)
        )
        result = await self.session.execute(stmt)
        updated = result.scalar_one()
        await self.session.commit()
        return updated

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
        return items, Pagination(limit=limit, has_more=total > len(items), total_count=total)


class AgentTurnRepository(BaseRepository[AgentTurn]):
    model = AgentTurn

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

    async def shift_ordering_indices(self, session_id: str, *, starting_at: int, delta: int = 1) -> None:
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

    async def update_message(self, message: AgentMessage, **data: object) -> AgentMessage:
        for key, value in data.items():
            setattr(message, key, value)
        await self.session.commit()
        await self.session.refresh(message)
        return message


class AgentEventRepository(BaseRepository[AgentEvent]):
    model = AgentEvent

    async def next_seq(self, session_id: str) -> int:
        stmt = select(func.max(self.model.seq)).where(self.model.session_id == session_id)
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

    async def list_for_batch(self, batch_id: str) -> list[AgentAction]:
        stmt = (
            select(self.model)
            .where(self.model.tool_batch_id == batch_id)
            .order_by(self.model.tool_call_ordinal, self.model.id)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class AgentToolCallBatchRepository(BaseRepository[AgentToolCallBatch]):
    model = AgentToolCallBatch

    async def continuation_state(self, batch_id: str) -> str:
        batch = await self.get(batch_id)
        if batch is None:
            return "missing"
        actions = await AgentActionRepository(self.session).list_for_batch(batch_id)
        if len(actions) != batch.tool_call_count:
            return "evaluating"
        terminal = {
            AgentActionStatus.COMPLETED,
            AgentActionStatus.FAILED,
            AgentActionStatus.CANCELLED,
            AgentActionStatus.REJECTED,
        }
        if all(action.status in terminal for action in actions):
            return "ready"
        if any(action.status == AgentActionStatus.REQUESTED for action in actions):
            return "requested"
        if any(action.status == AgentActionStatus.RUNNING for action in actions):
            return "running"
        return "waiting"


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
