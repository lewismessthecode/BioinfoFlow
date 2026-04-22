from __future__ import annotations

from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.run_config import RunConfigHelper
from app.scheduler.cleanup import WorkDirCleaner
from app.services.audit_service import AuditService
from app.services.batch_service import BatchService
from app.services.notification_service import NotificationService
from app.utils.logging import get_logger

logger = get_logger(__name__)


class RunCompletionHooks:
    def __init__(
        self,
        session: AsyncSession,
        *,
        cleaner: WorkDirCleaner | None = None,
        audit_service: AuditService | None = None,
        notification_service: NotificationService | None = None,
        batch_service: BatchService | None = None,
    ) -> None:
        self._cleaner = cleaner or WorkDirCleaner()
        self._audit = audit_service or AuditService(session)
        self._notifications = notification_service or NotificationService(session)
        self._batches = batch_service or BatchService(session)

    async def on_run_terminal(
        self,
        run,
        *,
        status: str,
        workspace_path: str | Path,
        engine: str,
    ) -> dict:
        """Run the four completion hooks with per-step isolation.

        Each side effect (cleanup, audit, user notification, batch
        roll-up) must survive the others failing. Before isolation a
        PermissionError inside cleanup_run suppressed audit +
        notifications + batch status *and* leaked the scheduler slot
        because the exception escaped the caller.
        """
        runtime = RunConfigHelper(run.config).runtime
        cleanup: dict = {}
        try:
            cleanup = await self._cleaner.cleanup_run(
                run.run_id,
                workspace_path=workspace_path,
                status=status,
                engine=engine,
                runtime=runtime,
            )
        except Exception as exc:
            logger.error(
                "scheduler.hook.cleanup_failed",
                run_id=run.run_id,
                error=str(exc),
                error_type=type(exc).__name__,
            )

        action = {
            "completed": "run.completed",
            "failed": "run.failed",
            "cancelled": "run.cancelled",
        }.get(status, "run.updated")
        try:
            await self._audit.log(
                action=action,
                resource_type="run",
                resource_id=run.run_id,
                project_id=str(run.project_id),
                actor="scheduler",
                details={"status": status, "cleanup": cleanup},
            )
        except Exception as exc:
            logger.error(
                "scheduler.hook.audit_failed",
                run_id=run.run_id,
                error=str(exc),
                error_type=type(exc).__name__,
            )

        trigger = {
            "completed": "on_complete",
            "failed": "on_failure",
        }.get(status)
        if trigger:
            try:
                await self._notifications.notify(
                    str(run.project_id),
                    trigger,
                    {"run_id": run.run_id, "status": status},
                )
            except Exception as exc:
                logger.error(
                    "scheduler.hook.notify_failed",
                    run_id=run.run_id,
                    trigger=trigger,
                    error=str(exc),
                    error_type=type(exc).__name__,
                )

        try:
            batch = await self._batches.find_batch_for_run(run.run_id)
            if batch is not None:
                updated = await self._batches.update_batch_status(batch.batch_id)
                if updated["status"] in {"completed", "partial", "failed"}:
                    try:
                        await self._notifications.notify(
                            str(run.project_id),
                            "on_batch_complete",
                            updated,
                        )
                    except Exception as exc:
                        logger.error(
                            "scheduler.hook.batch_notify_failed",
                            run_id=run.run_id,
                            batch_id=batch.batch_id,
                            error=str(exc),
                            error_type=type(exc).__name__,
                        )
        except Exception as exc:
            logger.error(
                "scheduler.hook.batch_rollup_failed",
                run_id=run.run_id,
                error=str(exc),
                error_type=type(exc).__name__,
            )
        return cleanup
