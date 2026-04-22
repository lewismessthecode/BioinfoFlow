"""Unit tests for RunCompiler's compile path.

End-to-end coverage lives in test_run_lifecycle.py + test_runs.py (those
tests hit POST /runs which runs through the full compiler). These tests
focus on the pure helpers so regressions in key translation / path
resolution / table rendering surface clearly.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

import app.services.run_compiler as run_compiler_module
from app.path_layout import RunLayout
from app.schemas.form_spec import ColumnSpec, FormField, FormSpec
from app.schemas.run import RunCreate
from app.services.run_compiler import (
    CompileError,
    LaunchSpec,
    RunCompiler,
    _render_csv,
)


@pytest.mark.unit
def test_run_create_accepts_empty_values():
    payload = RunCreate(project_id=uuid4(), workflow_id=uuid4())
    assert payload.values == {}


@pytest.mark.unit
def test_run_create_rejects_legacy_fields():
    for legacy in ("params", "inputs", "submission", "submission_mode"):
        with pytest.raises(Exception):
            RunCreate(
                project_id=uuid4(),
                workflow_id=uuid4(),
                **{legacy: {"x": 1}},
            )


@pytest.mark.unit
def test_launch_spec_renders_shell_script():
    launch = LaunchSpec(
        argv=("nextflow", "run", "main.nf", "--params", "x=1"),
        env={"FOO": "bar", "BAZ": "with space"},
        cwd="/tmp/work",
        engine="nextflow",
    )
    script = launch.as_shell_script()
    assert script.startswith("#!/usr/bin/env bash")
    assert "export BAZ='with space'" in script
    assert "export FOO=bar" in script
    assert "cd /tmp/work" in script
    assert "exec nextflow run main.nf --params x=1" in script


@pytest.mark.unit
def test_render_csv_preserves_column_order_from_first_row():
    rows = [
        {"sample": "S1", "fastq_1": "/a.fq", "fastq_2": "/b.fq"},
        {"sample": "S2", "fastq_1": "/c.fq", "fastq_2": "/d.fq"},
    ]
    text = _render_csv(rows)
    lines = text.strip().splitlines()
    assert lines[0] == "sample,fastq_1,fastq_2"
    assert lines[1] == "S1,/a.fq,/b.fq"
    assert lines[2] == "S2,/c.fq,/d.fq"


@pytest.mark.unit
def test_build_engine_inputs_uses_absolute_results_dir_for_wdl_outdir(tmp_path):
    compiler = _make_compiler(storage=SimpleNamespace(resolve_asset=AsyncMock()))
    workspace_path = tmp_path / "project-home"
    workspace_path.mkdir(parents=True, exist_ok=True)
    layout = RunLayout.for_run(
        "project-1",
        "run_abs_outdir",
        "wdl",
        external_root_path=str(workspace_path),
    )
    workflow = SimpleNamespace(
        schema_json={
            "workflow_name": "resource_stress_mini",
            "inputs": [
                {
                    "name": "outdir",
                    "is_internal": True,
                }
            ],
        }
    )

    params, inputs, samples_count = compiler._build_engine_inputs(
        workflow=workflow,
        engine="wdl",
        spec=FormSpec(fields=[]),
        resolved_values={},
        layout=layout,
        workspace_path=workspace_path,
        run_id="run_abs_outdir",
    )

    assert samples_count == 0
    assert params["outdir"] == str(layout.results.resolve())
    assert inputs["resource_stress_mini.outdir"] == str(layout.results.resolve())


@pytest.mark.asyncio
async def test_resolve_path_cell_passes_absolute_paths_through():
    compiler = _make_compiler(storage=SimpleNamespace(resolve_asset=AsyncMock()))
    result = await compiler._resolve_path_cell("/abs/path.fq", project_id="p")
    assert result == "/abs/path.fq"
    compiler.storage.resolve_asset.assert_not_called()


@pytest.mark.asyncio
async def test_resolve_path_cell_resolves_asset_uris():
    resolved = SimpleNamespace(path="/data/sources/reference/hg38.fa")
    compiler = _make_compiler(
        storage=SimpleNamespace(resolve_asset=AsyncMock(return_value=resolved))
    )
    result = await compiler._resolve_path_cell(
        "asset://reference/hg38.fa", project_id="p"
    )
    assert result == "/data/sources/reference/hg38.fa"
    compiler.storage.resolve_asset.assert_awaited_once()


@pytest.mark.asyncio
async def test_resolve_path_cell_raises_compile_error_on_bad_asset():
    compiler = _make_compiler(
        storage=SimpleNamespace(
            resolve_asset=AsyncMock(side_effect=FileNotFoundError("missing"))
        )
    )
    with pytest.raises(CompileError) as exc_info:
        await compiler._resolve_path_cell(
            "asset://project/nope.fq", project_id="p"
        )
    assert exc_info.value.code == "ASSET_NOT_FOUND"


@pytest.mark.asyncio
async def test_resolve_values_skips_platform_managed_fields():
    spec = FormSpec(
        fields=[
            FormField(
                id="outdir",
                label="Out",
                section="advanced",
                kind="string",
                platform_managed=True,
            ),
            FormField(
                id="threads",
                label="Threads",
                section="params",
                kind="int",
            ),
        ]
    )
    compiler = _make_compiler(storage=SimpleNamespace(resolve_asset=AsyncMock()))
    resolved = await compiler._resolve_values(
        {"outdir": "ignored", "threads": 8}, spec, project_id="p"
    )
    assert resolved == {"threads": 8}


@pytest.mark.asyncio
async def test_resolve_values_resolves_table_path_columns():
    spec = FormSpec(
        fields=[
            FormField(
                id="sheet",
                label="Sheet",
                section="data",
                kind="table",
                columns=[
                    ColumnSpec(name="sample", kind="string"),
                    ColumnSpec(name="fastq_1", kind="path"),
                ],
            )
        ]
    )
    resolved_asset = SimpleNamespace(path="/data/a.fastq.gz")
    compiler = _make_compiler(
        storage=SimpleNamespace(
            resolve_asset=AsyncMock(return_value=resolved_asset)
        )
    )
    resolved = await compiler._resolve_values(
        {
            "sheet": {
                "filename": "samples.csv",
                "rows": [{"sample": "S1", "fastq_1": "asset://project/a.fastq.gz"}],
            }
        },
        spec,
        project_id="p",
    )
    assert resolved == {
        "sheet": {
            "filename": "samples.csv",
            "rows": [{"sample": "S1", "fastq_1": "/data/a.fastq.gz"}],
        }
    }


@pytest.mark.asyncio
async def test_resolve_values_rejects_manual_file_outside_allowed_roots(
    monkeypatch, tmp_path
):
    compiler = _make_compiler(
        storage=SimpleNamespace(resolve_asset=AsyncMock()),
        project_repo=SimpleNamespace(get=AsyncMock(return_value=SimpleNamespace(id="p"))),
    )
    roots = _configure_path_roots(monkeypatch, tmp_path)
    outside = roots["project_data"] / "reads.fastq.gz"
    outside.parent.mkdir(parents=True, exist_ok=True)
    outside.write_text("FASTQ", encoding="utf-8")

    spec = FormSpec(
        fields=[
            FormField(
                id="reference",
                label="Reference",
                section="data",
                kind="file",
                allow_roots=["reference"],
            )
        ]
    )

    with pytest.raises(CompileError) as exc_info:
        await compiler._resolve_values(
            {"reference": str(outside)},
            spec,
            project_id="p",
        )

    assert exc_info.value.code == "PATH_OUTSIDE_ALLOWED_ROOT"


@pytest.mark.asyncio
async def test_resolve_values_resolves_relative_project_data_paths(
    monkeypatch, tmp_path
):
    compiler = _make_compiler(
        storage=SimpleNamespace(resolve_asset=AsyncMock()),
        project_repo=SimpleNamespace(get=AsyncMock(return_value=SimpleNamespace(id="p"))),
    )
    roots = _configure_path_roots(monkeypatch, tmp_path)
    target = roots["project_data"] / "reads" / "sample.fastq.gz"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("FASTQ", encoding="utf-8")

    spec = FormSpec(
        fields=[
            FormField(
                id="reads",
                label="Reads",
                section="data",
                kind="file",
                allow_roots=["project_data"],
            )
        ]
    )

    resolved = await compiler._resolve_values(
        {"reads": "reads/sample.fastq.gz"},
        spec,
        project_id="p",
    )

    assert resolved == {"reads": str(target)}


@pytest.mark.asyncio
async def test_resolve_values_resolves_file_lists_within_allowed_roots(
    monkeypatch, tmp_path
):
    compiler = _make_compiler(
        storage=SimpleNamespace(resolve_asset=AsyncMock()),
        project_repo=SimpleNamespace(get=AsyncMock(return_value=SimpleNamespace(id="p"))),
    )
    roots = _configure_path_roots(monkeypatch, tmp_path)
    first = roots["project_data"] / "reads" / "sample_R1.fastq.gz"
    second = roots["project_data"] / "reads" / "sample_R2.fastq.gz"
    first.parent.mkdir(parents=True, exist_ok=True)
    first.write_text("R1", encoding="utf-8")
    second.write_text("R2", encoding="utf-8")

    spec = FormSpec(
        fields=[
            FormField(
                id="reads",
                label="Reads",
                section="data",
                kind="file_list",
                allow_roots=["project_data"],
            )
        ]
    )

    resolved = await compiler._resolve_values(
        {"reads": ["reads/sample_R1.fastq.gz", "reads/sample_R2.fastq.gz"]},
        spec,
        project_id="p",
    )

    assert resolved == {"reads": [str(first), str(second)]}


@pytest.mark.asyncio
async def test_resolve_values_resolves_table_paths_within_allowed_roots(
    monkeypatch, tmp_path
):
    compiler = _make_compiler(
        storage=SimpleNamespace(resolve_asset=AsyncMock()),
        project_repo=SimpleNamespace(get=AsyncMock(return_value=SimpleNamespace(id="p"))),
    )
    roots = _configure_path_roots(monkeypatch, tmp_path)
    target = roots["project_data"] / "reads" / "sample.fastq.gz"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("FASTQ", encoding="utf-8")

    spec = FormSpec(
        fields=[
            FormField(
                id="sheet",
                label="Sheet",
                section="data",
                kind="table",
                allow_roots=["project_data"],
                columns=[
                    ColumnSpec(name="sample", kind="string"),
                    ColumnSpec(name="fastq_1", kind="path"),
                ],
            )
        ]
    )

    resolved = await compiler._resolve_values(
        {
            "sheet": {
                "filename": "samples.csv",
                "rows": [{"sample": "S1", "fastq_1": "reads/sample.fastq.gz"}],
            }
        },
        spec,
        project_id="p",
    )

    assert resolved == {
        "sheet": {
            "filename": "samples.csv",
            "rows": [{"sample": "S1", "fastq_1": str(target)}],
        }
    }


def _make_compiler(*, storage, project_repo=None) -> RunCompiler:
    compiler = RunCompiler.__new__(RunCompiler)
    compiler.session = SimpleNamespace()
    compiler.storage = storage
    compiler.project_repo = project_repo or SimpleNamespace(
        get=AsyncMock(return_value=SimpleNamespace(id="p"))
    )
    return compiler


def _configure_path_roots(monkeypatch, tmp_path: Path) -> dict[str, Path]:
    roots = {
        "project_data": tmp_path / "project-data",
        "shared_data": tmp_path / "deliveries",
        "reference": tmp_path / "reference",
    }
    for root in roots.values():
        root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(
        run_compiler_module,
        "project_data_root",
        lambda project: roots["project_data"],
        raising=False,
    )
    monkeypatch.setattr(
        run_compiler_module,
        "deliveries_root",
        lambda: roots["shared_data"],
        raising=False,
    )
    monkeypatch.setattr(
        run_compiler_module,
        "reference_root",
        lambda: roots["reference"],
        raising=False,
    )
    return roots
