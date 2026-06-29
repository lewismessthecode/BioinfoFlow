from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import app.database as app_database
from sqlalchemy import and_, exists, func, or_, select, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.engine.backend import EngineEventType, ExecutionBackend
from app.engine.local import LocalBackend
from app.engine.registry import get_adapter
from app.models.run import Run, RunStatus
from app.models.run_config import RunConfigHelper
from app.schemas.run import RunErrorCode, RunErrorStage
from app.models.workflow import Workflow, WorkflowEngine
from app.path_layout import project_home, run_audit_root, run_engine_workspace
from app.repositories.project_repo import ProjectRepository
from app.repositories.run_repo import RunRepository
from app.runtime.events import publish_run_dag, publish_run_status
from app.runtime.jobs import (
    _build_engine_config,
    _duration_seconds,
    _finalize_dag_statuses,
    _handle_engine_event,
    _now,
    attach_required_image_auth,
    initialize_run_dag,
)
from app.scheduler.config import SchedulerConfig
from app.scheduler.hooks import RunCompletionHooks
from app.scheduler.models import ScheduledTask, TaskState
from app.scheduler.monitor import ResourceMonitor
from app.scheduler.queue import TaskQueue
from app.scheduler.resources import SystemResources
from app.scheduler.slots import SlotTracker
from app.scheduler.retry import RetryEvaluator
from app.scheduler.timeout import TimeoutWatcher
from app.services.run_service import RunService
from app.utils.logging import get_logger


logger = get_logger(__name__)


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


DEFAULT_STATE_COUNTS = {
    "queued": 0,
    "dispatched": 0,
    "completed": 0,
    "failed": 0,
    "cancelled": 0,
}

RUN_ACTIVE_STATUSES = (
    RunStatus.PENDING.value,
    RunStatus.QUEUED.value,
    RunStatus.PREPARING.value,
    RunStatus.RUNNING.value,
)


@dataclass(frozen=True, slots=True)
class ExecutionLease:
    task_id: str
    run_id: str
    worker_id: str | None
    attempt: int
    dispatched_at: datetime | None


class QueueFullError(RuntimeError):
    pass


class SchedulerStorageUnavailableError(RuntimeError):
    """Raised when scheduler persistence tables are not available."""

    pass


