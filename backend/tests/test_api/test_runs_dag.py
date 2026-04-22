from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.models.project import Project
from app.models.run import Run
from app.models.run import RunStatus
from app.models.workflow import Workflow, WorkflowEngine, WorkflowSource


@pytest.mark.asyncio
async def test_run_dag_matches_workflow_dag_for_schema_backed_workflows(
    async_client, db_session, tmp_path
):
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    schema = {
        "tasks": [
            {
                "name": "FASTQC",
                "inputs": ["reads"],
                "outputs": ["report"],
                "container": "biocontainers/fastqc:0.12.1",
            },
            {
                "name": "ALIGNMENT",
                "inputs": ["reads", "reference"],
                "outputs": ["bam"],
                "container": "biocontainers/bwa:0.7.17",
            },
        ],
        "dependencies": [
            {"source": "FASTQC", "target": "ALIGNMENT"},
        ],
    }

    project = Project(
        name="Schema DAG Project", storage_mode="external", external_root_path=str(workspace), user_id="dev"
    )
    workflow = Workflow(
        name=f"wf-{uuid4()}",
        source=WorkflowSource.LOCAL,
        engine=WorkflowEngine.NEXTFLOW,
        version=str(uuid4()),
        schema_json=schema,
    )
    db_session.add_all([project, workflow])
    await db_session.commit()
    await db_session.refresh(project)
    await db_session.refresh(workflow)

    run = Run(
        run_id="run_schema_dag",
        project_id=str(project.id),
        workflow_id=str(workflow.id),
        status=RunStatus.QUEUED.value,
        config={"params": {"outdir": "results"}},
        samples_count=0,
        tasks_total=2,
        tasks_completed=0,
    )
    db_session.add(run)
    await db_session.commit()

    workflow_dag_resp = await async_client.get(f"/api/v1/workflows/{workflow.id}/dag")
    run_dag_resp = await async_client.get(f"/api/v1/runs/{run.run_id}/dag")

    assert workflow_dag_resp.status_code == 200
    assert run_dag_resp.status_code == 200

    workflow_dag = workflow_dag_resp.json()["data"]
    run_dag = run_dag_resp.json()["data"]

    assert run_dag == workflow_dag
    assert workflow_dag["nodes"][0]["id"] == "fastqc"
    assert workflow_dag["nodes"][0]["data"] == {
        "label": "FASTQC",
        "displayLabel": "FASTQC",
        "status": "pending",
        "inputs": {"reads": "reads"},
        "outputs": {"report": "report"},
        "container": "biocontainers/fastqc:0.12.1",
    }
    assert workflow_dag["edges"] == [
        {
            "id": "e_fastqc_alignment",
            "source": "fastqc",
            "target": "alignment",
            "animated": False,
        }
    ]


