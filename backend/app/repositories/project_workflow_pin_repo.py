from __future__ import annotations

from sqlalchemy import select

from app.models.project_workflow_pin import ProjectWorkflowPin
from app.repositories.base import BaseRepository


class ProjectWorkflowPinRepository(BaseRepository[ProjectWorkflowPin]):
    model = ProjectWorkflowPin

    async def get_by_group(
        self, *, project_id: str, workflow_source: str, workflow_name: str
    ) -> ProjectWorkflowPin | None:
        stmt = select(self.model).where(
            self.model.project_id == project_id,
            self.model.workflow_source == workflow_source,
            self.model.workflow_name == workflow_name,
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def list_by_project(self, *, project_id: str) -> list[ProjectWorkflowPin]:
        stmt = select(self.model).where(self.model.project_id == project_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
