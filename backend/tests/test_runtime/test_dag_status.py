"""Tests for DAG status update and finalization logic in jobs.py."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.models.run import RunStatus
from app.runtime.jobs import (
    _apply_runtime_patch,
    _apply_process_statuses,
    _finalize_dag_statuses,
    _update_dag_task_status,
)


@pytest.fixture(autouse=True)
def _mock_flag_modified():
    """flag_modified requires a real SQLAlchemy model; stub it for unit tests."""
    with patch("app.runtime.jobs.flag_modified"):
        yield


def _make_dag(*node_names: str, status: str = "pending") -> dict:
    """Build a minimal DAG with named nodes."""
    from app.utils.dag_builder import normalize_dag_id

    nodes = [
        {
            "id": normalize_dag_id(name),
            "type": "pipeline",
            "position": {"x": 0, "y": 0},
            "data": {"label": name, "displayLabel": name, "status": status},
        }
        for name in node_names
    ]
    edges = []
    for i in range(len(nodes) - 1):
        edges.append(
            {
                "id": f"e_{nodes[i]['id']}_{nodes[i + 1]['id']}",
                "source": nodes[i]["id"],
                "target": nodes[i + 1]["id"],
                "animated": False,
            }
        )
    return {"nodes": nodes, "edges": edges}


def _make_run(dag: dict, status: str = RunStatus.RUNNING.value) -> SimpleNamespace:
    """Build a minimal run-like object with mutable config."""
    return SimpleNamespace(
        config={"dag": dag, "runtime": {}},
        status=status,
    )


# ---------- _update_dag_task_status ----------


@pytest.mark.asyncio
async def test_update_dag_task_status_with_workflow_prefix():
    """Task name with workflow prefix like 'nf-core/viralrecon:FASTQC(sample1)' should match node 'fastqc'."""
    dag = _make_dag("FASTQC", "ALIGNMENT", "VARIANT_CALLING")
    run = _make_run(dag)
    session = AsyncMock()

    await _update_dag_task_status(
        session, run, "nf-core/viralrecon:FASTQC (sample1)", "COMPLETED", None
    )

    node_statuses = {n["id"]: n["data"]["status"] for n in run.config["dag"]["nodes"]}
    assert node_statuses["fastqc"] == "success"
    assert node_statuses["alignment"] == "pending"
    assert node_statuses["variant_calling"] == "pending"


@pytest.mark.asyncio
async def test_update_dag_task_status_simple_name():
    """Simple task name like 'FASTQC (sample1)' should match node 'fastqc'."""
    dag = _make_dag("FASTQC", "MULTIQC")
    run = _make_run(dag)
    session = AsyncMock()

    await _update_dag_task_status(session, run, "FASTQC (sample1)", "RUNNING", None)

    node_statuses = {n["id"]: n["data"]["status"] for n in run.config["dag"]["nodes"]}
    assert node_statuses["fastqc"] == "running"
    assert node_statuses["multiqc"] == "pending"


@pytest.mark.asyncio
async def test_update_dag_task_status_no_match_preserves_existing_nodes_and_adds_runtime_node():
    """Unknown task names should keep schema node statuses while adding a runtime node."""
    dag = _make_dag("FASTQC", "MULTIQC")
    run = _make_run(dag)
    session = AsyncMock()

    await _update_dag_task_status(
        session, run, "UNKNOWN_PROCESS (x)", "COMPLETED", None
    )

    node_statuses = {n["id"]: n["data"]["status"] for n in run.config["dag"]["nodes"]}
    assert node_statuses["fastqc"] == "pending"
    assert node_statuses["multiqc"] == "pending"
    assert node_statuses["unknown_process"] == "success"


@pytest.mark.asyncio
async def test_update_dag_task_status_edge_animation():
    """Running node should animate its outgoing edge."""
    dag = _make_dag("FASTQC", "MULTIQC")
    run = _make_run(dag)
    session = AsyncMock()

    await _update_dag_task_status(session, run, "FASTQC", "RUNNING", None)

    edges = run.config["dag"]["edges"]
    assert edges[0]["animated"] is True


@pytest.mark.asyncio
async def test_update_dag_task_status_empty_dag_is_noop():
    """If DAG has no schema nodes, runtime task events should grow the DAG."""
    run = _make_run({"nodes": [], "edges": []})
    session = AsyncMock()

    await _update_dag_task_status(session, run, "FASTQC", "COMPLETED", None)
    nodes = run.config["dag"]["nodes"]
    assert len(nodes) == 1
    assert nodes[0]["id"] == "fastqc"
    assert nodes[0]["data"]["status"] == "success"
    assert nodes[0]["data"]["source"] == "runtime"


@pytest.mark.asyncio
async def test_update_dag_task_status_creates_runtime_node_when_no_match():
    dag = _make_dag("FASTQC")
    run = _make_run(dag)
    session = AsyncMock()

    await _update_dag_task_status(session, run, "ALIGNMENT", "RUNNING", None)

    node_ids = [node["id"] for node in run.config["dag"]["nodes"]]
    assert node_ids == ["fastqc", "alignment"]
    assert run.config["dag"]["nodes"][-1]["data"]["source"] == "runtime"
    assert run.config["dag"]["edges"] == [
        {
            "id": "e_fastqc_alignment",
            "source": "fastqc",
            "target": "alignment",
            "animated": True,
        }
    ]


# ---------- _finalize_dag_statuses ----------


@pytest.mark.asyncio
async def test_finalize_completed_run_sweeps_pending_to_success():
    """On a completed run, remaining pending/running nodes should become success."""
    dag = _make_dag("FASTQC", "ALIGNMENT", "VARIANT_CALLING")
    dag["nodes"][0]["data"]["status"] = "success"
    dag["nodes"][1]["data"]["status"] = "running"
    # node[2] stays "pending"

    run = _make_run(dag, status=RunStatus.COMPLETED.value)

    await _finalize_dag_statuses(run)

    statuses = {n["id"]: n["data"]["status"] for n in run.config["dag"]["nodes"]}
    assert statuses["fastqc"] == "success"
    assert statuses["alignment"] == "success"
    assert statuses["variant_calling"] == "success"


@pytest.mark.asyncio
async def test_finalize_failed_run_sweeps_running_to_failed():
    """On a failed run, running nodes should become failed; pending stays pending; success stays success."""
    dag = _make_dag("FASTQC", "ALIGNMENT", "VARIANT_CALLING")
    dag["nodes"][0]["data"]["status"] = "success"
    dag["nodes"][1]["data"]["status"] = "running"
    # node[2] stays "pending"

    run = _make_run(dag, status=RunStatus.FAILED.value)

    await _finalize_dag_statuses(run)

    statuses = {n["id"]: n["data"]["status"] for n in run.config["dag"]["nodes"]}
    assert statuses["fastqc"] == "success"
    assert statuses["alignment"] == "failed"
    assert statuses["variant_calling"] == "pending"


@pytest.mark.asyncio
async def test_finalize_stops_all_edge_animations():
    """All edge animations should stop after finalization."""
    dag = _make_dag("FASTQC", "MULTIQC")
    dag["edges"][0]["animated"] = True

    run = _make_run(dag, status=RunStatus.COMPLETED.value)

    await _finalize_dag_statuses(run)

    assert all(not e["animated"] for e in run.config["dag"]["edges"])


# ---------- _apply_process_statuses ----------


def test_apply_process_statuses_matches_normalized_ids():
    """Process names should be normalized before matching against node IDs."""
    dag = _make_dag("FASTQC", "VARIANT_CALLING")
    statuses = {"FASTQC": "success", "VARIANT_CALLING": "failed"}

    result = _apply_process_statuses(dag, statuses)

    node_statuses = {n["id"]: n["data"]["status"] for n in result["nodes"]}
    assert node_statuses["fastqc"] == "success"
    assert node_statuses["variant_calling"] == "failed"


@pytest.mark.asyncio
async def test_apply_runtime_patch_merges_runtime_without_dropping_existing_keys():
    run = SimpleNamespace(
        config={
            "runtime": {
                "dag_path": ".bioinfoflow/run_123/dag.dot",
                "trace_path": ".bioinfoflow/run_123/trace.tsv",
            }
        }
    )
    session = AsyncMock()

    await _apply_runtime_patch(
        session,
        run,
        {"runtime": {"docker_available": False}},
    )

    assert run.config["runtime"]["dag_path"] == ".bioinfoflow/run_123/dag.dot"
    assert run.config["runtime"]["trace_path"] == ".bioinfoflow/run_123/trace.tsv"
    assert run.config["runtime"]["docker_available"] is False