@pytest.mark.asyncio
async def test_run_repair_dag_endpoint_repairs_terminal_statuses_from_trace(
    async_client, db_session, tmp_path
):
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    project = Project(
        name="Repair DAG Project", storage_mode="external", external_root_path=str(workspace), user_id="dev"
    )
    workflow = Workflow(
        name=f"wf-{uuid4()}",
        source=WorkflowSource.LOCAL,
        engine=WorkflowEngine.NEXTFLOW,
        version=str(uuid4()),
    )
    db_session.add_all([project, workflow])
    await db_session.commit()
    await db_session.refresh(project)
    await db_session.refresh(workflow)

    run_dir = workspace / ".bioinfoflow" / "run_repair_dag"
    run_dir.mkdir(parents=True)
    (run_dir / "trace.tsv").write_text(
        "\n".join(
            [
                "task_id\thash\tnative_id\tname\tstatus\texit\tsubmit\tduration\trealtime\t%cpu\tpeak_rss\tpeak_vmem\trchar\twchar",
                "1\t35/875c05\t81069\tREFERENCE_STATS (reference)\tCOMPLETED\t0\t2026-03-16 21:40:29.105\t130ms\t0ms\t-\t-\t-\t-\t-",
                "2\t23/8799be\t81071\tREADS_STATS (sample1)\tCOMPLETED\t0\t2026-03-16 21:40:29.117\t123ms\t0ms\t-\t-\t-\t-\t-",
                "3\t7d/2bf3db\t81125\tSUMMARY_REPORT (summary)\tCOMPLETED\t0\t2026-03-16 21:40:29.299\t98ms\t0ms\t-\t-\t-\t-\t-",
            ]
        ),
        encoding="utf-8",
    )

    run = Run(
        run_id="run_repair_dag",
        project_id=str(project.id),
        workflow_id=str(workflow.id),
        status=RunStatus.COMPLETED.value,
        config={
            "runtime": {"trace_path": ".bioinfoflow/run_repair_dag/trace.tsv"},
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
                            "status": "pending",
                        },
                    },
                    {
                        "id": "reference_stats",
                        "type": "pipeline",
                        "position": {"x": 200, "y": 0},
                        "data": {
                            "label": "REFERENCE_STATS",
                            "displayLabel": "REFERENCE_STATS",
                            "status": "pending",
                        },
                    },
                    {
                        "id": "summary_report",
                        "type": "pipeline",
                        "position": {"x": 100, "y": 120},
                        "data": {
                            "label": "SUMMARY_REPORT",
                            "displayLabel": "SUMMARY_REPORT",
                            "status": "pending",
                        },
                    },
                ],
                "edges": [
                    {
                        "id": "e_reads_stats_summary_report",
                        "source": "reads_stats",
                        "target": "summary_report",
                        "animated": True,
                    }
                ],
            },
        },
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
        samples_count=0,
        tasks_total=3,
        tasks_completed=3,
    )
    db_session.add(run)
    await db_session.commit()

    repair_resp = await async_client.post(f"/api/v1/runs/{run.run_id}/repair-dag")
    assert repair_resp.status_code == 200

    payload = repair_resp.json()["data"]
    assert payload["run_id"] == run.run_id
    assert payload["repaired"] is True
    assert payload["node_status_counts"] == {"success": 3}

    dag_resp = await async_client.get(f"/api/v1/runs/{run.run_id}/dag")
    statuses = [node["data"]["status"] for node in dag_resp.json()["data"]["nodes"]]
    assert statuses == ["success", "success", "success"]
    assert dag_resp.json()["data"]["edges"][0]["animated"] is False


