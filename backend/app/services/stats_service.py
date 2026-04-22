"""Dashboard statistics service.

Aggregates counts and recent activity across runs, workflows, images, and projects.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.stats_repo import StatsRepository


class StatsService:
    def __init__(self, session: AsyncSession):
        self._repo = StatsRepository(session)

    async def get_dashboard_stats(self, *, user_id: str | None = None) -> dict:
        """Return aggregated dashboard statistics, scoped to *user_id*."""
        by_status = await self._repo.get_run_counts_by_status(user_id=user_id)
        workflows_total = await self._repo.get_workflow_count()
        images_by_status = await self._repo.get_image_counts_by_status()
        projects_total = await self._repo.get_project_count(user_id=user_id)
        recent_run_models = await self._repo.get_recent_runs(
            limit=5, user_id=user_id
        )

        runs_stats = {
            "total": sum(by_status.values()),
            "running": by_status.get("running", 0),
            "completed": by_status.get("completed", 0),
            "failed": by_status.get("failed", 0),
            "queued": by_status.get("queued", 0),
            "pending": by_status.get("pending", 0),
            "cancelled": by_status.get("cancelled", 0),
        }
        images_stats = {
            "total": sum(images_by_status.values()),
            "local": images_by_status.get("local", 0),
            "remote": images_by_status.get("remote", 0),
            "pulling": images_by_status.get("pulling", 0),
        }
        recent_runs = [
            {
                "run_id": run.run_id,
                "workflow_id": str(run.workflow_id) if run.workflow_id else None,
                "status": run.status,
                "started_at": (
                    run.started_at.isoformat() if run.started_at else None
                ),
                "duration_seconds": run.duration_seconds,
                "current_task": run.current_task,
            }
            for run in recent_run_models
        ]

        return {
            "runs": runs_stats,
            "workflows": {"total": workflows_total},
            "images": images_stats,
            "projects": {"total": projects_total},
            "recent_runs": recent_runs,
        }
