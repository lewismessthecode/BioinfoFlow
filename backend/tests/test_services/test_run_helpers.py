from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.run_helpers import (
    build_mock_variant_dag,
    resolve_payload_paths,
    resolve_resume_token,
    write_samplesheet_csv,
)


def test_resolve_payload_paths_tracks_resolved_file_inputs(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "reads.fastq.gz").write_text("reads", encoding="utf-8")

    payload = {
        "input_file": "reads.fastq.gz",
        "config_uri": "s3://bucket/config.json",
        "output_dir": "results",
        "reads_glob": "reads/*.fastq.gz",
        "threads": 4,
    }

    resolved, files = resolve_payload_paths(
        workspace_path=workspace,
        payload=payload,
        scope="inputs",
    )

    assert resolved["input_file"] == str(workspace / "reads.fastq.gz")
    assert resolved["config_uri"] == "s3://bucket/config.json"
    assert resolved["output_dir"] == "results"
    assert resolved["reads_glob"] == str(workspace / "reads/*.fastq.gz")
    assert resolved["threads"] == 4
    assert files == [
        {
            "scope": "inputs",
            "key": "input_file",
            "kind": "path",
            "raw": "reads.fastq.gz",
            "resolved": str(workspace / "reads.fastq.gz"),
        },
        {
            "scope": "inputs",
            "key": "reads_glob",
            "kind": "glob",
            "raw": "reads/*.fastq.gz",
            "resolved": str(workspace / "reads/*.fastq.gz"),
        },
    ]


def test_resolve_resume_token_prefers_session_id_then_resume_token_then_run_name():
    run = SimpleNamespace(
        config={
            "runtime": {
                "session_id": "12345678-1234-5678-1234-567812345678",
                "resume_token": "resume-token",
            }
        },
        nextflow_run_name="nf-run-name",
    )
    assert resolve_resume_token(run) == "12345678-1234-5678-1234-567812345678"

    run.config["runtime"]["session_id"] = "not-a-uuid"
    assert resolve_resume_token(run) == "resume-token"

    run.config["runtime"]["resume_token"] = "bad/token"
    assert resolve_resume_token(run) == "nf-run-name"

    run.nextflow_run_name = "bad/name"
    assert resolve_resume_token(run) is None


def test_build_mock_variant_dag_sets_statuses_without_mutating_source():
    source_dag = {
        "nodes": [
            {"id": "align", "data": {"label": "Align", "status": "pending"}},
            {"id": "qc", "data": {"label": "QC", "status": "pending"}},
        ],
        "edges": [{"id": "e_align_qc", "source": "align", "target": "qc", "animated": False}],
    }

    running = build_mock_variant_dag(source_dag, "running")
    failed = build_mock_variant_dag(source_dag, "failed")

    assert source_dag["nodes"][0]["data"]["status"] == "pending"
    assert [node["data"]["status"] for node in running["nodes"]] == ["running", "success"]
    assert running["edges"][0]["animated"] is True
    assert [node["data"]["status"] for node in failed["nodes"]] == ["failed", "success"]
    assert failed["edges"][0]["animated"] is False


def test_write_samplesheet_csv_writes_rows_and_validates_referenced_files(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "sampleA_R1.fastq.gz").write_text("r1", encoding="utf-8")
    (workspace / "sampleA_R2.fastq.gz").write_text("r2", encoding="utf-8")
    dest = tmp_path / "samplesheet.csv"

    write_samplesheet_csv(
        workspace,
        [{"id": "sampleA", "r1": "sampleA_R1.fastq.gz", "r2": "sampleA_R2.fastq.gz"}],
        dest,
        headers=("sample", "fastq_1", "fastq_2"),
        extract_row=lambda row: (
            [row["id"], row["r1"], row["r2"]],
            [row["r1"], row["r2"]],
        ),
        error_label="FASTQ",
    )

    assert dest.read_text(encoding="utf-8") == (
        "sample,fastq_1,fastq_2\n"
        "sampleA,sampleA_R1.fastq.gz,sampleA_R2.fastq.gz\n"
    )

    with pytest.raises(FileNotFoundError, match="sample FASTQ not found"):
        write_samplesheet_csv(
            workspace,
            [{"id": "sampleB", "r1": "missing.fastq.gz", "r2": "sampleA_R2.fastq.gz"}],
            dest,
            headers=("sample", "fastq_1", "fastq_2"),
            extract_row=lambda row: (
                [row["id"], row["r1"], row["r2"]],
                [row["r1"], row["r2"]],
            ),
            error_label="FASTQ",
        )
