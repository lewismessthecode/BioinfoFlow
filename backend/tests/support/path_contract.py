from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project
from app.models.project_workflow_binding import ProjectWorkflowBinding
from app.models.workflow import Workflow, WorkflowEngine, WorkflowSource
from app.path_layout import ensure_project_layout, workflow_bundle_home


async def create_project(
    session: AsyncSession,
    *,
    name: str,
    user_id: str = "dev",
    storage_mode: str = "managed",
    external_root_path: str | None = None,
    description: str | None = None,
    is_default: bool = False,
) -> Project:
    project = Project(
        name=name,
        description=description,
        storage_mode=storage_mode,
        external_root_path=external_root_path,
        user_id=user_id,
        is_default=is_default,
    )
    session.add(project)
    await session.commit()
    await session.refresh(project)
    ensure_project_layout(project)
    return project


async def create_workflow(
    session: AsyncSession,
    *,
    name: str | None = None,
    source: WorkflowSource = WorkflowSource.LOCAL,
    engine: WorkflowEngine = WorkflowEngine.NEXTFLOW,
    version: str | None = None,
    source_ref: str | None = None,
    entrypoint_relpath: str | None = None,
    bundle_kind: str | None = None,
    content: str | None = None,
    schema_json: dict | None = None,
    description: str | None = None,
) -> Workflow:
    workflow = Workflow(
        name=f"wf-{uuid4()}" if name is None else name,
        description=description,
        source=source,
        engine=engine,
        source_ref=source_ref,
        entrypoint_relpath=entrypoint_relpath,
        bundle_kind=bundle_kind,
        version=str(uuid4()) if version is None else version,
        schema_json=schema_json,
    )
    session.add(workflow)
    await session.commit()
    await session.refresh(workflow)

    if (
        str(getattr(source, "value", source)) == WorkflowSource.LOCAL.value
        and content is not None
    ):
        bundle_root = workflow_bundle_home(str(workflow.id))
        bundle_root.mkdir(parents=True, exist_ok=True)
        relative_path = entrypoint_relpath or (
            "main.wdl"
            if str(getattr(engine, "value", engine)) == WorkflowEngine.WDL.value
            else "main.nf"
        )
        target = bundle_root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        workflow.entrypoint_relpath = relative_path
        workflow.bundle_kind = bundle_kind or "local_bundle"
        workflow.source_ref = source_ref or "local"
        await session.commit()
        await session.refresh(workflow)

    return workflow


async def bind_workflow(
    session: AsyncSession, *, project_id: str, workflow_id: str
) -> None:
    session.add(
        ProjectWorkflowBinding(project_id=project_id, workflow_id=workflow_id)
    )
    await session.commit()


def write_project_file(root: Path, relative_path: str, content: str) -> Path:
    target = root / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return target
