from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, exists, or_, select, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.run import Run, RunStatus
from app.schemas.run import RunErrorCode, RunErrorStage
from app.scheduler.models import ScheduledTask, TaskState
from app.utils.logging import get_logger
from app.utils.time import duration_seconds, utc_now


logger = get_logger(__name__)

RUN_ACTIVE_STATUSES = (
    RunStatus.PENDING.value,
    RunStatus.QUEUED.value,
    RunStatus.PREPARING.value,
    RunStatus.RUNNING.value,
)


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


async def recover_orphan_runs(
    session: AsyncSession,
    *,
    stale_timeout_minutes: int,
    worker_heartbeat_grace_seconds: int | None,
    scheduled_tasks_available: bool,
    include_error_details: bool = True,
) -> list[Run]:
    """Recover active runs that no longer have a live execution owner.

    The scheduler and the legacy runtime entry point both use this coordinator.
    ``scheduled_tasks_available=False`` preserves the legacy compatibility mode:
    it applies the same run staleness policy without querying the task table.
    """
    stale_cutoff = utc_now() - timedelta(minutes=stale_timeout_minutes)
    heartbeat_cutoff = None
    if worker_heartbeat_grace_seconds is not None:
        heartbeat_cutoff = utc_now() - timedelta(
            seconds=worker_heartbeat_grace_seconds
        )

    try:
        stale_condition = or_(
            and_(
                Run.started_at.is_not(None),
                Run.started_at <= stale_cutoff,
            ),
            and_(Run.started_at.is_(None), Run.created_at <= stale_cutoff),
        )
        if heartbeat_cutoff is not None:
            stale_condition = or_(
                stale_condition,
                and_(
                    Run.status == RunStatus.RUNNING.value,
                    Run.last_heartbeat_at.is_not(None),
                    Run.last_heartbeat_at <= heartbeat_cutoff,
                ),
            )

        stmt = select(Run).where(
            Run.status.in_([RunStatus.QUEUED.value, RunStatus.RUNNING.value]),
            stale_condition,
        )
        task_exists = None
        if scheduled_tasks_available:
            task_exists = exists(
                select(ScheduledTask.id).where(
                    ScheduledTask.run_id == Run.run_id,
                    ScheduledTask.state.in_(
                        [TaskState.QUEUED.value, TaskState.DISPATCHED.value]
                    ),
                )
            )
            stmt = stmt.where(~task_exists)

        result = await session.execute(stmt)
        stale_runs = result.scalars().all()
        recovered_runs: list[Run] = []

        for run in stale_runs:
            heartbeat_stale = (
                heartbeat_cutoff is not None
                and run.last_heartbeat_at is not None
                and _ensure_utc(run.last_heartbeat_at) <= heartbeat_cutoff
            )
            if heartbeat_stale:
                error_message = "Worker heartbeat lost; marking run as failed"
                error_json = {
                    "stage": RunErrorStage.EXECUTION,
                    "code": RunErrorCode.WORKER_LOST,
                    "message": error_message,
                    "hint": "The worker handling this run stopped responding. "
                    "Retry to start a new run.",
                }
            else:
                error_message = "Run recovery: marked stale after service restart"
                error_json = {
                    "stage": RunErrorStage.EXECUTION,
                    "code": RunErrorCode.RUN_STALE,
                    "message": error_message,
                    "hint": "The scheduler restarted while this run was in flight.",
                }
            if not include_error_details:
                error_json = None

            completed_at = utc_now()
            run_duration_seconds = duration_seconds(run.started_at, completed_at)
            update_conditions = [
                Run.run_id == run.run_id,
                Run.status.in_(RUN_ACTIVE_STATUSES),
                stale_condition,
            ]
            if task_exists is not None:
                update_conditions.append(~task_exists)

            with session.no_autoflush:
                update_result = await session.execute(
                    update(Run)
                    .where(*update_conditions)
                    .execution_options(synchronize_session=False)
                    .values(
                        status=RunStatus.FAILED.value,
                        error_message=error_message,
                        error_json=error_json,
                        completed_at=completed_at,
                        duration_seconds=run_duration_seconds,
                    )
                )
            if update_result.rowcount == 1:
                recovered_runs.append(run)

        if recovered_runs:
            await session.commit()
            for run in recovered_runs:
                await session.refresh(run)
        else:
            await session.rollback()
    except OperationalError as exc:
        if "no such table: runs" not in str(exc).lower():
            raise
        logger.info("scheduler.recovery.skipped_missing_runs_table")
        return []

    return recovered_runs
