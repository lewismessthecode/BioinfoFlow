from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import and_, case, desc, exists, func, insert, literal, or_, select, update

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
    AgentToolCallBatch,
    AgentToolCallBatchStatus,
    AgentTurn,
    AgentTurnStatus,
)
from app.repositories.base import BaseRepository
from app.schemas.common import Pagination


def _owned_running_turn(turn_id, owner_token: str):
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
    """Reject unrelated ORM mutations before starting an owned publication."""
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
    owner_fenced: bool = False,
):
    """Insert a publication only while the durable turn owner still matches.

    ``owner_fenced`` is reserved for a larger atomic unit that has already
    acquired the turn row's owner fence in the same transaction.  It lets the
    durable tool-batch coordinator stage several related rows before one
    commit without weakening the clean-session guard at the transaction edge.
    """
    if owner_fenced:
        if not await _fence_owned_turn(
            session,
            turn_id=turn_id,
            expected_owner_token=expected_owner_token,
        ):
            await session.rollback()
            return None, False
        obj = model(turn_id=turn_id, **data)
        session.add(obj)
        await session.flush()
        if commit:
            await session.commit()
            await session.refresh(obj)
        return obj, True

    ensure_clean_owned_publication_session(session)
    values = dict(data)
    values.setdefault("turn_id", turn_id)
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
        if not await _fence_owned_turn(
            session,
            turn_id=turn_id,
            expected_owner_token=expected_owner_token,
        ):
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

    async def get_fresh(self, session_id: str) -> AgentSession | None:
        stmt = (
            select(self.model)
            .where(self.model.id == session_id)
            .execution_options(populate_existing=True)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    def _active_nonterminal_turn_exists(self):
        return (
            select(AgentTurn.id)
            .where(
                AgentTurn.id == self.model.active_turn_id,
                AgentTurn.status.in_(
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
        require_target_mutable: bool = False,
        commit: bool = True,
        **data: object,
    ) -> AgentSession | None:
        values = dict(data)
        if increment_policy_version:
            values["permission_policy_version"] = (
                self.model.permission_policy_version + 1
            )
        conditions = [self.model.id == session.id]
        if require_target_mutable:
            conditions.append(~self._active_nonterminal_turn_exists())
            values["active_turn_id"] = None
        stmt = (
            update(self.model)
            .where(*conditions)
            .values(**values)
            .returning(self.model)
            .execution_options(populate_existing=True)
        )
        result = await self.session.execute(stmt)
        updated = result.scalar_one_or_none()
        if updated is None:
            if commit:
                await self.session.rollback()
            return None
        if commit:
            await self.session.commit()
        else:
            await self.session.flush()
        return updated

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
        return items, Pagination(
            limit=limit, has_more=total > len(items), total_count=total
        )


class AgentTurnRepository(BaseRepository[AgentTurn]):
    model = AgentTurn

    def ensure_clean_resume_claim_session(self) -> None:
        if self.session.new or self.session.dirty or self.session.deleted:
            raise RuntimeError("Atomic turn resume claim requires a clean session")

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
        """List recovery candidates, including actively leased running turns.

        Active leases are deliberately returned so startup recovery can report
        them as ``skipped``.  The claim CAS remains the authority that prevents
        any mutation or ownership takeover before the lease expires.
        """
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

    async def create_with_session_claim(
        self,
        *,
        session_id: str,
        turn_id: str,
        session_updates: dict[str, object] | None = None,
        increment_policy_version: bool = False,
        user_parts: list[dict],
        user_metadata: dict,
        created_event_type: str,
        created_event_payload: dict,
        **data,
    ) -> AgentTurn | None:
        values = {"active_turn_id": turn_id, **(session_updates or {})}
        if increment_policy_version:
            values["permission_policy_version"] = (
                AgentSession.permission_policy_version + 1
            )
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
                    status=AgentMessageStatus.COMMITTED,
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

    async def claim_action_resume(
        self,
        turn_id: str,
        *,
        owner_token: str,
        expected_resume_batch_token: str | None,
        claimed_at: datetime,
        lease_until: datetime,
    ) -> tuple[AgentTurn | None, bool]:
        self.ensure_clean_resume_claim_session()
        await self.session.commit()
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
                    [AgentTurnStatus.WAITING_APPROVAL, AgentTurnStatus.RUNNING]
                ),
                or_(
                    self.model.lease_until.is_(None),
                    self.model.lease_until <= claimed_at,
                ),
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
        return await self.get_fresh(turn_id), claimed

    async def claim_run(
        self,
        turn_id: str,
        *,
        owner_token: str,
        claimed_at: datetime,
        lease_until: datetime,
    ) -> tuple[AgentTurn | None, bool]:
        self.ensure_clean_resume_claim_session()
        await self.session.commit()
        result = await self.session.execute(
            update(self.model)
            .where(
                self.model.id == turn_id,
                self.model.status.in_([AgentTurnStatus.QUEUED, AgentTurnStatus.RUNNING]),
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
        return await self.get_fresh(turn_id), claimed

    async def claim_recovery(
        self,
        turn_id: str,
        *,
        owner_token: str,
        claimed_at: datetime,
        lease_until: datetime,
    ) -> tuple[AgentTurn | None, bool]:
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
                status=AgentTurnStatus.RUNNING,
                owner_token=owner_token,
                claimed_at=claimed_at,
                lease_until=lease_until,
            )
            .execution_options(synchronize_session=False)
        )
        claimed = result.rowcount == 1
        await self.session.commit()
        return await self.get_fresh(turn_id), claimed

    async def claim_execution(
        self,
        turn_id: str,
        *,
        owner_token: str,
        claimed_at: datetime,
        lease_until: datetime,
    ) -> AgentTurn | None:
        turn, claimed = await self.claim_run(
            turn_id,
            owner_token=owner_token,
            claimed_at=claimed_at,
            lease_until=lease_until,
        )
        return turn if claimed else None

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

    async def renew_execution_lease(
        self,
        turn_id: str,
        *,
        owner_token: str,
        lease_until: datetime,
    ) -> AgentTurn | None:
        result = await self.session.execute(
            update(self.model)
            .where(
                self.model.id == turn_id,
                self.model.status == AgentTurnStatus.RUNNING,
                self.model.owner_token == owner_token,
            )
            .values(lease_until=lease_until)
            .returning(self.model)
            .execution_options(populate_existing=True)
        )
        renewed = result.scalar_one_or_none()
        await self.session.commit()
        return renewed

    async def lock_execution_owner(self, turn_id: str, *, owner_token: str) -> bool:
        result = await self.session.execute(
            update(self.model)
            .where(
                self.model.id == turn_id,
                self.model.status == AgentTurnStatus.RUNNING,
                self.model.owner_token == owner_token,
            )
            .values(owner_token=owner_token)
            .returning(self.model.id)
        )
        return result.scalar_one_or_none() is not None

    async def update_claimed_execution(
        self,
        turn_id: str,
        *,
        owner_token: str,
        commit: bool = True,
        **values,
    ) -> AgentTurn | None:
        result = await self.session.execute(
            update(self.model)
            .where(
                self.model.id == turn_id,
                self.model.status == AgentTurnStatus.RUNNING,
                self.model.owner_token == owner_token,
            )
            .values(**values)
            .returning(self.model)
            .execution_options(populate_existing=True)
        )
        updated = result.scalar_one_or_none()
        if commit:
            await self.session.commit()
        else:
            await self.session.flush()
        return updated

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
        return await self.get_fresh(turn_id), updated

    async def queue_waiting_for_resume(
        self,
        turn_id: str,
        *,
        resume_batch_token: str | None = None,
    ) -> bool:
        result = await self.session.execute(
            update(self.model)
            .where(
                self.model.id == turn_id,
                self.model.status.in_(
                    [AgentTurnStatus.WAITING_APPROVAL, AgentTurnStatus.RUNNING]
                ),
            )
            .values(
                claimed_at=case(
                    (self.model.status == AgentTurnStatus.WAITING_APPROVAL, None),
                    else_=self.model.claimed_at,
                ),
                lease_until=case(
                    (self.model.status == AgentTurnStatus.WAITING_APPROVAL, None),
                    else_=self.model.lease_until,
                ),
                owner_token=case(
                    (self.model.status == AgentTurnStatus.WAITING_APPROVAL, None),
                    else_=self.model.owner_token,
                ),
                resume_batch_token=func.coalesce(
                    self.model.resume_batch_token,
                    resume_batch_token,
                ),
            )
            .returning(self.model.id)
        )
        return result.scalar_one_or_none() is not None

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
            "owner_token": None,
            "resume_batch_token": None,
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

    async def create_for_owned_turn(
        self,
        *,
        turn_id: str,
        expected_owner_token: str,
        commit: bool = True,
        owner_fenced: bool = False,
        **data: Any,
    ) -> tuple[AgentMessage | None, bool]:
        return await _create_for_owned_turn(
            self.session,
            self.model,
            turn_id=turn_id,
            expected_owner_token=expected_owner_token,
            data=data,
            commit=commit,
            owner_fenced=owner_fenced,
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
            if not await _fence_owned_turn(
                self.session,
                turn_id=turn_id,
                expected_owner_token=expected_owner_token,
            ):
                await self.session.rollback()
                return None, False
            summary, owned = await _create_for_owned_turn(
                self.session,
                self.model,
                turn_id=turn_id,
                expected_owner_token=expected_owner_token,
                data=summary_data,
                commit=False,
                owner_fenced=True,
            )
            if not owned or summary is None:
                await self.session.rollback()
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
            if not await _fence_owned_turn(
                self.session,
                turn_id=turn_id,
                expected_owner_token=expected_owner_token,
            ):
                await self.session.rollback()
                return None, False
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
        result = await self.session.execute(
            select(self.model)
            .where(
                self.model.session_id == session_id,
                self.model.turn_id == turn_id,
                self.model.role == "tool",
                self.model.status == AgentMessageStatus.COMMITTED,
            )
            .order_by(desc(self.model.ordering_index), desc(self.model.id))
        )
        for message in result.scalars().all():
            if (message.message_metadata or {}).get("tool_call_id") == tool_call_id:
                return message
        return None

    async def create_replacing_turn_metadata(
        self,
        *,
        metadata_key: str,
        expected_owner_token: str | None = None,
        **data: object,
    ) -> AgentMessage | None:
        return await self._create_replacing_metadata(
            scope_field="turn_id",
            scope_id=str(data["turn_id"]),
            metadata_key=metadata_key,
            expected_owner_token=expected_owner_token,
            data=data,
        )

    async def create_replacing_session_metadata(
        self,
        *,
        metadata_key: str,
        expected_owner_token: str | None = None,
        **data: object,
    ) -> AgentMessage | None:
        return await self._create_replacing_metadata(
            scope_field="session_id",
            scope_id=str(data["session_id"]),
            metadata_key=metadata_key,
            expected_owner_token=expected_owner_token,
            data=data,
        )

    async def _create_replacing_metadata(
        self,
        *,
        scope_field: str,
        scope_id: str,
        metadata_key: str,
        expected_owner_token: str | None,
        data: dict[str, object],
    ) -> AgentMessage | None:
        turn_id = str(data["turn_id"])
        if expected_owner_token is not None:
            ensure_clean_owned_publication_session(self.session)
            if not await _fence_owned_turn(
                self.session,
                turn_id=turn_id,
                expected_owner_token=expected_owner_token,
            ):
                await self.session.rollback()
                return None
        scope_column = getattr(self.model, scope_field)
        result = await self.session.execute(
            select(self.model).where(scope_column == scope_id)
        )
        for existing in result.scalars().all():
            metadata = dict(existing.message_metadata or {})
            if metadata_key in metadata:
                metadata.pop(metadata_key)
                existing.message_metadata = metadata or None
        message = self.model(**data)
        self.session.add(message)
        await self.session.commit()
        await self.session.refresh(message)
        return message

    async def clear_turn_metadata(
        self,
        *,
        turn_id: str,
        metadata_key: str,
        expected_owner_token: str | None = None,
    ) -> bool:
        return await self._clear_metadata(
            scope_field="turn_id",
            scope_id=turn_id,
            turn_id=turn_id,
            metadata_key=metadata_key,
            expected_owner_token=expected_owner_token,
        )

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
        return await self._clear_metadata(
            scope_field="session_id",
            scope_id=session_id,
            turn_id=turn_id,
            metadata_key=metadata_key,
            expected_owner_token=expected_owner_token,
        )

    async def _clear_metadata(
        self,
        *,
        scope_field: str,
        scope_id: str,
        turn_id: str | None,
        metadata_key: str,
        expected_owner_token: str | None,
    ) -> bool:
        if expected_owner_token is not None:
            ensure_clean_owned_publication_session(self.session)
            if not await _fence_owned_turn(
                self.session,
                turn_id=str(turn_id),
                expected_owner_token=expected_owner_token,
            ):
                await self.session.rollback()
                return False
        result = await self.session.execute(
            select(self.model).where(getattr(self.model, scope_field) == scope_id)
        )
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
        return True

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

    async def create_for_owned_turn(
        self,
        *,
        turn_id: str,
        expected_owner_token: str,
        commit: bool = True,
        owner_fenced: bool = False,
        **data: Any,
    ) -> tuple[AgentEvent | None, bool]:
        return await _create_for_owned_turn(
            self.session,
            self.model,
            turn_id=turn_id,
            expected_owner_token=expected_owner_token,
            data=data,
            commit=commit,
            owner_fenced=owner_fenced,
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
        commit: bool = True,
        owner_fenced: bool = False,
        **data: Any,
    ) -> tuple[AgentAction | None, bool]:
        return await _create_for_owned_turn(
            self.session,
            self.model,
            turn_id=turn_id,
            expected_owner_token=expected_owner_token,
            data=data,
            commit=commit,
            owner_fenced=owner_fenced,
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
        if updated_id is None or not await _fence_owned_turn(
            self.session,
            turn_id=str(action.turn_id),
            expected_owner_token=expected_owner_token,
        ):
            await self.session.rollback()
            return None, False
        await self.session.commit()
        return await self.get_fresh(str(updated_id)), True

    def ensure_clean_resume_claim_session(self) -> None:
        if self.session.new or self.session.dirty or self.session.deleted:
            raise RuntimeError("Atomic action resume claim requires a clean session")

    async def claim_requested_resume(
        self,
        action_id: str,
        *,
        started_at: datetime,
        expected_owner_token: str | None = None,
    ) -> tuple[AgentAction | None, bool]:
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
            turn_id = await self.session.scalar(
                select(self.model.turn_id).where(self.model.id == action_id)
            )
            if turn_id is None or not await _fence_owned_turn(
                self.session,
                turn_id=str(turn_id),
                expected_owner_token=expected_owner_token,
            ):
                await self.session.rollback()
                claimed = False
        await self.session.commit()
        return await self.get_fresh(action_id), claimed

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
        expected_turn_owner_token: str | None = None,
    ) -> AgentAction | None:
        if expected_turn_owner_token is not None and not await self._lock_turn_owner(
            action_id,
            owner_token=expected_turn_owner_token,
        ):
            return None
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

    async def transition_running(
        self,
        action_id: str,
        *,
        status: str,
        completed_at: datetime,
        result: dict | None = None,
        output_summary: str | None = None,
        error: dict | None = None,
        expected_turn_owner_token: str | None = None,
    ) -> AgentAction | None:
        if expected_turn_owner_token is not None and not await self._lock_turn_owner(
            action_id,
            owner_token=expected_turn_owner_token,
        ):
            return None
        values = {
            "status": status,
            "completed_at": completed_at,
        }
        if result is not None:
            values["result"] = result
        if output_summary is not None:
            values["output_summary"] = output_summary
        if error is not None:
            values["error"] = error
        conditions = [
            self.model.id == action_id,
            self.model.status == AgentActionStatus.RUNNING,
        ]
        updated = await self.session.execute(
            update(self.model)
            .where(*conditions)
            .values(**values)
            .returning(self.model)
            .execution_options(populate_existing=True)
        )
        return updated.scalar_one_or_none()

    async def cancel_open(
        self,
        action_id: str,
        *,
        error: dict,
        completed_at: datetime,
        expected_turn_owner_token: str | None = None,
    ) -> AgentAction | None:
        if expected_turn_owner_token is not None and not await self._lock_turn_owner(
            action_id,
            owner_token=expected_turn_owner_token,
        ):
            return None
        updated = await self.session.execute(
            update(self.model)
            .where(
                self.model.id == action_id,
                self.model.status.in_(
                    [
                        AgentActionStatus.WAITING_DECISION,
                        AgentActionStatus.REQUESTED,
                        AgentActionStatus.RUNNING,
                    ]
                ),
            )
            .values(
                status=AgentActionStatus.CANCELLED,
                requires_resume=False,
                error=error,
                completed_at=completed_at,
            )
            .returning(self.model)
            .execution_options(populate_existing=True)
        )
        return updated.scalar_one_or_none()

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
        expected_turn_owner_token: str | None = None,
    ) -> AgentAction | None:
        if expected_turn_owner_token is not None and not await self._lock_turn_owner(
            action_id,
            owner_token=expected_turn_owner_token,
        ):
            return None
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
        risk_level: str | None = None,
        risk_reasons: list | None = None,
        affected_resources: list | None = None,
        permission_decision: dict | None = None,
        evaluated_policy_version: int | None = None,
        permission_context_snapshot: dict | None = None,
        expected_turn_owner_token: str | None = None,
    ) -> AgentAction | None:
        if expected_turn_owner_token is not None and not await self._lock_turn_owner(
            action_id,
            owner_token=expected_turn_owner_token,
        ):
            return None
        values = {
            "status": AgentActionStatus.FAILED,
            "requires_resume": False,
            "error": error,
            "completed_at": completed_at,
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
        result = await self.session.execute(
            update(self.model)
            .where(
                self.model.id == action_id,
                self.model.status == AgentActionStatus.REQUESTED,
            )
            .values(**values)
            .returning(self.model)
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def _lock_turn_owner(self, action_id: str, *, owner_token: str) -> bool:
        turn_id = await self.session.scalar(
            select(self.model.turn_id).where(self.model.id == action_id)
        )
        if turn_id is None:
            return False
        return await AgentTurnRepository(self.session).lock_execution_owner(
            str(turn_id),
            owner_token=owner_token,
        )


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
        existing_max = (
            select(func.coalesce(func.max(self.model.batch_ordinal), 0))
            .where(self.model.turn_id == turn_id)
            .scalar_subquery()
        )
        result = await self.session.execute(
            update(AgentTurn)
            .where(AgentTurn.id == turn_id)
            .values(
                tool_batch_sequence=case(
                    (
                        AgentTurn.tool_batch_sequence < existing_max,
                        existing_max + 1,
                    ),
                    else_=AgentTurn.tool_batch_sequence + 1,
                )
            )
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

    async def create_for_owned_turn(
        self,
        *,
        turn_id: str,
        expected_owner_token: str,
        commit: bool = True,
        owner_fenced: bool = False,
        **data: Any,
    ) -> tuple[AgentArtifact | None, bool]:
        return await _create_for_owned_turn(
            self.session,
            self.model,
            turn_id=turn_id,
            expected_owner_token=expected_owner_token,
            data=data,
            commit=commit,
            owner_fenced=owner_fenced,
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