class RunScheduler:
    """Persistent DB-backed run scheduler."""

    RESOURCE_WAIT_SECONDS = 30

    def __init__(
        self,
        *,
        config: SchedulerConfig,
        backend: ExecutionBackend | None = None,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
        queue: TaskQueue | None = None,
        monitor: ResourceMonitor | None = None,
    ) -> None:
        self.config = config
        self._backend = backend or LocalBackend()
        self._session_factory = session_factory or app_database.async_session_maker
        self._queue = queue or TaskQueue(session_factory=self._session_factory)
        self._slots = SlotTracker(config.effective_total_slots())
        # Optional resource monitor (for the /scheduler/resources display API only)
        self._monitor = monitor
        self._workers: list[asyncio.Task] = []
        self._running = False
        self._scheduled_tasks_available = True
        self._timeout_watcher = TimeoutWatcher(
            scheduler=self,
            session_factory=self._session_factory,
            check_interval=max(1.0, self.config.poll_interval_seconds),
        )

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        await self.recover()
        if not self._scheduled_tasks_available:
            self._running = False
            raise SchedulerStorageUnavailableError(
                "scheduled_tasks table is missing; apply backend migrations or use legacy scheduler mode"
            )
        if self._monitor is not None:
            await self._monitor.start()
        await self._timeout_watcher.start()
        for worker_id in range(self.config.effective_max_workers()):
            self._workers.append(asyncio.create_task(self._worker(worker_id)))

    async def stop(self) -> None:
        self._running = False
        await self._timeout_watcher.stop()
        if self._monitor is not None:
            await self._monitor.stop()
        for worker in self._workers:
            worker.cancel()
        if self._workers:
            await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()

    async def enqueue(self, run_id: str, *, priority: str = "normal") -> ScheduledTask:
        existing = await self._queue.get_active_for_run(run_id)
        if existing is not None:
            return existing
        depth = await self._queue.depth()
        if depth >= self.config.max_queue_depth:
            logger.warning(
                "scheduler.queue.full",
                run_id=run_id,
                depth=depth,
                max_queue_depth=self.config.max_queue_depth,
            )
            raise QueueFullError("run scheduler queue is full")
        max_attempts = 1
        weight = 1
        async with self._session_factory() as session:
            run = await RunRepository(session).get_by_run_id(run_id)
            if run is None:
                raise ValueError("run not found")
            if run.status not in {
                RunStatus.PENDING.value,
                RunStatus.QUEUED.value,
            }:
                raise ValueError(f"run is not schedulable from status {run.status}")
            retry_policy = RunConfigHelper(run.config).retry_policy
            max_attempts += max(0, int(retry_policy.get("max_retries", 0) or 0))
            if run.workflow_id:
                w = await session.scalar(
                    select(Workflow.weight).where(Workflow.id == run.workflow_id)
                )
                weight = w or 1
        return await self._queue.enqueue(
            run_id,
            priority=priority,
            max_attempts=max_attempts,
            weight=weight,
        )

    async def cancel(self, run_id: str, *, reason: str | None = None) -> bool:
        task = await self._queue.get_active_for_run(run_id)
        if not task:
            return False

        async with self._session_factory() as session:
            repo = RunRepository(session)
            run = await repo.get_by_run_id(run_id)
            if not run:
                return False
            workspace_path, engine = await self._resolve_run_context(session, run)
            workspace_path_str = str(workspace_path) if workspace_path else None

            if (
                task.state == TaskState.DISPATCHED.value
                and run.status == RunStatus.RUNNING.value
            ):
                workflow = await session.get(Workflow, run.workflow_id)
                if not workflow:
                    return False
                adapter = get_adapter(
                    getattr(workflow.engine, "value", workflow.engine)
                )
                cancelled = await self._backend.cancel(
                    adapter,
                    pid=RunConfigHelper(run.config).pid,
                    run_name=run.nextflow_run_name,
                )
                if not cancelled:
                    return False

            completed_at = _now()
            run.status = RunStatus.CANCELLED.value
            if reason:
                run.error_message = reason
            run.completed_at = completed_at
            run.duration_seconds = _duration_seconds(run.started_at, completed_at)
            if workspace_path_str:
                await _finalize_dag_statuses(run, workspace_path=workspace_path_str)
            run_updated = await self._transition_run_terminal_in_session(
                session,
                run,
                status=RunStatus.CANCELLED.value,
                completed_at=completed_at,
                error_message=run.error_message,
            )
            task_updated = await self._mark_task_terminal_in_session(
                session,
                task_id=task.id,
                state=TaskState.CANCELLED.value,
                completed_at=completed_at,
            )
            if not run_updated or not task_updated:
                await session.rollback()
                return False
            await session.commit()
            await session.refresh(run)
            if workspace_path_str and engine:
                await self._hooks(session).on_run_terminal(
                    run,
                    status=RunStatus.CANCELLED.value,
                    workspace_path=workspace_path_str,
                    engine=engine,
                )

        await publish_run_status(run, message=reason or "Run cancelled")
        await publish_run_dag(run)
        return True

    async def recover(self) -> int:
        stale_task_count = await self._recover_stale_tasks()
        orphan_run_count = await self._recover_orphan_runs()
        used = await self._compute_used_slots()
        dispatched_count = await self._compute_dispatched_task_count()
        self._slots.sync_from_db(used)
        logger.info(
            "scheduler.slots.recovered",
            dispatched_count=dispatched_count,
            total=self._slots.total,
            used=self._slots.used,
            available=self._slots.available,
        )
        return stale_task_count + orphan_run_count

    async def _compute_used_slots(self) -> int:
        """Derive used slot count from DISPATCHED tasks in DB."""
        try:
            async with self._session_factory() as session:
                stmt = select(func.coalesce(func.sum(ScheduledTask.weight), 0)).where(
                    ScheduledTask.state == TaskState.DISPATCHED.value
                )
                return int(await session.scalar(stmt) or 0)
        except OperationalError:
            return 0

    async def _compute_dispatched_task_count(self) -> int:
        """Count DISPATCHED task rows in DB."""
        try:
            async with self._session_factory() as session:
                stmt = (
                    select(func.count())
                    .select_from(ScheduledTask)
                    .where(ScheduledTask.state == TaskState.DISPATCHED.value)
                )
                return int(await session.scalar(stmt) or 0)
        except OperationalError:
            return 0

    async def _recover_stale_tasks(self) -> int:
        """Fail scheduler tasks that exceeded the stale timeout."""
        self._scheduled_tasks_available = True
        try:
            stale_tasks = await self._queue.get_stale(self.config.stale_timeout_minutes)
        except OperationalError as exc:
            if "no such table: scheduled_tasks" not in str(exc).lower():
                raise
            self._scheduled_tasks_available = False
            logger.info("scheduler.recovery.skipped_missing_scheduled_tasks_table")
            return 0

        recovered = 0
        stale_cutoff = _now() - timedelta(minutes=self.config.stale_timeout_minutes)
        for task in stale_tasks:
            async with self._session_factory() as session:
                run = await RunRepository(session).get_by_run_id(task.run_id)
                message = (
                    "Run recovery: run missing"
                    if not run
                    else "Run recovery: marked stale after service restart"
                )
                completed_at = _now()
                task_updated = await self._mark_stale_task_failed_in_session(
                    session,
                    task=task,
                    error=message,
                    completed_at=completed_at,
                    stale_cutoff=stale_cutoff,
                )
                if not task_updated:
                    await session.rollback()
                    continue
                if not run:
                    await session.commit()
                    recovered += 1
                    continue

                run.duration_seconds = _duration_seconds(run.started_at, completed_at)
                run.error_message = message
                run_updated = await self._transition_run_terminal_in_session(
                    session,
                    run,
                    status=RunStatus.FAILED.value,
                    completed_at=completed_at,
                    error_message=message,
                )
                if not run_updated:
                    await session.rollback()
                    continue
                await session.commit()
                await session.refresh(run)

            await publish_run_status(run, message=message)
            recovered += 1
        return recovered

    async def _recover_orphan_runs(self) -> int:
        """Fail runs stuck in QUEUED/RUNNING with no active scheduler task.

        Two detection signals:
        * coarse: started_at / created_at older than ``stale_timeout_minutes``
        * fine-grained: worker heartbeat older than ``worker_heartbeat_grace_seconds``
          for a run in RUNNING state — indicates the worker died mid-execution.
        """
        stale_cutoff = _now() - timedelta(minutes=self.config.stale_timeout_minutes)
        heartbeat_cutoff = _now() - timedelta(
            seconds=self.config.worker_heartbeat_grace_seconds
        )
        try:
            async with self._session_factory() as session:
                stale_condition = or_(
                    and_(
                        Run.started_at.is_not(None),
                        Run.started_at <= stale_cutoff,
                    ),
                    and_(Run.started_at.is_(None), Run.created_at <= stale_cutoff),
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
                active_task_absent = None
                if self._scheduled_tasks_available:
                    task_exists = exists(
                        select(ScheduledTask.id).where(
                            ScheduledTask.run_id == Run.run_id,
                            ScheduledTask.state.in_(
                                [TaskState.QUEUED.value, TaskState.DISPATCHED.value]
                            ),
                        )
                    )
                    active_task_absent = ~task_exists
                    stmt = stmt.where(~task_exists)

                result = await session.execute(stmt)
                stale_runs = result.scalars().all()

                recovered_runs: list[Run] = []
                for run in stale_runs:
                    heartbeat_stale = (
                        run.last_heartbeat_at is not None
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
                        error_message = (
                            "Run recovery: marked stale after service restart"
                        )
                        error_json = {
                            "stage": RunErrorStage.EXECUTION,
                            "code": RunErrorCode.RUN_STALE,
                            "message": error_message,
                            "hint": "The scheduler restarted while this run was in flight.",
                        }
                    completed_at = _now()
                    duration_seconds = _duration_seconds(run.started_at, completed_at)
                    with session.no_autoflush:
                        update_conditions = [
                            Run.run_id == run.run_id,
                            Run.status.in_(RUN_ACTIVE_STATUSES),
                            stale_condition,
                        ]
                        if active_task_absent is not None:
                            update_conditions.append(active_task_absent)
                        update_result = await session.execute(
                            update(Run)
                            .where(*update_conditions)
                            .values(
                                status=RunStatus.FAILED.value,
                                error_message=error_message,
                                error_json=error_json,
                                completed_at=completed_at,
                                duration_seconds=duration_seconds,
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
            return 0

        for run in recovered_runs:
            await publish_run_status(run, message=run.error_message or "Run failed")

        return len(recovered_runs)

    async def get_status(self) -> dict[str, object]:
        state_counts = {
            **DEFAULT_STATE_COUNTS,
            **await self._queue.state_counts(),
        }
        dispatched = await self._queue.get_dispatched_summaries()
        return {
            "workers": self.config.effective_max_workers(),
            "queue_depth": await self._queue.depth(),
            "resource_monitoring_enabled": self._monitor is not None,
            "states": state_counts,
            "total_slots": self._slots.total,
            "used_slots": self._slots.used,
            "available_slots": self._slots.available,
            "config": {
                "total_slots": self.config.effective_total_slots(),
                "max_workers": self.config.effective_max_workers(),
                "max_queue_depth": self.config.max_queue_depth,
                "poll_interval_seconds": self.config.poll_interval_seconds,
                "stale_timeout_minutes": self.config.stale_timeout_minutes,
                "worker_heartbeat_grace_seconds": self.config.worker_heartbeat_grace_seconds,
                "resource_check_enabled": self.config.resource_check_enabled,
            },
            "active_runs": [
                {"run_id": run_id, "weight": weight} for run_id, weight in dispatched
            ],
        }

    def get_resource_snapshot(self) -> SystemResources | None:
        if self._monitor is None:
            return None
        try:
            return self._monitor.current()
        except Exception:  # noqa: BLE001
            logger.exception("scheduler.resource_snapshot.failed")
            return None

    async def execute_run(self, run_id: str, *, worker_id: str = "legacy") -> None:
        await self._execute_run_id(run_id, worker_id=worker_id)

    async def _start_run_in_session(
        self,
        session: AsyncSession,
        run: Run,
        *,
        task_id: str | None,
        worker_id: str,
    ) -> tuple[bool, ExecutionLease | None]:
        started_at = run.started_at or _now()
        lease: ExecutionLease | None = None
        with session.no_autoflush:
            if task_id:
                task_result = await session.execute(
                    select(ScheduledTask).where(
                        ScheduledTask.id == task_id,
                        ScheduledTask.run_id == run.run_id,
                        ScheduledTask.state == TaskState.DISPATCHED.value,
                        ScheduledTask.worker_id == worker_id,
                    )
                )
                task = task_result.scalars().first()
                if task is None:
                    await session.rollback()
                    return False, None
                lease = ExecutionLease(
                    task_id=task.id,
                    run_id=task.run_id,
                    worker_id=task.worker_id,
                    attempt=task.attempt,
                    dispatched_at=task.dispatched_at,
                )

            result = await session.execute(
                update(Run)
                .where(
                    Run.run_id == run.run_id,
                    Run.status.in_([RunStatus.PENDING.value, RunStatus.QUEUED.value]),
                )
                .values(
                    status=RunStatus.RUNNING.value,
                    started_at=started_at,
                    completed_at=None,
                    duration_seconds=None,
                    error_message=None,
                )
            )
        if result.rowcount != 1:
            await session.rollback()
            return False, None
        await session.commit()
        await session.refresh(run)
        return True, lease

    async def _worker(self, worker_index: int) -> None:
        worker_id = f"worker-{worker_index}"
        while self._running:
            try:
                task = await self._queue.claim_next_fitting(
                    worker_id, self._slots.available
                )
                if not task:
                    await asyncio.sleep(self.config.poll_interval_seconds)
                    continue
                # try_acquire closes the race against the stale
                # available-snapshot we passed into claim_next_fitting:
                # another worker may have consumed the slot while we
                # were waiting on the claim lock. If so, put the task
                # back on the queue so a worker with free capacity can
                # pick it up on the next poll.
                if not self._slots.try_acquire(task.weight):
                    await self._queue.re_enqueue(task.id, attempt=task.attempt)
                    logger.info(
                        "scheduler.slot.race_re_enqueued",
                        task_id=task.id,
                        weight=task.weight,
                        available=self._slots.available,
                    )
                    await asyncio.sleep(self.config.poll_interval_seconds)
                    continue
                logger.debug(
                    "scheduler.slot.acquired",
                    worker_id=worker_id,
                    task_id=task.id,
                    weight=task.weight,
                    used=self._slots.used,
                    available=self._slots.available,
                )
                try:
                    await self._execute_run_id(
                        task.run_id, task_id=task.id, worker_id=worker_id
                    )
                finally:
                    self._slots.release(task.weight)
                    logger.debug(
                        "scheduler.slot.released",
                        worker_id=worker_id,
                        task_id=task.id,
                        weight=task.weight,
                        used=self._slots.used,
                        available=self._slots.available,
                    )
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                logger.exception("scheduler.worker.task_error", worker_id=worker_id)

    async def _execute_run_id(
        self,
        run_id: str,
        *,
        task_id: str | None = None,
        worker_id: str,
    ) -> None:
        logger.info("scheduler.execute.start", run_id=run_id, worker_id=worker_id)
        async with self._session_factory() as session:
            repo = RunRepository(session)
            run_service = RunService(session)
            run = await repo.get_by_run_id(run_id)
            if not run:
                if task_id:
                    await self._queue.mark_failed(task_id, "Run not found")
                return

            if run.status == RunStatus.CANCELLED.value:
                if task_id:
                    await self._queue.mark_cancelled(task_id)
                return
            if run.status not in {RunStatus.PENDING.value, RunStatus.QUEUED.value}:
                if task_id:
                    await self._queue.mark_failed(
                        task_id,
                        f"Run is not executable from status {run.status}",
                    )
                return

            started, lease = await self._start_run_in_session(
                session,
                run,
                task_id=task_id,
                worker_id=worker_id,
            )
            if not started:
                return
            await publish_run_status(run, message="Run started")

            workflow = await session.get(Workflow, run.workflow_id)
            if not workflow:
                await self._fail_run(
                    session,
                    run,
                    "Workflow not found",
                    task_id=task_id,
                    lease=lease,
                    workspace_path=None,
                    engine=None,
                )
                return

            project_repo = ProjectRepository(session)
            project = await project_repo.get(run.project_id)
            if not project:
                await self._fail_run(
                    session,
                    run,
                    "Project not found",
                    task_id=task_id,
                    lease=lease,
                    workspace_path=None,
                    engine=None,
                )
                return

            workspace_path = project_home(project)

            engine_value = getattr(workflow.engine, "value", workflow.engine)
            if engine_value not in {
                WorkflowEngine.NEXTFLOW.value,
                WorkflowEngine.WDL.value,
            }:
                await self._fail_run(
                    session,
                    run,
                    "Unsupported workflow engine",
                    task_id=task_id,
                    lease=lease,
                    workspace_path=str(workspace_path),
                    engine=str(engine_value),
                )
                return

            ws_path = str(workspace_path)
            eng = str(engine_value)

            artifacts_dir = run_audit_root(project, run.run_id)
            artifacts_dir.mkdir(parents=True, exist_ok=True)
            dag_path = artifacts_dir / "dag.dot"
            trace_path = artifacts_dir / "trace.tsv"
            engine_work_dir = run_engine_workspace(
                project, run.run_id, str(engine_value)
            )

            runtime = dict(
                (run.config if isinstance(run.config, dict) else {}).get("runtime", {})
                or {}
            )
            runtime["dag_path"] = str(dag_path.relative_to(workspace_path))
            runtime["trace_path"] = str(trace_path.relative_to(workspace_path))
            runtime["work_dir"] = str(engine_work_dir.relative_to(workspace_path))
            if engine_value == WorkflowEngine.WDL.value:
                runtime["wdl_work_dir"] = str(
                    engine_work_dir.relative_to(workspace_path)
                )
                resume_work_dir = (
                    (run.config or {}).get("resume_work_dir")
                    if isinstance(run.config, dict)
                    else None
                )
                if isinstance(resume_work_dir, str) and resume_work_dir.strip():
                    runtime["resume_source_work_dir"] = resume_work_dir.strip()
            base = dict(run.config) if isinstance(run.config, dict) else {}
            run.config = {**base, "runtime": runtime}

            await initialize_run_dag(session, run, workflow, ws_path)

            adapter = get_adapter(engine_value)
            config = _build_engine_config(
                run=run,
                workflow=workflow,
                workspace_path=workspace_path,
                dag_path=dag_path,
                trace_path=trace_path,
            )
            config = await attach_required_image_auth(session, config)

            try:
                async for event in self._backend.submit(adapter, config, ws_path):
                    if not await self._execution_lease_active(session, lease):
                        await session.rollback()
                        return
                    run.last_heartbeat_at = _now()
                    if event.type == EngineEventType.ERROR:
                        await _handle_engine_event(
                            session,
                            run,
                            run_service,
                            event,
                            ws_path,
                            finalize_error=False,
                        )
                        await self._handle_task_failure(
                            session,
                            run,
                            task_id=task_id,
                            lease=lease,
                            error=run.error_message or event.message or "Run failed",
                            workspace_path=ws_path,
                            engine=eng,
                        )
                        return
                    if event.type == EngineEventType.COMPLETED:
                        await self._complete_run(
                            session,
                            run,
                            task_id=task_id,
                            lease=lease,
                            workspace_path=ws_path,
                            engine=eng,
                        )
                        return
                    await _handle_engine_event(
                        session,
                        run,
                        run_service,
                        event,
                        ws_path,
                    )
                    if run.status == RunStatus.FAILED.value:
                        if task_id:
                            await self._queue.mark_failed(
                                task_id,
                                run.error_message or "Run failed",
                            )
                        return
                    if run.status == RunStatus.CANCELLED.value:
                        if task_id:
                            await self._queue.mark_cancelled(task_id)
                        return
            except Exception as exc:  # noqa: BLE001
                adapter_name = getattr(adapter, "display_name", eng)
                error_message = f"{adapter_name} execution error: {exc}"
                await self._handle_task_failure(
                    session,
                    run,
                    task_id=task_id,
                    lease=lease,
                    error=error_message,
                    workspace_path=ws_path,
                    engine=eng,
                )
                logger.exception(
                    "scheduler.execute.engine_error",
                    run_id=run.run_id,
                    engine=engine_value,
                )
                return

            if run.status == RunStatus.RUNNING.value:
                await self._complete_run(
                    session,
                    run,
                    task_id=task_id,
                    lease=lease,
                    workspace_path=ws_path,
                    engine=eng,
                )

    async def _complete_run(
        self,
        session: AsyncSession,
        run: Run,
        *,
        task_id: str | None,
        lease: ExecutionLease | None = None,
        workspace_path: str,
        engine: str,
    ) -> None:
        completed_at = _now()
        run.status = RunStatus.COMPLETED.value
        run.completed_at = completed_at
        run.duration_seconds = _duration_seconds(run.started_at, completed_at)
        run.error_message = None
        await _finalize_dag_statuses(run, workspace_path=workspace_path)
        run_updated = await self._transition_run_terminal_in_session(
            session,
            run,
            status=RunStatus.COMPLETED.value,
            completed_at=completed_at,
            error_message=None,
        )
        task_updated = await self._mark_task_terminal_in_session(
            session,
            task_id=task_id,
            state=TaskState.COMPLETED.value,
            completed_at=completed_at,
            lease=lease,
        )
        if not run_updated or not task_updated:
            await session.rollback()
            return
        await session.commit()
        await session.refresh(run)
        await self._hooks(session).on_run_terminal(
            run,
            status=RunStatus.COMPLETED.value,
            workspace_path=workspace_path,
            engine=engine,
        )
        await publish_run_status(run, message="Run completed")
        await publish_run_dag(run)

    async def _fail_run(
        self,
        session: AsyncSession,
        run: Run,
        message: str,
        *,
        task_id: str | None,
        lease: ExecutionLease | None = None,
        workspace_path: str | None,
        engine: str | None,
    ) -> None:
        completed_at = _now()
        run.status = RunStatus.FAILED.value
        run.error_message = message
        run.completed_at = completed_at
        run.duration_seconds = _duration_seconds(run.started_at, completed_at)
        if workspace_path:
            await _finalize_dag_statuses(run, workspace_path=workspace_path)
        run_updated = await self._transition_run_terminal_in_session(
            session,
            run,
            status=RunStatus.FAILED.value,
            completed_at=completed_at,
            error_message=message,
        )
        task_updated = await self._mark_task_terminal_in_session(
            session,
            task_id=task_id,
            state=TaskState.FAILED.value,
            error=message,
            completed_at=completed_at,
            lease=lease,
        )
        if not run_updated or not task_updated:
            await session.rollback()
            return
        await session.commit()
        await session.refresh(run)
        if workspace_path and engine:
            await self._hooks(session).on_run_terminal(
                run,
                status=RunStatus.FAILED.value,
                workspace_path=workspace_path,
                engine=engine,
            )
        await publish_run_status(run, message=message)
        await publish_run_dag(run)

    async def _execution_lease_active(
        self,
        session: AsyncSession,
        lease: ExecutionLease | None,
    ) -> bool:
        if lease is None:
            return True
        with session.no_autoflush:
            task_id = await session.scalar(
                select(ScheduledTask.id).where(
                    ScheduledTask.id == lease.task_id,
                    *_execution_lease_conditions(lease),
                )
            )
        return task_id is not None

    async def handle_timeout(self, run_id: str, *, reason: str) -> bool:
        """Route a timed-out run through retry-aware failure handling.

        Previously TimeoutWatcher called ``cancel`` directly, which
        marked the run cancelled and never consulted the retry policy.
        Timeouts now flow through ``_handle_task_failure`` so
        transient hangs can be retried per the user's policy.
        """
        async with self._session_factory() as session:
            repo = RunRepository(session)
            run = await repo.get_by_run_id(run_id)
            if not run:
                return False
            task = await self._queue.get_active_for_run(run_id)
            task_id = task.id if task else None
            workspace_path, engine = await self._resolve_run_context(session, run)
            await self._handle_task_failure(
                session,
                run,
                task_id=task_id,
                error=reason,
                workspace_path=str(workspace_path) if workspace_path else None,
                engine=engine,
            )
            return True

    async def _handle_task_failure(
        self,
        session: AsyncSession,
        run: Run,
        *,
        task_id: str | None,
        lease: ExecutionLease | None = None,
        error: str,
        workspace_path: str | None,
        engine: str | None,
    ) -> None:
        if task_id:
            task = await self._queue.get(task_id)
            if task is not None:
                active_lease = lease or _lease_from_task(task)
                if await self._schedule_retry(
                    session, run, task, error, lease=active_lease
                ):
                    return
                current_task = await self._queue.get(task_id)
                current_run = await RunRepository(session).get_by_run_id(run.run_id)
                if (
                    current_task is None
                    or current_task.state != TaskState.DISPATCHED.value
                    or current_run is None
                    or current_run.status not in RUN_ACTIVE_STATUSES
                ):
                    await session.rollback()
                    return
        await self._fail_run(
            session,
            run,
            error,
            task_id=task_id,
            lease=lease,
            workspace_path=workspace_path,
            engine=engine,
        )

    async def _schedule_retry(
        self,
        session: AsyncSession,
        run: Run,
        task: ScheduledTask,
        error: str,
        *,
        lease: ExecutionLease | None = None,
    ) -> bool:
        retry_policy = RunConfigHelper(run.config).retry_policy
        evaluator = RetryEvaluator()
        if not evaluator.should_retry(task, error, retry_policy=retry_policy):
            return False

        delay = evaluator.next_delay(task, retry_policy=retry_policy)
        delay_until = _now() + timedelta(seconds=delay)
        next_attempt = task.attempt + 1
        if next_attempt > int(task.max_attempts or 1):
            return False

        config = _clear_retry_runtime_fields(run.config)
        run.status = RunStatus.QUEUED.value
        run.started_at = None
        run.completed_at = None
        run.duration_seconds = None
        run.last_heartbeat_at = None
        run.current_task = None
        run.tasks_total = 0
        run.tasks_completed = 0
        run.nextflow_run_name = None
        run.config = config
        run.error_message = error
        run.error_json = None
        with session.no_autoflush:
            task_conditions = [ScheduledTask.id == task.id]
            if lease is not None:
                task_conditions.extend(_execution_lease_conditions(lease))
            else:
                task_conditions.append(
                    ScheduledTask.state == TaskState.DISPATCHED.value
                )
            task_result = await session.execute(
                update(ScheduledTask)
                .where(
                    *task_conditions,
                    ScheduledTask.max_attempts >= next_attempt,
                )
                .values(
                    state=TaskState.QUEUED.value,
                    attempt=next_attempt,
                    delay_until=delay_until,
                    dispatched_at=None,
                    completed_at=None,
                    worker_id=None,
                    error_message=error,
                )
            )
            if task_result.rowcount != 1:
                await session.rollback()
                return False
            run_result = await session.execute(
                update(Run)
                .where(
                    Run.run_id == run.run_id,
                    Run.status.in_(RUN_ACTIVE_STATUSES),
                )
                .values(
                    status=RunStatus.QUEUED.value,
                    started_at=None,
                    completed_at=None,
                    duration_seconds=None,
                    last_heartbeat_at=None,
                    current_task=None,
                    tasks_total=0,
                    tasks_completed=0,
                    nextflow_run_name=None,
                    config=config,
                    error_message=error,
                    error_json=None,
                )
            )
            if run_result.rowcount != 1:
                await session.rollback()
                return False
        await session.commit()
        await session.refresh(run)
        await publish_run_status(
            run,
            message=f"Run retry scheduled (attempt {next_attempt}/{task.max_attempts})",
        )
        return True

    async def _mark_task_terminal_in_session(
        self,
        session: AsyncSession,
        *,
        task_id: str | None,
        state: str,
        error: str | None = None,
        completed_at: datetime | None = None,
        lease: ExecutionLease | None = None,
    ) -> bool:
        if not task_id:
            return True
        values = {
            "state": state,
            "completed_at": completed_at or _now(),
            "delay_until": None,
        }
        if error is not None:
            values["error_message"] = error
        with session.no_autoflush:
            conditions = [ScheduledTask.id == task_id]
            if lease is not None:
                conditions.extend(_execution_lease_conditions(lease))
            else:
                conditions.append(
                    ScheduledTask.state.in_(
                        [TaskState.QUEUED.value, TaskState.DISPATCHED.value]
                    )
                )
            result = await session.execute(
                update(ScheduledTask).where(*conditions).values(**values)
            )
        return result.rowcount == 1

    async def _mark_stale_task_failed_in_session(
        self,
        session: AsyncSession,
        *,
        task: ScheduledTask,
        error: str,
        completed_at: datetime,
        stale_cutoff: datetime,
    ) -> bool:
        values = {
            "state": TaskState.FAILED.value,
            "completed_at": completed_at,
            "delay_until": None,
            "error_message": error,
        }
        current = await session.get(ScheduledTask, task.id)
        if current is None:
            return False
        snapshot_worker_id = getattr(task, "worker_id", None)
        snapshot_attempt = int(getattr(task, "attempt", 1) or 1)
        if (
            current.run_id != task.run_id
            or current.state != TaskState.DISPATCHED.value
            or current.attempt != snapshot_attempt
            or (
                snapshot_worker_id is not None
                and current.worker_id != snapshot_worker_id
            )
            or current.dispatched_at is None
        ):
            return False
        dispatched_at = _ensure_utc(current.dispatched_at)
        if dispatched_at > stale_cutoff:
            return False
        with session.no_autoflush:
            result = await session.execute(
                update(ScheduledTask)
                .where(
                    ScheduledTask.id == current.id,
                    ScheduledTask.run_id == current.run_id,
                    ScheduledTask.state == TaskState.DISPATCHED.value,
                    ScheduledTask.worker_id == current.worker_id,
                    ScheduledTask.attempt == current.attempt,
                    ScheduledTask.dispatched_at == current.dispatched_at,
                )
                .execution_options(synchronize_session=False)
                .values(**values)
            )
        return result.rowcount == 1

    async def _transition_run_terminal_in_session(
        self,
        session: AsyncSession,
        run: Run,
        *,
        status: str,
        completed_at: datetime,
        error_message: str | None,
    ) -> bool:
        values = {
            "status": status,
            "completed_at": completed_at,
            "duration_seconds": run.duration_seconds,
            "error_message": error_message,
            "config": run.config,
        }
        with session.no_autoflush:
            result = await session.execute(
                update(Run)
                .where(
                    Run.run_id == run.run_id,
                    Run.status.in_(RUN_ACTIVE_STATUSES),
                )
                .values(**values)
            )
        return result.rowcount == 1

    def _hooks(self, session: AsyncSession) -> RunCompletionHooks:
        return RunCompletionHooks(session)

    async def _resolve_run_context(
        self,
        session: AsyncSession,
        run: Run,
    ) -> tuple[Path | None, str | None]:
        project = await ProjectRepository(session).get(run.project_id)
        workflow = (
            await session.get(Workflow, run.workflow_id) if run.workflow_id else None
        )
        if not project or not workflow:
            return None, None
        workspace_path = project_home(project)
        engine = getattr(workflow.engine, "value", workflow.engine)
        return workspace_path, str(engine)


def _execution_lease_conditions(lease: ExecutionLease) -> list:
    return [
        ScheduledTask.run_id == lease.run_id,
        ScheduledTask.state == TaskState.DISPATCHED.value,
        ScheduledTask.worker_id == lease.worker_id,
        ScheduledTask.attempt == lease.attempt,
        ScheduledTask.dispatched_at == lease.dispatched_at,
    ]


def _lease_from_task(task: ScheduledTask) -> ExecutionLease | None:
    if task.state != TaskState.DISPATCHED.value:
        return None
    return ExecutionLease(
        task_id=task.id,
        run_id=task.run_id,
        worker_id=task.worker_id,
        attempt=task.attempt,
        dispatched_at=task.dispatched_at,
    )


def _clear_retry_runtime_fields(config: dict | None) -> dict:
    if not isinstance(config, dict):
        return {}
    cleaned = dict(config)
    runtime = dict(cleaned.get("runtime") or {})
    for key in (
        "pid",
        "process_id",
        "engine_pid",
        "container_id",
        "backend_job_id",
        "executor_id",
        "run_name",
        "nextflow_run_name",
        "engine",
    ):
        runtime.pop(key, None)
    cleaned["runtime"] = runtime
    return cleaned
