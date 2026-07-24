from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import String, case, cast, delete, func, or_, select, update
from sqlalchemy.orm import selectinload

from app.models.project import Project
from app.models.run import Run, RunStatus
from app.scheduler.models import ScheduledTask
from app.repositories.base import BaseRepository
from app.schemas.common import Pagination
from app.models.workflow import Workflow
from app.utils.pagination import decode_cursor, encode_cursor

RUN_ACTIVE_STATUSES = (
    RunStatus.PENDING.value,
    RunStatus.QUEUED.value,
    RunStatus.PREPARING.value,
    RunStatus.RUNNING.value,
)


class RunRepository(BaseRepository[Run]):
    model = Run

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

    async def search_context(
        self,
        *,
        workspace_id: str,
        query: str,
        current_project_id: str | None = None,
        limit: int = 20,
        cursor: str | None = None,
    ) -> tuple[list[Run], Pagination]:
        escaped = (
            query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        )
        pattern = f"%{escaped}%"
        stmt = (
            select(self.model)
            .join(Project, Project.id == self.model.project_id)
            .outerjoin(Workflow, Workflow.id == self.model.workflow_id)
            .where(Project.workspace_id == workspace_id)
            .options(
                selectinload(self.model.project),
                selectinload(self.model.workflow),
            )
        )
        if query:
            stmt = stmt.where(
                or_(
                    self.model.run_id.ilike(pattern, escape="\\"),
                    self.model.nextflow_run_name.ilike(pattern, escape="\\"),
                    self.model.status.ilike(pattern, escape="\\"),
                    Workflow.name.ilike(pattern, escape="\\"),
                    cast(self.model.config, String).ilike(pattern, escape="\\"),
                )
            )
        total_count = await self.session.scalar(
            select(func.count()).select_from(stmt.order_by(None).subquery())
        )
        offset = 0
        if cursor:
            try:
                offset = max(int(decode_cursor(cursor).get("offset") or 0), 0)
            except (ValueError, TypeError, KeyError) as exc:
                raise ValueError("Invalid run search cursor") from exc
        project_rank = (
            case((self.model.project_id == current_project_id, 0), else_=1)
            if current_project_id
            else 0
        )
        result = await self.session.execute(
            stmt.order_by(
                project_rank,
                self.model.created_at.desc(),
                self.model.id.desc(),
            )
            .offset(offset)
            .limit(limit + 1)
        )
        items = list(result.scalars().unique().all())
        has_more = len(items) > limit
        items = items[:limit]
        return items, Pagination(
            limit=limit,
            has_more=has_more,
            next_cursor=(
                encode_cursor({"offset": offset + len(items)})
                if has_more
                else None
            ),
            total_count=total_count or 0,
        )

    async def get_replay_by_intent(
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
            )
            .order_by(self.model.created_at.desc(), self.model.id.desc())
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def has_replay_children(self, source_run_id: str) -> bool:
        stmt = select(self.model.run_id).where(
            self.model.source_run_id == source_run_id
        )
        result = await self.session.execute(stmt.limit(1))
        return result.first() is not None

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
        duration_seconds = _duration_seconds(run.started_at, completed_at)
        with self.session.no_autoflush:
            result = await self.session.execute(
                update(self.model)
                .where(
                    self.model.run_id == run_id,
                    self.model.status.in_(RUN_ACTIVE_STATUSES),
                )
                .values(
                    status=RunStatus.FAILED.value,
                    error_message=message,
                    completed_at=completed_at,
                    duration_seconds=duration_seconds,
                )
            )
        if result.rowcount != 1:
            await self.session.rollback()
            return None
        await self.session.commit()
        return await self.get_by_run_id(run_id)

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
