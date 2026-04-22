from __future__ import annotations

from uuid import uuid4

import pytest

from app.models.project import Project
from app.models.run import Run, RunStatus
from app.models.workflow import Workflow, WorkflowEngine, WorkflowSource
from app.path_layout import run_home
from app.scheduler.hooks import RunCompletionHooks
from app.services.audit_service import AuditService


@pytest.mark.asyncio
async def test_run_completion_hooks_cleanup_success_and_write_audit(
    db_session, tmp_path
):
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    project = Project(
        name=f"Hooks Project {uuid4()}",
        storage_mode="external",
        external_root_path=str(workspace),
        user_id="dev",
    )
    workflow = Workflow(
        name=f"wf-{uuid4()}",
        source=WorkflowSource.LOCAL,
        engine=WorkflowEngine.NEXTFLOW,
        version=str(uuid4()),
    )
    run = Run(
        run_id="run_hooks_123",
        project_id=str(project.id),
        workflow_id=str(workflow.id),
        status=RunStatus.COMPLETED.value,
        config={"params": {"outdir": "results"}},
        samples_count=0,
        tasks_total=0,
        tasks_completed=0,
    )

    db_session.add_all([project, workflow])
    await db_session.commit()
    await db_session.refresh(project)
    await db_session.refresh(workflow)
    run.project_id = str(project.id)
    run.workflow_id = str(workflow.id)
    db_session.add(run)
    await db_session.commit()

    archive_dir = run_home(project, run.run_id)
    (archive_dir / "audit").mkdir(parents=True, exist_ok=True)
    (archive_dir / "audit" / "run.manifest.json").write_text("{}", encoding="utf-8")

    hooks = RunCompletionHooks(db_session)
    await hooks.on_run_terminal(
        run,
        status="completed",
        workspace_path=workspace,
        engine="nextflow",
    )

    assert archive_dir.exists() is False

    audit_entries = await AuditService(db_session).list_for_resource("run", run.run_id)
    assert [entry.action for entry in audit_entries] == ["run.completed"]
    assert audit_entries[0].details["cleanup"]["deleted"] == [str(archive_dir)]
