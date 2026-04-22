"""Repository for dashboard statistics queries.

Centralises aggregation queries that were previously inlined in StatsService.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.image import DockerImage
from app.models.project import Project
from app.models.run import Run
from app.models.workflow import Workflow


class StatsRepository:
    """Read-only repository for dashboard aggregation queries."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_run_counts_by_status(
        self, *, user_id: str | None = None
    ) -> dict[str, int]:
        """Return ``{status: count}`` for all runs, optionally scoped to *user_id*.

        When *user_id* is provided, only runs whose parent project is owned by
        that user are counted.
        """
        stmt = select(Run.status, func.count(Run.id))
        if user_id is not None:
            stmt = stmt.join(Project, Project.id == Run.project_id).where(
                Project.user_id == user_id
            )
        stmt = stmt.group_by(Run.status)
        result = await self.session.execute(stmt)
        return dict(result.all())

    async def get_workflow_count(self) -> int:
        result = await self.session.execute(select(func.count(Workflow.id)))
        return result.scalar() or 0

    async def get_image_counts_by_status(self) -> dict[str, int]:
        """Return ``{status: count}`` for Docker images."""
        result = await self.session.execute(
            select(DockerImage.status, func.count(DockerImage.id)).group_by(
                DockerImage.status
            )
        )
        return dict(result.all())

    async def get_project_count(self, *, user_id: str | None = None) -> int:
        stmt = select(func.count(Project.id))
        if user_id is not None:
            stmt = stmt.where(Project.user_id == user_id)
        result = await self.session.execute(stmt)
        return result.scalar() or 0

    async def get_recent_runs(
        self, *, limit: int = 5, user_id: str | None = None
    ) -> list[Run]:
        """Return the most recent *limit* Run model instances.

        When *user_id* is provided, only runs whose parent project is owned by
        that user are returned.
        """
        stmt = select(Run)
        if user_id is not None:
            stmt = stmt.join(Project, Project.id == Run.project_id).where(
                Project.user_id == user_id
            )
        stmt = stmt.order_by(Run.created_at.desc()).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
