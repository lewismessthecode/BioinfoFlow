from __future__ import annotations

from sqlalchemy import and_, desc, exists, func, or_, select, update
from datetime import datetime, timezone

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
    AgentToolCallBatchStatus,
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

    async def lock_policy(self, session_id: str) -> AgentSession | None:
        """Serialize policy updates and atomic tool-batch authorization.

        A no-op ``UPDATE`` acquires the session row's write lock on PostgreSQL
        and SQLite alike. ``updated_at`` is explicitly preserved so preparing
        a tool batch does not make the conversation appear user-modified.
        The caller owns the surrounding transaction and must commit/rollback.
        """
        result = await self.session.execute(
            update(self.model)
            .where(self.model.id == session_id)
            .values(
                permission_policy_version=self.model.permission_policy_version,
                updated_at=self.model.updated_at,
            )
            .returning(self.model)
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def policy_version_matches(self, session_id: str, version: int) -> bool:
        current = await self.session.scalar(
            select(self.model.permission_policy_version).where(
                self.model.id == session_id
            )
        )
        return current is not None and int(current) == version

    async def update_with_policy_version(
        self,
        session: AgentSession,
        *,
        increment_policy_version: bool,
        commit: bool = True,
        **data: object,
    ) -> AgentSession:
        values = dict(data)
        if increment_policy_version:
            values["permission_policy_version"] = (
                self.model.permission_policy_version + 1
            )
        stmt = (
            update(self.model)
            .where(self.model.id == session.id)
            .values(**values)
            .returning(self.model)
            .execution_options(populate_existing=True)
        )
        result = await self.session.execute(stmt)
        updated = result.scalar_one()
        if commit:
            await self.session.commit()
        else:
            await self.session.flush()
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
        return items, Pagination(
            limit=limit, has_more=total > len(items), total_count=total
        )


class AgentTurnRepository(BaseRepository[AgentTurn]):
    model = AgentTurn

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

    async def claim_cancelled(
        self,
        turn_id: str,
        *,
        termination_reason: str,
        interrupted_at=None,
    ) -> bool:
        values = {
            "status": AgentTurnStatus.CANCELLED,
            "termination_reason": termination_reason,
            "completed_at": func.now(),
            "loop_state": {"termination_reason": termination_reason},
            "claimed_at": None,
            "lease_until": None,
        }
        if interrupted_at is not None:
            values["interrupt_requested_at"] = interrupted_at
        result = await self.session.execute(
            update(self.model)
            .where(
                self.model.id == turn_id,
                self.model.status.not_in(
                    [
                        AgentTurnStatus.COMPLETED,
                        AgentTurnStatus.FAILED,
                        AgentTurnStatus.CANCELLED,
                    ]
                ),
            )
            .values(**values)
            .returning(self.model.id)
        )
        return result.scalar_one_or_none() is not None


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

    async def get_fresh(self, action_id: str) -> AgentAction | None:
        result = await self.session.execute(
            select(self.model)
            .where(self.model.id == action_id)
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

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
            .execution_options(populate_existing=True)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_active_batches(self, session_id: str) -> list[AgentAction]:
        stmt = (
            select(self.model)
            .outerjoin(
                AgentToolCallBatch,
                AgentToolCallBatch.id == self.model.tool_batch_id,
            )
            .where(
                self.model.session_id == session_id,
                self.model.kind == "tool",
                or_(
                    and_(
                        self.model.tool_batch_id.is_(None),
                        self.model.status == AgentActionStatus.WAITING_DECISION,
                    ),
                    AgentToolCallBatch.status.not_in(
                        [
                            AgentToolCallBatchStatus.TERMINAL,
                            AgentToolCallBatchStatus.FAILED,
                            AgentToolCallBatchStatus.CANCELLED,
                        ]
                    ),
                ),
            )
            .order_by(
                AgentToolCallBatch.batch_ordinal.asc().nullsfirst(),
                self.model.tool_call_ordinal,
                self.model.id,
            )
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def decide_waiting(
        self,
        action_id: str,
        *,
        status: str,
        input: dict,
        permission_decision: dict,
    ) -> AgentAction | None:
        result = await self.session.execute(
            update(self.model)
            .where(
                self.model.id == action_id,
                self.model.status == AgentActionStatus.WAITING_DECISION,
            )
            .values(
                input=input,
                normalized_input=input,
                redacted_input=input,
                permission_decision=permission_decision,
                status=status,
            )
            .returning(self.model)
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def claim_requested(
        self,
        action_id: str,
        *,
        started_at: datetime,
        risk_level: str | None = None,
        risk_reasons: list | None = None,
        affected_resources: list | None = None,
        permission_decision: dict | None = None,
        evaluated_policy_version: int | None = None,
        permission_context_snapshot: dict | None = None,
        expected_policy_version: int | None = None,
    ) -> AgentAction | None:
        values = {
            "status": AgentActionStatus.RUNNING,
            "requires_resume": False,
            "started_at": started_at,
        }
        for key, value in (
            ("risk_level", risk_level),
            ("risk_reasons", risk_reasons),
            ("affected_resources", affected_resources),
            ("permission_decision", permission_decision),
            ("evaluated_policy_version", evaluated_policy_version),
            ("permission_context_snapshot", permission_context_snapshot),
        ):
            if value is not None:
                values[key] = value
        conditions = [
            self.model.id == action_id,
            self.model.status == AgentActionStatus.REQUESTED,
        ]
        if expected_policy_version is not None:
            conditions.append(
                exists(
                    select(AgentSession.id).where(
                        AgentSession.id == self.model.session_id,
                        AgentSession.permission_policy_version
                        == expected_policy_version,
                    )
                )
            )
        result = await self.session.execute(
            update(self.model)
            .where(*conditions)
            .values(**values)
            .returning(self.model)
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def defer_requested_for_approval(
        self,
        action_id: str,
        *,
        risk_level: str,
        risk_reasons: list,
        affected_resources: list,
        permission_decision: dict,
        evaluated_policy_version: int,
        permission_context_snapshot: dict,
    ) -> AgentAction | None:
        result = await self.session.execute(
            update(self.model)
            .where(
                self.model.id == action_id,
                self.model.status == AgentActionStatus.REQUESTED,
            )
            .values(
                status=AgentActionStatus.WAITING_DECISION,
                requires_resume=True,
                risk_level=risk_level,
                risk_reasons=risk_reasons,
                affected_resources=affected_resources,
                permission_decision=permission_decision,
                evaluated_policy_version=evaluated_policy_version,
                permission_context_snapshot=permission_context_snapshot,
            )
            .returning(self.model)
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def fail_requested(
        self,
        action_id: str,
        *,
        error: dict,
        completed_at: datetime,
    ) -> AgentAction | None:
        result = await self.session.execute(
            update(self.model)
            .where(
                self.model.id == action_id,
                self.model.status == AgentActionStatus.REQUESTED,
            )
            .values(
                status=AgentActionStatus.FAILED,
                requires_resume=False,
                error=error,
                completed_at=completed_at,
            )
            .returning(self.model)
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()


class AgentToolCallBatchRepository(BaseRepository[AgentToolCallBatch]):
    model = AgentToolCallBatch

    async def get_fresh(self, batch_id: str) -> AgentToolCallBatch | None:
        stmt = (
            select(self.model)
            .where(self.model.id == batch_id)
            .execution_options(populate_existing=True)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def reserve_next_ordinal(self, turn_id: str) -> int:
        result = await self.session.execute(
            update(AgentTurn)
            .where(AgentTurn.id == turn_id)
            .values(tool_batch_sequence=AgentTurn.tool_batch_sequence + 1)
            .returning(AgentTurn.tool_batch_sequence)
        )
        ordinal = result.scalar_one_or_none()
        if ordinal is None:
            raise RuntimeError(
                f"Cannot reserve tool batch ordinal for missing turn: {turn_id}"
            )
        return int(ordinal)

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

    async def list_nonterminal_for_turn(self, turn_id: str) -> list[AgentToolCallBatch]:
        stmt = (
            select(self.model)
            .where(
                self.model.turn_id == turn_id,
                self.model.status.not_in(["terminal", "failed", "cancelled"]),
            )
            .order_by(
                self.model.batch_ordinal.asc().nullsfirst(),
                self.model.created_at,
                self.model.id,
            )
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def claim_ready(self, batch_id: str) -> bool:
        stmt = (
            update(self.model)
            .where(
                self.model.id == batch_id,
                self.model.status == "ready",
            )
            .values(
                status="continuing",
                continuation_claimed_at=datetime.now(timezone.utc),
            )
            .returning(self.model.id)
        )
        result = await self.session.execute(stmt)
        claimed = result.scalar_one_or_none() is not None
        await self.session.commit()
        return claimed

    async def release_continuing(self, batch_id: str) -> bool:
        stmt = (
            update(self.model)
            .where(
                self.model.id == batch_id,
                self.model.status == "continuing",
            )
            .values(status="ready", continuation_claimed_at=None)
            .returning(self.model.id)
        )
        result = await self.session.execute(stmt)
        released = result.scalar_one_or_none() is not None
        await self.session.commit()
        return released

    async def settle_unclaimed(self, batch_id: str, *, status: str) -> bool:
        stmt = (
            update(self.model)
            .where(
                self.model.id == batch_id,
                self.model.status.in_(["evaluating", "waiting"]),
            )
            .values(status=status)
            .returning(self.model.id)
        )
        result = await self.session.execute(stmt)
        changed = result.scalar_one_or_none() is not None
        await self.session.commit()
        return changed

    async def terminalize_continuing(self, batch_id: str, *, status: str) -> bool:
        stmt = (
            update(self.model)
            .where(
                self.model.id == batch_id,
                self.model.status == "continuing",
            )
            .values(
                status=status,
                completed_at=datetime.now(timezone.utc),
            )
            .returning(self.model.id)
        )
        result = await self.session.execute(stmt)
        changed = result.scalar_one_or_none() is not None
        await self.session.commit()
        return changed

    async def terminalize_continuing_pending(self, batch_id: str) -> bool:
        result = await self.session.execute(
            update(self.model)
            .where(self.model.id == batch_id, self.model.status == "continuing")
            .values(status="terminal", completed_at=datetime.now(timezone.utc))
            .returning(self.model.id)
        )
        return result.scalar_one_or_none() is not None

    async def cancel_nonterminal(self, batch_id: str) -> bool:
        result = await self.session.execute(
            update(self.model)
            .where(
                self.model.id == batch_id,
                self.model.status.in_(["evaluating", "waiting", "ready", "continuing"]),
            )
            .values(status="cancelled", completed_at=datetime.now(timezone.utc))
            .returning(self.model.id)
        )
        changed = result.scalar_one_or_none() is not None
        await self.session.commit()
        return changed

    async def cancel_nonterminal_pending(self, batch_id: str) -> bool:
        result = await self.session.execute(
            update(self.model)
            .where(
                self.model.id == batch_id,
                self.model.status.in_(["evaluating", "waiting", "ready", "continuing"]),
            )
            .values(status="cancelled", completed_at=datetime.now(timezone.utc))
            .returning(self.model.id)
        )
        return result.scalar_one_or_none() is not None


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
