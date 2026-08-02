from __future__ import annotations

from sqlalchemy import select

from app.models.project_workflow_binding import ProjectWorkflowBinding
from app.models.workflow import Workflow
from app.repositories.base import BaseRepository
from app.schemas.common import Pagination


class WorkflowRepository(BaseRepository[Workflow]):
    model = Workflow

    async def list(
        self,
        *,
        limit: int = 20,
        cursor: str | None = None,
        search: str | None = None,
        source: str | None = None,
    ) -> tuple[list[Workflow], Pagination]:
        stmt = select(self.model)
        stmt = self._apply_search(
            stmt, [self.model.name, self.model.description], search
        )
        filters = {"source": source}
        return await super().list(
            limit=limit, cursor=cursor, filters=filters, stmt=stmt
        )

    async def get_by_unique(
        self, *, source: str, name: str, version: str
    ) -> Workflow | None:
        stmt = select(self.model).where(
            self.model.source == source,
            self.model.name == name,
            self.model.version == version,
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def search_context(
        self,
        *,
        query: str,
        project_id: str | None = None,
        limit: int = 20,
    ) -> list[Workflow]:
        """Search workflows for agent context, optionally within a project."""
        stmt = select(self.model)
        if project_id:
            stmt = stmt.join(
                ProjectWorkflowBinding,
                ProjectWorkflowBinding.workflow_id == self.model.id,
            ).where(ProjectWorkflowBinding.project_id == project_id)
        if query:
            escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace(
                "_", "\\_"
            )
            stmt = stmt.where(self.model.name.ilike(f"%{escaped}%", escape="\\"))
        result = await self.session.execute(
            stmt.order_by(self.model.created_at.desc(), self.model.id.desc()).limit(
                limit
            )
        )
        return list(result.scalars().all())
