from __future__ import annotations

from sqlalchemy import select

from app.models.project_workflow_binding import ProjectWorkflowBinding
from app.models.workflow import Workflow
from app.repositories.base import BaseRepository


class ProjectWorkflowBindingRepository(BaseRepository[ProjectWorkflowBinding]):
    model = ProjectWorkflowBinding

    async def get_by_project_workflow(
        self, *, project_id: str, workflow_id: str
    ) -> ProjectWorkflowBinding | None:
        stmt = select(self.model).where(
            self.model.project_id == project_id, self.model.workflow_id == workflow_id
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def is_enabled(self, *, project_id: str, workflow_id: str) -> bool:
        stmt = (
            select(self.model.id)
            .where(
                self.model.project_id == project_id,
                self.model.workflow_id == workflow_id,
            )
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def ensure_binding(
        self, *, project_id: str, workflow_id: str
    ) -> ProjectWorkflowBinding:
        """Create a binding if one does not already exist and flush."""
        binding = ProjectWorkflowBinding(
            project_id=project_id, workflow_id=workflow_id
        )
        self.session.add(binding)
        await self.session.flush()
        return binding

    async def list_workflows_for_project(self, project_id: str) -> list[Workflow]:
        """Return all Workflow rows bound to *project_id*."""
        stmt = (
            select(Workflow)
            .join(self.model, Workflow.id == self.model.workflow_id)
            .where(self.model.project_id == project_id)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