@pytest.mark.asyncio
async def test_run_mock_dag_variants_endpoint_creates_status_samples(
    async_client, db_session, tmp_path
):
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    project = Project(
        name="Mock DAG Project", storage_mode="external", external_root_path=str(workspace), user_id="dev"
    )
    workflow = Workflow(
        name=f"wf-{uuid4()}",
        source=WorkflowSource.LOCAL,
        engine=WorkflowEngine.NEXTFLOW,
        version=str(uuid4()),
    )
    db_session.add_all([project, workflow])
    await db_session.commit()
    await db_session.refresh(project)
    await db_session.refresh(workflow)

    source_log_dir = workspace / ".bioinfoflow" / "run_mock_source"
    source_log_dir.mkdir(parents=True)
    (source_log_dir / "run.log").write_text("source log\n", encoding="utf-8")
    (workspace / "results").mkdir()

    source_run = Run(
        run_id="run_mock_source",
        project_id=str(project.id),
        workflow_id=str(workflow.id),
        status=RunStatus.COMPLETED.value,
        config={
            "log_path": ".bioinfoflow/run_mock_source/run.log",
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
                    },
                    {
                        "id": "reference_stats",
                        "type": "pipeline",
                        "position": {"x": 200, "y": 0},
                        "data": {
                            "label": "REFERENCE_STATS",
                            "displayLabel": "REFERENCE_STATS",
                            "status": "success",
                        },
                    },
                    {
                        "id": "summary_report",
                        "type": "pipeline",
                        "position": {"x": 100, "y": 120},
                        "data": {
                            "label": "SUMMARY_REPORT",
                            "displayLabel": "SUMMARY_REPORT",
                            "status": "success",
                        },
                    },
                ],
                "edges": [
                    {
                        "id": "e_reads_stats_summary_report",
                        "source": "reads_stats",
                        "target": "summary_report",
                        "animated": False,
                    },
                    {
                        "id": "e_reference_stats_summary_report",
                        "source": "reference_stats",
                        "target": "summary_report",
                        "animated": False,
                    },
                ],
            },
        },
        samples_count=0,
        tasks_total=3,
        tasks_completed=3,
    )
    db_session.add(source_run)
    await db_session.commit()

    mock_resp = await async_client.post(
        f"/api/v1/runs/{source_run.run_id}/mock-dag-variants"
    )
    assert mock_resp.status_code == 201

    data = mock_resp.json()["data"]
    assert data["source_run_id"] == source_run.run_id
    created = data["runs"]
    assert len(created) >= 4

    by_variant = {item["variant"]: item for item in created}
    assert {"pending", "queued", "running", "failed"}.issubset(by_variant)

    pending_dag = await async_client.get(
        f"/api/v1/runs/{by_variant['pending']['run_id']}/dag"
    )
    pending_statuses = {
        node["data"]["status"] for node in pending_dag.json()["data"]["nodes"]
    }
    assert pending_statuses == {"pending"}

    failed_dag = await async_client.get(
        f"/api/v1/runs/{by_variant['failed']['run_id']}/dag"
    )
    failed_statuses = {
        node["data"]["status"] for node in failed_dag.json()["data"]["nodes"]
    }
    assert "failed" in failed_statuses

    logs_resp = await async_client.get(
        f"/api/v1/runs/{by_variant['running']['run_id']}/logs"
    )
    assert logs_resp.status_code == 200
    assert logs_resp.json()["data"]["logs"]

    outputs_resp = await async_client.get(
        f"/api/v1/runs/{by_variant['queued']['run_id']}/outputs"
    )
    assert outputs_resp.status_code == 200
    assert outputs_resp.json()["data"]["files"]


@pytest.mark.asyncio
async def test_repair_run_dag_keeps_mock_variant_statuses_stable(
    async_client, db_session, tmp_path
):
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    project = Project(
        name="Mock DAG Repair Project", storage_mode="external", external_root_path=str(workspace), user_id="dev"
    )
    workflow = Workflow(
        name=f"wf-{uuid4()}",
        source=WorkflowSource.LOCAL,
        engine=WorkflowEngine.NEXTFLOW,
        version=str(uuid4()),
    )
    db_session.add_all([project, workflow])
    await db_session.commit()
    await db_session.refresh(project)
    await db_session.refresh(workflow)

    source_log_dir = workspace / ".bioinfoflow" / "run_mock_repair_source"
    source_log_dir.mkdir(parents=True)
    (source_log_dir / "run.log").write_text("source log\n", encoding="utf-8")
    (source_log_dir / "trace.tsv").write_text(
        "\n".join(
            [
                "task_id\thash\tnative_id\tname\tstatus\texit\tsubmit\tduration\trealtime\t%cpu\tpeak_rss\tpeak_vmem\trchar\twchar",
                "1\t35/875c05\t81069\tREFERENCE_STATS (reference)\tCOMPLETED\t0\t2026-03-16 21:40:29.105\t130ms\t0ms\t-\t-\t-\t-\t-",
                "2\t23/8799be\t81071\tREADS_STATS (sample1)\tCOMPLETED\t0\t2026-03-16 21:40:29.117\t123ms\t0ms\t-\t-\t-\t-\t-",
                "3\t7d/2bf3db\t81125\tSUMMARY_REPORT (summary)\tCOMPLETED\t0\t2026-03-16 21:40:29.299\t98ms\t0ms\t-\t-\t-\t-\t-",
            ]
        ),
        encoding="utf-8",
    )
    (workspace / "results").mkdir()

    source_run = Run(
        run_id="run_mock_repair_source",
        project_id=str(project.id),
        workflow_id=str(workflow.id),
        status=RunStatus.COMPLETED.value,
        config={
            "runtime": {"trace_path": ".bioinfoflow/run_mock_repair_source/trace.tsv"},
            "log_path": ".bioinfoflow/run_mock_repair_source/run.log",
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
                    },
                    {
                        "id": "reference_stats",
                        "type": "pipeline",
                        "position": {"x": 200, "y": 0},
                        "data": {
                            "label": "REFERENCE_STATS",
                            "displayLabel": "REFERENCE_STATS",
                            "status": "success",
                        },
                    },
                    {
                        "id": "summary_report",
                        "type": "pipeline",
                        "position": {"x": 100, "y": 120},
                        "data": {
                            "label": "SUMMARY_REPORT",
                            "displayLabel": "SUMMARY_REPORT",
                            "status": "success",
                        },
                    },
                ],
                "edges": [
                    {
                        "id": "e_reads_stats_summary_report",
                        "source": "reads_stats",
                        "target": "summary_report",
                        "animated": False,
                    },
                    {
                        "id": "e_reference_stats_summary_report",
                        "source": "reference_stats",
                        "target": "summary_report",
                        "animated": False,
                    },
                ],
            },
        },
        samples_count=0,
        tasks_total=3,
        tasks_completed=3,
    )
    db_session.add(source_run)
    await db_session.commit()

    mock_resp = await async_client.post(
        f"/api/v1/runs/{source_run.run_id}/mock-dag-variants?variants=failed"
    )
    assert mock_resp.status_code == 201
    failed_run_id = mock_resp.json()["data"]["runs"][0]["run_id"]

    repair_resp = await async_client.post(f"/api/v1/runs/{failed_run_id}/repair-dag")
    assert repair_resp.status_code == 200
    assert repair_resp.json()["data"]["repaired"] is False

    dag_resp = await async_client.get(f"/api/v1/runs/{failed_run_id}/dag")
    statuses = [node["data"]["status"] for node in dag_resp.json()["data"]["nodes"]]
    assert statuses == ["failed", "success", "pending"]


