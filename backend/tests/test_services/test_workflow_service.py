from __future__ import annotations

from uuid import uuid4

import pytest

from app.models.workflow import WorkflowEngine, WorkflowSource
from app.path_layout import local_workflows_root, workflow_bundle_home, workflow_home
from app.services.workflow_service import WorkflowService
from tests.support.path_contract import create_workflow


@pytest.mark.asyncio
async def test_create_local_workflow_rejects_absolute_inline_entrypoint_paths(
    db_session, tmp_path
):
    service = WorkflowService(db_session)
    outside = tmp_path / "outside" / "main.nf"

    with pytest.raises(ValueError, match="entrypoint_relpath"):
        await service.create_workflow(
            {
                "source": "local",
                "engine": "nextflow",
                "name": "unsafe-inline",
                "content": "nextflow.enable.dsl=2\nworkflow { }\n",
                "file_name": str(outside),
            }
        )

    assert not outside.exists()


@pytest.mark.asyncio
async def test_create_local_workflow_rejects_absolute_uploaded_bundle_paths(
    db_session, tmp_path
):
    service = WorkflowService(db_session)
    outside = tmp_path / "outside" / "workflow.nf"

    with pytest.raises(ValueError, match="entrypoint_relpath"):
        await service.create_workflow(
            {
                "source": "local",
                "engine": "nextflow",
                "name": "unsafe-upload",
                "entrypoint_relpath": str(outside),
                "bundle_files": [
                    {
                        "relpath": str(outside),
                        "content": "nextflow.enable.dsl=2\nworkflow { }\n",
                    }
                ],
            }
        )

    assert not outside.exists()


@pytest.mark.asyncio
async def test_create_local_workflow_rejects_nested_inline_entrypoint_traversal(
    db_session,
):
    service = WorkflowService(db_session)

    with pytest.raises(ValueError, match="entrypoint_relpath"):
        await service.create_workflow(
            {
                "source": "local",
                "engine": "nextflow",
                "name": "unsafe-inline-nested",
                "content": "nextflow.enable.dsl=2\nworkflow { }\n",
                "entrypoint_relpath": "nested/../main.nf",
            }
        )


@pytest.mark.asyncio
async def test_create_local_workflow_rejects_nested_uploaded_bundle_traversal(
    db_session,
):
    service = WorkflowService(db_session)

    with pytest.raises(ValueError, match="bundle file path"):
        await service.create_workflow(
            {
                "source": "local",
                "engine": "nextflow",
                "name": "unsafe-upload-nested",
                "entrypoint_relpath": "main.nf",
                "bundle_files": [
                    {
                        "relpath": "nested/../main.nf",
                        "content": "nextflow.enable.dsl=2\nworkflow { }\n",
                    }
                ],
            }
        )


@pytest.mark.asyncio
async def test_create_local_workflow_ignores_payload_id_for_bundle_paths(
    db_session, tmp_path
):
    service = WorkflowService(db_session)
    workflow_path = tmp_path / "workflow.nf"
    workflow_path.write_text("nextflow.enable.dsl=2\nworkflow { }\n", encoding="utf-8")

    workflow = await service.create_workflow(
        {
            "id": "../escaped-workflow",
            "source": "local",
            "engine": "nextflow",
            "name": f"safe-id-{uuid4()}",
            "source_ref": str(workflow_path),
        }
    )

    assert str(workflow.id) != "../escaped-workflow"
    assert workflow_bundle_home(str(workflow.id)).is_relative_to(local_workflows_root())
    assert not (local_workflows_root().parent / "escaped-workflow").exists()


@pytest.mark.asyncio
async def test_create_local_workflow_rejects_import_source_outside_allowed_roots(
    db_session,
):
    service = WorkflowService(db_session)

    with pytest.raises(ValueError, match="not allowed"):
        await service.create_workflow(
            {
                "source": "local",
                "engine": "nextflow",
                "name": f"unsafe-source-{uuid4()}",
                "source_ref": "/etc/passwd",
            }
        )


@pytest.mark.asyncio
async def test_update_workflow_rebuilds_form_spec_when_schema_changes(db_session):
    workflow = await create_workflow(
        db_session,
        name=f"wf-{uuid4()}",
        engine=WorkflowEngine.NEXTFLOW,
        content="nextflow.enable.dsl=2\nworkflow { }\n",
    )

    service = WorkflowService(db_session)
    updated = await service.update_workflow(
        workflow,
        {
            "schema_json": {
                "inputs": [
                    {
                        "name": "reads",
                        "type": "File",
                        "value_kind": "file",
                        "optional": False,
                    }
                ]
            }
        },
    )

    assert updated.form_spec is not None
    assert updated.form_spec["fields"][0]["id"] == "reads"
    assert updated.form_spec["fields"][0]["kind"] == "file"


@pytest.mark.asyncio
async def test_delete_local_workflow_removes_bundle_directory(db_session):
    workflow = await create_workflow(
        db_session,
        name=f"wf-{uuid4()}",
        engine=WorkflowEngine.NEXTFLOW,
        content="nextflow.enable.dsl=2\nworkflow { }\n",
    )
    workflow_root = workflow_home(str(workflow.id))
    assert workflow_root.exists()

    service = WorkflowService(db_session)
    await service.delete_workflow(workflow)

    assert await service.get_workflow(str(workflow.id)) is None
    assert not workflow_root.exists()


@pytest.mark.asyncio
async def test_resolve_source_path_returns_local_entrypoint_and_rejects_remote(
    db_session,
):
    local_workflow = await create_workflow(
        db_session,
        name=f"wf-{uuid4()}",
        engine=WorkflowEngine.NEXTFLOW,
        content="nextflow.enable.dsl=2\nworkflow { }\n",
    )
    remote_workflow = await create_workflow(
        db_session,
        name=f"wf-{uuid4()}",
        source=WorkflowSource.GITHUB,
        engine=WorkflowEngine.NEXTFLOW,
        version="main",
    )

    service = WorkflowService(db_session)

    assert service.resolve_source_path(local_workflow) == (
        workflow_bundle_home(str(local_workflow.id)) / "main.nf"
    )
    with pytest.raises(
        ValueError, match="source code is only available for local workflows"
    ):
        service.resolve_source_path(remote_workflow)
