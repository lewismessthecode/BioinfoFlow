from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import delete, select

from app.models.project import Project
from app.models.run import Run, RunStatus
from app.scheduler.models import ScheduledTask
from app.repositories.base import BaseRepository
from app.schemas.common import Pagination


class RunRepository(BaseRepository[Run]):
    model = Run
    active_statuses = [
        RunStatus.PENDING.value,
        RunStatus.QUEUED.value,
        RunStatus.PREPARING.value,
        RunStatus.RUNNING.value,
    ]

    async def list(
        self,
        *,
        limit: int = 20,
        cursor: str | None = None,
        project_id: str | None = None,
        workflow_id: str | None = None,
        status: list[str] | None = None,
        user_id: str | None = None,
        workspace_id: str | None = None,
    ) -> tuple[list[Run], Pagination]:
        stmt = select(self.model)
        if user_id is not None or workspace_id is not None:
            stmt = stmt.join(Project, Project.id == self.model.project_id)
        if user_id is not None:
            stmt = stmt.where(Project.user_id != "system")
        if workspace_id is not None:
            stmt = stmt.where(Project.workspace_id == workspace_id)
        filters = {
            "project_id": project_id,
            "workflow_id": workflow_id,
            "status": status,
        }
        return await super().list(
            limit=limit, cursor=cursor, filters=filters, stmt=stmt
        )

    async def get_by_run_id(self, run_id: str) -> Run | None:
        stmt = select(self.model).where(self.model.run_id == run_id)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_active_replay(
        self,
        *,
        source_run_id: str,
        replay_kind: str,
        replay_idempotency_key: str,
    ) -> Run | None:
        stmt = (
            select(self.model)
            .where(
                self.model.source_run_id == source_run_id,
                self.model.replay_kind == replay_kind,
                self.model.replay_idempotency_key == replay_idempotency_key,
                self.model.status.in_(self.active_statuses),
            )
            .order_by(self.model.created_at.desc(), self.model.id.desc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def list_by_statuses(
        self,
        statuses: list[str],
        *,
        project_id: str | None = None,
        user_id: str | None = None,
        workspace_id: str | None = None,
    ) -> list[Run]:
        """Return runs matching any of the given statuses."""
        stmt = select(self.model).where(self.model.status.in_(statuses))
        if project_id:
            stmt = stmt.where(self.model.project_id == project_id)
        if user_id is not None or workspace_id is not None:
            stmt = stmt.join(Project, Project.id == self.model.project_id)
        if user_id is not None:
            stmt = stmt.where(Project.user_id != "system")
        if workspace_id is not None:
            stmt = stmt.where(Project.workspace_id == workspace_id)
        stmt = stmt.order_by(self.model.created_at.desc(), self.model.id.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update_config(self, run: Run, config: dict) -> Run:
        """Persist a new config dict on *run* and refresh."""
        run.config = config
        await self.session.commit()
        await self.session.refresh(run)
        return run

    async def mark_failed(self, run_id: str, message: str) -> Run | None:
        """Mark a run as FAILED with an error message and timestamp."""
        run = await self.get_by_run_id(run_id)
        if not run:
            return None
        completed_at = datetime.now(timezone.utc)
        run.status = RunStatus.FAILED.value
        run.error_message = message
        run.completed_at = completed_at
        run.duration_seconds = _duration_seconds(run.started_at, completed_at)
        await self.session.commit()
        return run

    async def delete_scheduler_tasks(self, run_id: str) -> None:
        """Remove persistent scheduler rows for a run before deleting it."""
        await self.session.execute(
            delete(ScheduledTask).where(ScheduledTask.run_id == run_id)
        )

    async def delete_by_project_and_statuses(
        self, project_id: str, statuses: list[str]
    ) -> int:
        """Delete runs matching a project and status list. Returns count deleted."""
        stmt = select(self.model).where(
            self.model.project_id == project_id,
            self.model.status.in_(statuses),
        )
        result = await self.session.execute(stmt)
        runs = result.scalars().all()
        for run in runs:
            await self.session.delete(run)
        await self.session.commit()
        return len(runs)


def _duration_seconds(
    started_at: datetime | None,
    completed_at: datetime | None,
) -> int | None:
    if not started_at or not completed_at:
        return None
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)
    if completed_at.tzinfo is None:
        completed_at = completed_at.replace(tzinfo=timezone.utc)
    return int((completed_at - started_at).total_seconds())