@pytest.mark.asyncio
async def test_repair_run_dags_endpoint_supports_bulk_project_repair(
    async_client, db_session, tmp_path
):
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    project = Project(
        name="Bulk Repair Project", storage_mode="external", external_root_path=str(workspace), user_id="dev"
    )
    workflow = Workflow(
        name=f"wf-{uuid4()}",
        source=WorkflowSource.LOCAL,
        engine=WorkflowEngine.NEXTFLOW,
        version=str(uuid4()),
    )
    db_session.add_all([project, workflow])
    await db_session.commit()
    await db_session.refresh(project)
    await db_session.refresh(workflow)

    for run_name in ("run_bulk_repair_a", "run_bulk_repair_b"):
        run_dir = workspace / ".bioinfoflow" / run_name
        run_dir.mkdir(parents=True)
        (run_dir / "trace.tsv").write_text(
            "\n".join(
                [
                    "task_id\thash\tnative_id\tname\tstatus\texit\tsubmit\tduration\trealtime\t%cpu\tpeak_rss\tpeak_vmem\trchar\twchar",
                    "1\t35/875c05\t81069\tREADS_STATS (sample1)\tCOMPLETED\t0\t2026-03-16 21:40:29.117\t123ms\t0ms\t-\t-\t-\t-\t-",
                ]
            ),
            encoding="utf-8",
        )
        db_session.add(
            Run(
                run_id=run_name,
                project_id=str(project.id),
                workflow_id=str(workflow.id),
                status=RunStatus.COMPLETED.value,
                config={
                    "runtime": {"trace_path": f".bioinfoflow/{run_name}/trace.tsv"},
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
                                    "status": "pending",
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
        )
    await db_session.commit()

    resp = await async_client.post(f"/api/v1/runs/repair-dags?project_id={project.id}")
    assert resp.status_code == 200
    payload = resp.json()["data"]
    assert payload["summary"]["total"] == 2
    assert payload["summary"]["repaired"] == 2
    assert all(item["node_status_counts"] == {"success": 1} for item in payload["runs"])
