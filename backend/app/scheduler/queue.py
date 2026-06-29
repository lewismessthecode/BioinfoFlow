from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from sqlalchemy import case, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

import app.database as app_database
from app.scheduler.models import ScheduledTask, TaskPriority, TaskState


def _now() -> datetime:
    return datetime.now(timezone.utc)


class TaskQueue:
    model = ScheduledTask

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        self._session_factory = session_factory or app_database.async_session_maker
        self._claim_lock = asyncio.Lock()

    async def get(self, task_id: str) -> ScheduledTask | None:
        async with self._session_factory() as session:
            return await session.get(ScheduledTask, task_id)

    async def get_active_for_run(self, run_id: str) -> ScheduledTask | None:
        async with self._session_factory() as session:
            stmt = (
                select(ScheduledTask)
                .where(
                    ScheduledTask.run_id == run_id,
                    ScheduledTask.state.in_(
                        [TaskState.QUEUED.value, TaskState.DISPATCHED.value]
                    ),
                )
                .order_by(ScheduledTask.created_at.desc())
            )
            result = await session.execute(stmt)
            return result.scalars().first()

    async def enqueue(
        self,
        run_id: str,
        *,
        priority: str = TaskPriority.NORMAL.value,
        attempt: int = 1,
        max_attempts: int = 1,
        delay_until: datetime | None = None,
        weight: int = 1,
    ) -> ScheduledTask:
        async with self._session_factory() as session:
            existing = await self._get_active_for_run(session, run_id)
            if existing:
                return existing

            task = ScheduledTask(
                run_id=run_id,
                priority=priority,
                attempt=attempt,
                max_attempts=max_attempts,
                delay_until=delay_until,
                weight=max(1, weight),
            )
            session.add(task)
            try:
                await session.commit()
            except IntegrityError as exc:
                await session.rollback()
                if not _is_active_task_integrity_error(exc):
                    raise
                existing = await self._get_active_for_run(session, run_id)
                if existing:
                    return existing
                raise
            await session.refresh(task)
            return task

    async def dequeue(self) -> ScheduledTask | None:
        async with self._claim_lock:
            async with self._session_factory() as session:
                return await self._dequeue_in_session(session)

    async def claim_next(self, worker_id: str) -> ScheduledTask | None:
        async with self._claim_lock:
            async with self._session_factory() as session:
                return await self._claim_next_in_session(session, worker_id=worker_id)

    async def claim_next_fitting(
        self, worker_id: str, available_slots: int
    ) -> ScheduledTask | None:
        """Claim the first queued task whose weight fits available slots.

        Uses backfill scheduling: scans in priority+FIFO order but skips
        tasks whose weight exceeds available slots.
        """
        async with self._claim_lock:
            async with self._session_factory() as session:
                return await self._claim_next_in_session(
                    session,
                    worker_id=worker_id,
                    max_weight=available_slots,
                )

    async def get_dispatched_summaries(self) -> list[tuple[str, int]]:
        """Return (run_id, weight) for all DISPATCHED tasks."""
        async with self._session_factory() as session:
            stmt = select(ScheduledTask.run_id, ScheduledTask.weight).where(
                ScheduledTask.state == TaskState.DISPATCHED.value
            )
            result = await session.execute(stmt)
            return list(result.all())

    async def depth(self) -> int:
        async with self._session_factory() as session:
            stmt = (
                select(func.count())
                .select_from(ScheduledTask)
                .where(ScheduledTask.state == TaskState.QUEUED.value)
            )
            return int(await session.scalar(stmt) or 0)

    async def state_counts(self) -> dict[str, int]:
        async with self._session_factory() as session:
            stmt = select(ScheduledTask.state, func.count()).group_by(
                ScheduledTask.state
            )
            result = await session.execute(stmt)
            return {state: count for state, count in result.all()}

    async def cancel(self, run_id: str) -> bool:
        async with self._session_factory() as session:
            task = await self._get_active_for_run(session, run_id)
            if not task:
                return False
            await self._mark_terminal(
                session,
                task_id=task.id,
                state=TaskState.CANCELLED.value,
            )
            return True

    async def mark_dispatched(
        self,
        task_id: str,
        worker_id: str,
        *,
        dispatched_at: datetime | None = None,
    ) -> ScheduledTask | None:
        async with self._session_factory() as session:
            now = dispatched_at or _now()
            result = await session.execute(
                update(ScheduledTask)
                .where(
                    ScheduledTask.id == task_id,
                    ScheduledTask.state == TaskState.QUEUED.value,
                )
                .values(
                    state=TaskState.DISPATCHED.value,
                    worker_id=worker_id,
                    dispatched_at=now,
                    delay_until=None,
                )
            )
            if result.rowcount != 1:
                await session.rollback()
                return None
            await session.commit()
            task = await session.get(ScheduledTask, task_id)
            if task is None:
                return None
            await session.refresh(task)
            return task

    async def mark_completed(
        self,
        task_id: str,
        *,
        completed_at: datetime | None = None,
    ) -> ScheduledTask | None:
        async with self._session_factory() as session:
            return await self._mark_terminal(
                session,
                task_id=task_id,
                state=TaskState.COMPLETED.value,
                completed_at=completed_at,
            )

    async def mark_failed(
        self,
        task_id: str,
        error: str,
        *,
        completed_at: datetime | None = None,
    ) -> ScheduledTask | None:
        async with self._session_factory() as session:
            return await self._mark_terminal(
                session,
                task_id=task_id,
                state=TaskState.FAILED.value,
                error=error,
                completed_at=completed_at,
            )

    async def mark_cancelled(
        self,
        task_id: str,
        *,
        completed_at: datetime | None = None,
    ) -> ScheduledTask | None:
        async with self._session_factory() as session:
            return await self._mark_terminal(
                session,
                task_id=task_id,
                state=TaskState.CANCELLED.value,
                completed_at=completed_at,
            )

    async def re_enqueue(
        self,
        task_id: str,
        *,
        attempt: int,
        delay_until: datetime | None = None,
        error: str | None = None,
    ) -> ScheduledTask | None:
        async with self._session_factory() as session:
            values = {
                "state": TaskState.QUEUED.value,
                "attempt": attempt,
                "delay_until": delay_until,
                "dispatched_at": None,
                "completed_at": None,
                "worker_id": None,
            }
            if error is not None:
                values["error_message"] = error
            result = await session.execute(
                update(ScheduledTask)
                .where(
                    ScheduledTask.id == task_id,
                    ScheduledTask.state == TaskState.DISPATCHED.value,
                    ScheduledTask.max_attempts >= attempt,
                )
                .values(**values)
            )
            if result.rowcount != 1:
                await session.rollback()
                return None
            await session.commit()
            task = await session.get(ScheduledTask, task_id)
            if task is None:
                return None
            await session.refresh(task)
            return task

    async def get_stale(self, timeout_minutes: int) -> list[ScheduledTask]:
        cutoff = _now() - timedelta(minutes=timeout_minutes)
        async with self._session_factory() as session:
            stmt = select(ScheduledTask).where(
                ScheduledTask.state == TaskState.DISPATCHED.value,
                ScheduledTask.dispatched_at.is_not(None),
                ScheduledTask.dispatched_at <= cutoff,
            )
            result = await session.execute(stmt)
            return list(result.scalars().all())

    async def _dequeue_in_session(
        self,
        session: AsyncSession,
        max_weight: int | None = None,
    ) -> ScheduledTask | None:
        priority_rank = case(
            (ScheduledTask.priority == TaskPriority.URGENT.value, 0),
            (ScheduledTask.priority == TaskPriority.NORMAL.value, 1),
            else_=2,
        )
        conditions = [
            ScheduledTask.state == TaskState.QUEUED.value,
            or_(
                ScheduledTask.delay_until.is_(None),
                ScheduledTask.delay_until <= _now(),
            ),
        ]
        if max_weight is not None:
            conditions.append(ScheduledTask.weight <= max(1, max_weight))
        stmt = (
            select(ScheduledTask)
            .where(*conditions)
            .order_by(priority_rank.asc(), ScheduledTask.created_at.asc())
        )
        result = await session.execute(stmt)
        return result.scalars().first()

    async def _claim_next_in_session(
        self,
        session: AsyncSession,
        *,
        worker_id: str,
        max_weight: int | None = None,
    ) -> ScheduledTask | None:
        while True:
            task = await self._dequeue_in_session(session, max_weight=max_weight)
            if not task:
                return None
            dispatched_at = _now()
            result = await session.execute(
                update(ScheduledTask)
                .where(
                    ScheduledTask.id == task.id,
                    ScheduledTask.state == TaskState.QUEUED.value,
                )
                .values(
                    state=TaskState.DISPATCHED.value,
                    worker_id=worker_id,
                    dispatched_at=dispatched_at,
                    delay_until=None,
                )
            )
            if result.rowcount == 1:
                await session.commit()
                claimed = await session.get(ScheduledTask, task.id)
                if claimed is None:
                    return None
                await session.refresh(claimed)
                return claimed
            await session.rollback()

    async def _get_active_for_run(
        self,
        session: AsyncSession,
        run_id: str,
    ) -> ScheduledTask | None:
        stmt = (
            select(ScheduledTask)
            .where(
                ScheduledTask.run_id == run_id,
                ScheduledTask.state.in_(
                    [TaskState.QUEUED.value, TaskState.DISPATCHED.value]
                ),
            )
            .order_by(ScheduledTask.created_at.desc())
        )
        result = await session.execute(stmt)
        return result.scalars().first()

    async def _mark_terminal(
        self,
        session: AsyncSession,
        *,
        task_id: str,
        state: str,
        error: str | None = None,
        completed_at: datetime | None = None,
    ) -> ScheduledTask | None:
        values = {
            "state": state,
            "completed_at": completed_at or _now(),
            "delay_until": None,
        }
        if error is not None:
            values["error_message"] = error
        result = await session.execute(
            update(ScheduledTask)
            .where(
                ScheduledTask.id == task_id,
                ScheduledTask.state.in_(
                    [TaskState.QUEUED.value, TaskState.DISPATCHED.value]
                ),
            )
            .values(**values)
        )
        if result.rowcount != 1:
            await session.rollback()
            return None
        await session.commit()
        task = await session.get(ScheduledTask, task_id)
        if task is None:
            return None
        await session.refresh(task)
        return task


def _is_active_task_integrity_error(exc: IntegrityError) -> bool:
    constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", "")
    if constraint == "uq_scheduled_tasks_active_run":
        return True
    text = str(exc.orig).lower()
    return (
        "uq_scheduled_tasks_active_run" in text
        or "unique constraint failed: scheduled_tasks.run_id" in text
    )
