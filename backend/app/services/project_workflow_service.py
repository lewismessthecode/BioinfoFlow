from __future__ import annotations

from collections import defaultdict

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workflow import Workflow
from app.repositories.project_repo import ProjectRepository
from app.repositories.project_workflow_binding_repo import (
    ProjectWorkflowBindingRepository,
)
from app.repositories.project_workflow_pin_repo import ProjectWorkflowPinRepository
from app.repositories.workflow_repo import WorkflowRepository


class ProjectWorkflowService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.project_repo = ProjectRepository(session)
        self.workflow_repo = WorkflowRepository(session)
        self.binding_repo = ProjectWorkflowBindingRepository(session)
        self.pin_repo = ProjectWorkflowPinRepository(session)

    async def list_project_workflows(self, *, project_id: str) -> list[dict]:
        project = await self.project_repo.get(project_id)
        if not project:
            raise FileNotFoundError("project not found")

        pins = await self.pin_repo.list_by_project(project_id=project_id)
        pin_map: dict[tuple[str, str], str] = {
            (p.workflow_source, p.workflow_name): str(p.pinned_workflow_id)
            for p in pins
        }

        # All workflows enabled for this project.
        enabled = await self.binding_repo.list_workflows_for_project(project_id)

        grouped: dict[tuple[str, str], list[Workflow]] = defaultdict(list)
        for wf in enabled:
            source = getattr(wf.source, "value", wf.source)
            name = getattr(wf, "name", None)
            if not source or not name:
                continue
            grouped[(str(source), str(name))].append(wf)

        def _sort_key(wf: Workflow):
            created_at = getattr(wf, "created_at", None)
            wf_id = str(getattr(wf, "id", ""))
            return (created_at, wf_id)

        groups: list[dict] = []
        for (source, name), versions in grouped.items():
            versions_sorted = sorted(versions, key=_sort_key, reverse=True)
            pinned_id = pin_map.get((source, name))
            pinned = None
            if pinned_id:
                pinned = next(
                    (
                        wf
                        for wf in versions_sorted
                        if str(getattr(wf, "id", "")) == pinned_id
                    ),
                    None,
                )
            if pinned is None and versions_sorted:
                pinned = versions_sorted[0]

            if pinned is None:
                continue

            groups.append(
                {
                    "source": source,
                    "name": name,
                    "pinned_workflow": pinned,
                    "versions": versions_sorted,
                }
            )

        # Stable ordering for UI.
        groups.sort(key=lambda g: (g["source"], g["name"]))
        return groups

    async def bind_workflow(self, *, project_id: str, workflow_id: str) -> None:
        project = await self.project_repo.get(project_id)
        if not project:
            raise FileNotFoundError("project not found")
        workflow = await self.workflow_repo.get(workflow_id)
        if not workflow:
            raise FileNotFoundError("workflow not found")

        existing = await self.binding_repo.get_by_project_workflow(
            project_id=project_id, workflow_id=workflow_id
        )
        if not existing:
            await self.binding_repo.create(
                project_id=project_id, workflow_id=workflow_id
            )

        source = str(getattr(workflow.source, "value", workflow.source))
        name = str(getattr(workflow, "name", ""))
        if not source or not name:
            return

        # If no pin exists for this pipeline in the project, pin to the first bound version.
        pin = await self.pin_repo.get_by_group(
            project_id=project_id, workflow_source=source, workflow_name=name
        )
        if not pin:
            await self.pin_repo.create(
                project_id=project_id,
                workflow_source=source,
                workflow_name=name,
                pinned_workflow_id=workflow_id,
            )

    async def unbind_workflow(self, *, project_id: str, workflow_id: str) -> None:
        project = await self.project_repo.get(project_id)
        if not project:
            raise FileNotFoundError("project not found")

        workflow = await self.workflow_repo.get(workflow_id)
        if not workflow:
            # If workflow was deleted, attempt to remove binding record anyway.
            binding = await self.binding_repo.get_by_project_workflow(
                project_id=project_id, workflow_id=workflow_id
            )
            if binding:
                await self.binding_repo.delete(binding)
                return
            raise FileNotFoundError("workflow not found")

        binding = await self.binding_repo.get_by_project_workflow(
            project_id=project_id, workflow_id=workflow_id
        )
        if binding:
            await self.binding_repo.delete(binding)

        source = str(getattr(workflow.source, "value", workflow.source))
        name = str(getattr(workflow, "name", ""))
        if not source or not name:
            return

        pin = await self.pin_repo.get_by_group(
            project_id=project_id, workflow_source=source, workflow_name=name
        )
        if not pin:
            return

        if str(pin.pinned_workflow_id) != str(workflow_id):
            return

        # If we removed the pinned version, pick a new pinned version from remaining bindings.
        groups = await self.list_project_workflows(project_id=project_id)
        match = next(
            (g for g in groups if g["source"] == source and g["name"] == name), None
        )
        if not match:
            await self.pin_repo.delete(pin)
            return

        replacement = match["pinned_workflow"]
        await self.pin_repo.update(
            pin, pinned_workflow_id=str(getattr(replacement, "id"))
        )

    async def set_pin(self, *, project_id: str, pinned_workflow_id: str) -> None:
        project = await self.project_repo.get(project_id)
        if not project:
            raise FileNotFoundError("project not found")

        workflow = await self.workflow_repo.get(pinned_workflow_id)
        if not workflow:
            raise FileNotFoundError("workflow not found")

        enabled = await self.binding_repo.is_enabled(
            project_id=project_id, workflow_id=pinned_workflow_id
        )
        if not enabled:
            raise PermissionError("workflow not enabled for project")

        source = str(getattr(workflow.source, "value", workflow.source))
        name = str(getattr(workflow, "name", ""))
        if not source or not name:
            raise ValueError("workflow missing source or name")

        pin = await self.pin_repo.get_by_group(
            project_id=project_id, workflow_source=source, workflow_name=name
        )
        if pin:
            await self.pin_repo.update(pin, pinned_workflow_id=str(pinned_workflow_id))
        else:
            await self.pin_repo.create(
                project_id=project_id,
                workflow_source=source,
                workflow_name=name,
                pinned_workflow_id=str(pinned_workflow_id),
            )
