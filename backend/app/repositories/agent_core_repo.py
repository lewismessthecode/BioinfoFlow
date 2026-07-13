from __future__ import annotations

from uuid import UUID, uuid4

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
    AgentTurn,
    AgentTurnStatus,
)
from app.repositories.base import BaseRepository
from app.schemas.common import Pagination


class AgentSessionRepository(BaseRepository[AgentSession]):
    model = AgentSession

    async def get_fresh(self, session_id: str) -> AgentSession | None:
        result = await self.session.execute(
            select(self.model)
            .where(self.model.id == session_id)
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def lock_for_update(self, session_id: str) -> AgentSession | None:
        result = await self.session.execute(
            select(self.model)
            .where(self.model.id == session_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def claim_active_turn(self, session_id: str, turn_id: str) -> bool:
        result = await self.session.execute(
            update(self.model)
            .where(
                self.model.id == session_id,
                or_(
                    self.model.active_turn_id.is_(None),
                    self.model.active_turn_id == turn_id,
                ),
            )
            .values(active_turn_id=turn_id)
            .execution_options(synchronize_session=False)
        )
        await self.session.commit()
        return result.rowcount == 1

    async def release_active_turn(self, session_id: str, turn_id: str) -> bool:
        result = await self.session.execute(
            update(self.model)
            .where(
                self.model.id == session_id,
                self.model.active_turn_id == turn_id,
            )
            .values(active_turn_id=None)
            .execution_options(synchronize_session=False)
        )
        await self.session.commit()
        return result.rowcount == 1

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

    async def create_with_session_claim(
        self,
        *,
        session_id: str,
        turn_id: str,
        session_updates: dict[str, object] | None = None,
        user_parts: list[dict],
        user_metadata: dict,
        created_event_type: str,
        created_event_payload: dict,
        **data,
    ) -> AgentTurn | None:
        values = {"active_turn_id": turn_id, **(session_updates or {})}
        active_turn_exists = (
            select(self.model.id)
            .where(
                self.model.id == AgentSession.active_turn_id,
                self.model.status.in_(
                    [
                        AgentTurnStatus.QUEUED,
                        AgentTurnStatus.RUNNING,
                        AgentTurnStatus.WAITING_USER,
                        AgentTurnStatus.WAITING_APPROVAL,
                    ]
                ),
            )
            .exists()
        )
        result = await self.session.execute(
            update(AgentSession)
            .where(
                AgentSession.id == session_id,
                or_(
                    AgentSession.active_turn_id.is_(None),
                    ~active_turn_exists,
                ),
            )
            .values(**values)
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            await self.session.rollback()
            return None
        turn = self.model(id=UUID(turn_id), session_id=session_id, **data)
        ordering_index = int(
            await self.session.scalar(
                select(func.max(AgentMessage.ordering_index)).where(
                    AgentMessage.session_id == session_id
                )
            )
            or 0
        ) + 1
        event_seq = int(
            await self.session.scalar(
                select(func.max(AgentEvent.seq)).where(
                    AgentEvent.session_id == session_id
                )
            )
            or 0
        ) + 1
        self.session.add_all(
            [
                turn,
                AgentMessage(
                    session_id=session_id,
                    turn_id=UUID(turn_id),
                    role="user",
                    content_parts=user_parts,
                    message_metadata=user_metadata,
                    status="committed",
                    ordering_index=ordering_index,
                ),
                AgentEvent(
                    session_id=session_id,
                    turn_id=UUID(turn_id),
                    seq=event_seq,
                    type=created_event_type,
                    payload=created_event_payload,
                    visibility="user",
                    schema_version=1,
                ),
            ]
        )
        try:
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise
        await self.session.refresh(turn)
        return turn

    async def claim_for_run(
        self,
        turn_id: str,
        *,
        claimed_at,
        lease_until,
    ) -> AgentTurn | None:
        running_action_exists = (
            select(AgentAction.id)
            .where(
                AgentAction.turn_id == turn_id,
                AgentAction.status == AgentActionStatus.RUNNING,
            )
            .exists()
        )
        result = await self.session.execute(
            update(self.model)
            .where(
                self.model.id == turn_id,
                ~running_action_exists,
                or_(
                    (
                        self.model.status.in_(
                            [AgentTurnStatus.QUEUED, AgentTurnStatus.WAITING_APPROVAL]
                        )
                        & or_(
                            self.model.claimed_at.is_(None),
                            self.model.lease_until.is_(None),
                            self.model.lease_until < claimed_at,
                        )
                    ),
                    (
                        (self.model.status == AgentTurnStatus.RUNNING)
                        & or_(
                            self.model.claimed_at.is_(None),
                            self.model.lease_until.is_(None),
                            self.model.lease_until < claimed_at,
                        )
                    ),
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
            )
            .execution_options(synchronize_session=False)
        )
        await self.session.commit()
        if result.rowcount != 1:
            return None
        refreshed = await self.session.execute(
            select(self.model)
            .where(self.model.id == turn_id)
            .execution_options(populate_existing=True)
        )
        return refreshed.scalar_one()

    async def update_if_claimed(
        self,
        turn_id: str,
        *,
        expected_claimed_at,
        **values,
    ) -> AgentTurn | None:
        result = await self.session.execute(
            update(self.model)
            .where(
                self.model.id == turn_id,
                self.model.status == AgentTurnStatus.RUNNING,
                self.model.claimed_at == expected_claimed_at,
            )
            .values(**values)
            .execution_options(synchronize_session=False)
        )
        await self.session.commit()
        if result.rowcount != 1:
            return None
        return await self.get_fresh(turn_id)

    async def claim_expired_for_recovery(
        self,
        turn_id: str,
        *,
        expected_claimed_at,
        claimed_at,
        lease_until,
    ) -> AgentTurn | None:
        return await self.claim_for_recovery(
            turn_id,
            expected_status=AgentTurnStatus.RUNNING,
            expected_claimed_at=expected_claimed_at,
            claimed_at=claimed_at,
            lease_until=lease_until,
        )

    async def claim_for_recovery(
        self,
        turn_id: str,
        *,
        expected_status: str,
        expected_claimed_at,
        claimed_at,
        lease_until,
    ) -> AgentTurn | None:
        result = await self.session.execute(
            update(self.model)
            .where(
                self.model.id == turn_id,
                self.model.status == expected_status,
                self.model.claimed_at == expected_claimed_at,
                or_(
                    self.model.lease_until.is_(None),
                    self.model.lease_until <= claimed_at,
                ),
            )
            .values(claimed_at=claimed_at, lease_until=lease_until)
            .execution_options(synchronize_session=False)
        )
        await self.session.commit()
        if result.rowcount != 1:
            return None
        return await self.get_fresh(turn_id)

    async def update_if_recovery_claimed(
        self,
        turn_id: str,
        *,
        expected_claimed_at,
        **values,
    ) -> AgentTurn | None:
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
                self.model.claimed_at == expected_claimed_at,
            )
            .values(**values)
            .execution_options(synchronize_session=False)
        )
        await self.session.commit()
        if result.rowcount != 1:
            return None
        return await self.get_fresh(turn_id)

    async def get_fresh(self, turn_id: str) -> AgentTurn | None:
        result = await self.session.execute(
            select(self.model)
            .where(self.model.id == turn_id)
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

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

    async def find_with_pending_observation(
        self,
        session_id: str,
        *,
        exclude_turn_id: str | None = None,
    ) -> AgentTurn | None:
        for turn in await self.list_for_session(session_id):
            if exclude_turn_id is not None and str(turn.id) == exclude_turn_id:
                continue
            progress = (turn.loop_state or {}).get("progress")
            if isinstance(progress, dict) and isinstance(
                progress.get("pending_observation"), dict
            ):
                return turn
        return None


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

    async def claim_requested(
        self,
        action_id: str,
        *,
        started_at,
        turn_id: str | None = None,
        expected_turn_claimed_at=None,
    ) -> AgentAction | None:
        """Atomically transition one approved action into execution ownership."""
        conditions = [
            self.model.id == action_id,
            self.model.status == AgentActionStatus.REQUESTED,
        ]
        if turn_id is not None and expected_turn_claimed_at is not None:
            conditions.append(
                select(AgentTurn.id)
                .where(
                    AgentTurn.id == turn_id,
                    AgentTurn.status == AgentTurnStatus.RUNNING,
                    AgentTurn.claimed_at == expected_turn_claimed_at,
                )
                .exists()
            )
        result = await self.session.execute(
            update(self.model)
            .where(*conditions)
            .values(
                status=AgentActionStatus.RUNNING,
                requires_resume=False,
                started_at=started_at,
            )
            .execution_options(synchronize_session=False)
        )
        await self.session.commit()
        if result.rowcount != 1:
            return None
        return await self.session.get(self.model, action_id, populate_existing=True)

    async def transition_if_status(
        self,
        action_id: str,
        *,
        expected_statuses: list[str],
        status: str,
        **values,
    ) -> AgentAction | None:
        result = await self.session.execute(
            update(self.model)
            .where(
                self.model.id == action_id,
                self.model.status.in_(expected_statuses),
            )
            .values(status=status, **values)
            .execution_options(synchronize_session=False)
        )
        await self.session.commit()
        if result.rowcount != 1:
            return None
        return await self.session.get(self.model, action_id, populate_existing=True)

    async def complete_running(
        self,
        action_id: str,
        *,
        result: dict,
        output_summary: str | None,
        completed_at,
        artifact_descriptor: dict | None,
        artifact_event_type: str,
        action_event_type: str,
        expected_turn_claimed_at=None,
    ) -> tuple[AgentAction, list[str]] | None:
        session_id = await self.session.scalar(
            select(self.model.session_id).where(self.model.id == action_id)
        )
        if session_id is None:
            return None
        if await AgentSessionRepository(self.session).lock_for_update(
            str(session_id)
        ) is None:
            return None
        conditions = [
            self.model.id == action_id,
            self.model.status == AgentActionStatus.RUNNING,
        ]
        if expected_turn_claimed_at is not None:
            conditions.append(
                select(AgentTurn.id)
                .where(
                    AgentTurn.id == self.model.turn_id,
                    AgentTurn.status == AgentTurnStatus.RUNNING,
                    AgentTurn.claimed_at == expected_turn_claimed_at,
                )
                .exists()
            )
        transition = await self.session.execute(
            update(self.model)
            .where(*conditions)
            .values(
                status=AgentActionStatus.COMPLETED,
                result=result,
                output_summary=output_summary,
                completed_at=completed_at,
            )
            .execution_options(synchronize_session=False)
        )
        if transition.rowcount != 1:
            await self.session.rollback()
            return None
        action = await self.session.get(self.model, action_id, populate_existing=True)
        if action is None:
            await self.session.rollback()
            return None

        next_seq = int(
            await self.session.scalar(
                select(func.max(AgentEvent.seq)).where(
                    AgentEvent.session_id == action.session_id
                )
            )
            or 0
        ) + 1
        artifact_ids: list[str] = []
        events: list[AgentEvent] = []
        if artifact_descriptor is not None:
            artifact_id = uuid4()
            artifact = AgentArtifact(
                id=artifact_id,
                session_id=action.session_id,
                turn_id=action.turn_id,
                action_id=action.id,
                type=artifact_descriptor["type"],
                title=artifact_descriptor["title"],
                summary=artifact_descriptor["summary"],
                payload=artifact_descriptor["payload"],
            )
            self.session.add(artifact)
            artifact_ids.append(str(artifact_id))
            events.append(
                AgentEvent(
                    session_id=action.session_id,
                    turn_id=action.turn_id,
                    seq=next_seq,
                    type=artifact_event_type,
                    payload={
                        "artifact_id": str(artifact_id),
                        "action_id": str(action.id),
                        "type": artifact.type,
                        "title": artifact.title,
                    },
                    visibility="user",
                    schema_version=1,
                )
            )
            next_seq += 1
        events.append(
            AgentEvent(
                session_id=action.session_id,
                turn_id=action.turn_id,
                seq=next_seq,
                type=action_event_type,
                payload={
                    "action_id": str(action.id),
                    "name": action.name,
                    "tool_call_id": (
                        str(action.tool_call_id) if action.tool_call_id else None
                    ),
                    "input_preview": action.input_preview,
                    "result": result,
                    "artifact_ids": artifact_ids,
                },
                visibility="user",
                schema_version=1,
            )
        )
        self.session.add_all(events)
        try:
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise
        completed = await self.session.get(self.model, action_id, populate_existing=True)
        if completed is None:
            return None
        return completed, artifact_ids

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
