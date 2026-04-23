from __future__ import annotations

from uuid import uuid4

import pytest

from app.models.run import Run, RunStatus
from app.models.workflow import WorkflowEngine
from app.services.run_dag_service import RunDagService
from tests.support.path_contract import create_project, create_workflow


@pytest.mark.asyncio
async def test_get_dag_falls_back_to_workflow_schema_when_run_has_no_stored_dag(
    db_session, tmp_path
):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    project = await create_project(
        db_session,
        name=f"Project {uuid4()}",
        storage_mode="external",
        external_root_path=str(workspace),
    )
    workflow = await create_workflow(
        db_session,
        name=f"wf-{uuid4()}",
        engine=WorkflowEngine.NEXTFLOW,
        schema_json={
            "tasks": [
                {"name": "FASTQC", "inputs": ["reads"], "outputs": ["report"]},
                {"name": "ALIGN", "inputs": ["reads"], "outputs": ["bam"]},
            ],
            "dependencies": [{"source": "FASTQC", "target": "ALIGN"}],
        },
    )
    run = Run(
        run_id="run_schema_fallback",
        project_id=str(project.id),
        workflow_id=str(workflow.id),
        status=RunStatus.QUEUED.value,
        config={},
        samples_count=0,
        tasks_total=2,
        tasks_completed=0,
    )
    db_session.add(run)
    await db_session.commit()

    service = RunDagService(db_session)
    dag = await service.get_dag(run.run_id, user_id=project.user_id)

    assert [node["id"] for node in dag["nodes"]] == ["fastqc", "align"]
    assert dag["edges"][0]["source"] == "fastqc"
    assert dag["edges"][0]["target"] == "align"


@pytest.mark.asyncio
async def test_repair_run_dag_dry_run_reports_changes_without_persisting(db_session, tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    project = await create_project(
        db_session,
        name=f"Project {uuid4()}",
        storage_mode="external",
        external_root_path=str(workspace),
    )
    workflow = await create_workflow(
        db_session,
        name=f"wf-{uuid4()}",
        engine=WorkflowEngine.NEXTFLOW,
        content="nextflow.enable.dsl=2\nworkflow { }\n",
    )

    trace_dir = workspace / ".bioinfoflow" / "run_dry_repair"
    trace_dir.mkdir(parents=True)
    (trace_dir / "trace.tsv").write_text(
        "\n".join(
            [
                "task_id\thash\tnative_id\tname\tstatus\texit\t%cpu",
                "1\tabc\t1001\tREADS_STATS\tCOMPLETED\t0\t85.5",
            ]
        ),
        encoding="utf-8",
    )

    original_dag = {
        "nodes": [
            {
                "id": "reads_stats",
                "type": "pipeline",
                "position": {"x": 0, "y": 0},
                "data": {
                    "label": "READS_STATS",
                    "displayLabel": "READS_STATS",
                    "status": "pending",
                },
            }
        ],
        "edges": [],
    }
    run = Run(
        run_id="run_dry_repair",
        project_id=str(project.id),
        workflow_id=str(workflow.id),
        status=RunStatus.COMPLETED.value,
        config={
            "runtime": {"trace_path": ".bioinfoflow/run_dry_repair/trace.tsv"},
            "dag": original_dag,
        },
        samples_count=0,
        tasks_total=1,
        tasks_completed=1,
    )
    db_session.add(run)
    await db_session.commit()

    service = RunDagService(db_session)
    payload = await service.repair_run_dag(
        run.run_id,
        dry_run=True,
        user_id=project.user_id,
    )

    assert payload["repaired"] is True
    assert payload["reason"] == "dry-run"
    reloaded = await service.repo.get_by_run_id(run.run_id)
    assert reloaded.config["dag"]["nodes"][0]["data"]["status"] == "pending"


@pytest.mark.asyncio
async def test_create_mock_dag_variants_deduplicates_requested_variants(
    db_session, tmp_path
):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    project = await create_project(
        db_session,
        name=f"Project {uuid4()}",
        storage_mode="external",
        external_root_path=str(workspace),
    )
    workflow = await create_workflow(
        db_session,
        name=f"wf-{uuid4()}",
        engine=WorkflowEngine.NEXTFLOW,
        content="nextflow.enable.dsl=2\nworkflow { }\n",
    )
    source_run = Run(
        run_id="run_mock_source_dedup",
        project_id=str(project.id),
        workflow_id=str(workflow.id),
        status=RunStatus.COMPLETED.value,
        config={
            "params": {"outdir": "results"},
            "dag": {
                "nodes": [
                    {
                        "id": "reads_stats",
                        "type": "pipeline",
                        "position": {"x": 0, "y": 0},
                        "data": {
                            "label": "READS_STATS",
                            "displayLabel": "READS_STATS",
                            "status": "success",
                        },
                    }
                ],
                "edges": [],
            },
        },
        samples_count=0,
        tasks_total=1,
        tasks_completed=1,
    )
    db_session.add(source_run)
    await db_session.commit()

    service = RunDagService(db_session)
    payload = await service.create_mock_dag_variants(
        source_run.run_id,
        variants=["queued", "queued", "failed"],
        user_id=project.user_id,
    )

    assert [item["variant"] for item in payload["runs"]] == ["queued", "failed"]
    assert payload["runs"][0]["status"] == RunStatus.QUEUED.value
    assert payload["runs"][1]["status"] == RunStatus.FAILED.value


@pytest.mark.asyncio
async def test_create_mock_dag_variants_rejects_unknown_variant(db_session, tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    project = await create_project(
        db_session,
        name=f"Project {uuid4()}",
        storage_mode="external",
        external_root_path=str(workspace),
    )
    workflow = await create_workflow(
        db_session,
        name=f"wf-{uuid4()}",
        engine=WorkflowEngine.NEXTFLOW,
        content="nextflow.enable.dsl=2\nworkflow { }\n",
    )
    source_run = Run(
        run_id="run_mock_source_invalid",
        project_id=str(project.id),
        workflow_id=str(workflow.id),
        status=RunStatus.COMPLETED.value,
        config={
            "dag": {
                "nodes": [
                    {
                        "id": "reads_stats",
                        "type": "pipeline",
                        "position": {"x": 0, "y": 0},
                        "data": {
                            "label": "READS_STATS",
                            "displayLabel": "READS_STATS",
                            "status": "success",
                        },
                    }
                ],
                "edges": [],
            }
        },
        samples_count=0,
        tasks_total=1,
        tasks_completed=1,
    )
    db_session.add(source_run)
    await db_session.commit()

    service = RunDagService(db_session)
    with pytest.raises(ValueError, match="unsupported mock variant"):
        await service.create_mock_dag_variants(
            source_run.run_id,
            variants=["bogus"],
            user_id=project.user_id,
        )

