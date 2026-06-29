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
    CompiledRun,
    LaunchSpec,
    RunCompiler,
    ValidatedRun,
    _render_csv,
)
from app.services.workflow_image_service import WorkflowImageRegistry


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
        await compiler._resolve_path_cell("asset://project/nope.fq", project_id="p")
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
        storage=SimpleNamespace(resolve_asset=AsyncMock(return_value=resolved_asset))
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
        project_repo=SimpleNamespace(
            get=AsyncMock(return_value=SimpleNamespace(id="p"))
        ),
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
        project_repo=SimpleNamespace(
            get=AsyncMock(return_value=SimpleNamespace(id="p"))
        ),
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
async def test_resolve_values_accepts_absolute_paths_through_symlinked_alias(
    monkeypatch, tmp_path
):
    compiler = _make_compiler(
        storage=SimpleNamespace(resolve_asset=AsyncMock()),
        project_repo=SimpleNamespace(
            get=AsyncMock(return_value=SimpleNamespace(id="p"))
        ),
    )
    roots = _configure_path_roots(monkeypatch, tmp_path)
    target = roots["reference"] / "hg38.fa"
    target.write_text(">chr1\n", encoding="utf-8")
    alias = tmp_path / "reference-alias"
    try:
        alias.symlink_to(roots["reference"], target_is_directory=True)
    except OSError as exc:  # pragma: no cover - platform/filesystem dependent
        pytest.skip(f"symlinks unavailable: {exc}")

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

    resolved = await compiler._resolve_values(
        {"reference": str(alias / "hg38.fa")},
        spec,
        project_id="p",
    )

    assert resolved == {"reference": str(target.resolve())}


@pytest.mark.asyncio
async def test_resolve_values_resolves_file_lists_within_allowed_roots(
    monkeypatch, tmp_path
):
    compiler = _make_compiler(
        storage=SimpleNamespace(resolve_asset=AsyncMock()),
        project_repo=SimpleNamespace(
            get=AsyncMock(return_value=SimpleNamespace(id="p"))
        ),
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
        project_repo=SimpleNamespace(
            get=AsyncMock(return_value=SimpleNamespace(id="p"))
        ),
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


def test_materialize_wdl_table_path_cells_into_current_run_input(tmp_path):
    compiler = _make_compiler(storage=SimpleNamespace(resolve_asset=AsyncMock()))
    project = SimpleNamespace(
        id="p",
        storage_mode="external",
        external_root_path=str(tmp_path / "project"),
    )
    layout = RunLayout.for_run(project, "run_wdl_table_paths", "wdl")
    upload_root = tmp_path / "project" / "state" / "run_uploads"
    source = upload_root / "upload-1" / "reads.fq.gz"
    source.parent.mkdir(parents=True)
    source.write_text("FASTQ", encoding="utf-8")
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

    materialized = compiler._materialize_runtime_inputs(
        {
            "sheet": {
                "filename": "samples.csv",
                "rows": [{"sample": "S1", "fastq_1": str(source)}],
            }
        },
        workflow=SimpleNamespace(source="remote", engine="wdl"),
        spec=spec,
        layout=layout,
        project=project,
    )

    copied = Path(materialized["sheet"]["rows"][0]["fastq_1"])
    assert copied != source
    assert copied.is_relative_to(layout.input.resolve())
    assert copied.read_text(encoding="utf-8") == "FASTQ"


@pytest.mark.asyncio
async def test_compile_wdl_launch_snapshot_does_not_pull_required_images(
    monkeypatch, tmp_path
):
    class FakeWDLAdapter:
        engine_name = "wdl"
        display_name = "MiniWDL"
        binary = "miniwdl"
        supports_native_resume = False

        def __init__(self):
            self.pre_submit_config: dict | None = None

        async def pre_submit(self, config: dict, workspace: str) -> dict:
            self.pre_submit_config = config
            return config

        async def build_command(self, config: dict, workspace: str) -> list[str]:
            return ["miniwdl", "run", config["workflow_path"]]

    adapter = FakeWDLAdapter()
    project_id = uuid4()
    workflow_id = uuid4()
    project_home = tmp_path / "project-home"
    workflow_path = tmp_path / "workflow.wdl"
    workflow_path.write_text("version 1.0\nworkflow wf {}\n", encoding="utf-8")

    compiler = _make_compiler(storage=SimpleNamespace(resolve_asset=AsyncMock()))
    monkeypatch.setattr(run_compiler_module, "get_adapter", lambda engine: adapter)
    monkeypatch.setattr(run_compiler_module, "generate_run_id", lambda: "run_wdl")
    monkeypatch.setattr(
        compiler,
        "_materialize_runtime_inputs",
        lambda resolved_values, **kwargs: resolved_values,
    )
    monkeypatch.setattr(
        compiler,
        "_build_engine_inputs",
        lambda **kwargs: ({}, {}, 0),
    )

    payload = RunCreate(project_id=project_id, workflow_id=workflow_id)
    validated = ValidatedRun(
        project=SimpleNamespace(
            id=str(project_id),
            storage_mode="external",
            external_root_path=str(project_home),
        ),
        workflow=SimpleNamespace(
            id=str(workflow_id),
            name="parabricks_container_smoke",
            engine="wdl",
            source="remote",
            source_ref=str(workflow_path),
            schema_json={
                "workflow_name": "parabricks_container_smoke",
                "tasks": [
                    {
                        "name": "smoke",
                        "container": "nvcr.io/nvidia/clara/clara-parabricks:4.7.0-1",
                    }
                ],
            },
        ),
        spec=FormSpec(fields=[]),
        submitted_values={},
        resolved_values={},
    )

    compiled = await compiler._compile(payload, validated=validated)

    assert isinstance(compiled, CompiledRun)
    assert adapter.pre_submit_config is not None
    assert adapter.pre_submit_config["runtime"]["required_images"] == [
        "nvcr.io/nvidia/clara/clara-parabricks:4.7.0-1"
    ]
    assert adapter.pre_submit_config["runtime"]["pull_required_images"] is False
    assert "pull_required_images" not in compiled.run.config["runtime"]


@pytest.mark.asyncio
async def test_compile_wdl_uses_resolved_registry_images_in_runtime_and_source(
    monkeypatch, tmp_path
):
    class FakeWDLAdapter:
        engine_name = "wdl"
        display_name = "MiniWDL"
        binary = "miniwdl"
        supports_native_resume = False

        def __init__(self):
            self.pre_submit_config: dict | None = None

        async def pre_submit(self, config: dict, workspace: str) -> dict:
            self.pre_submit_config = config
            return config

        async def build_command(self, config: dict, workspace: str) -> list[str]:
            return ["miniwdl", "run", config["workflow_path"]]

    adapter = FakeWDLAdapter()
    project_id = uuid4()
    workflow_id = uuid4()
    project_home = tmp_path / "project-home"
    workflow_path = tmp_path / "workflow.wdl"
    workflow_path.write_text(
        'version 1.0\n'
        'task align {\n'
        '  command <<< echo hi >>>\n'
        '  runtime { docker: "bwa:0.7.17" }\n'
        '}\n'
        'workflow wf { call align }\n',
        encoding="utf-8",
    )

    compiler = _make_compiler(storage=SimpleNamespace(resolve_asset=AsyncMock()))
    monkeypatch.setattr(run_compiler_module, "get_adapter", lambda engine: adapter)
    monkeypatch.setattr(run_compiler_module, "generate_run_id", lambda: "run_wdl")
    monkeypatch.setattr(
        compiler,
        "_resolve_workflow_image_registry",
        AsyncMock(
            return_value=WorkflowImageRegistry(
                endpoint="https://harbor.example.test",
                namespace="bio",
                registry_id="registry-1",
                auth_config={"username": "robot", "password": "secret"},
            )
        ),
        raising=False,
    )
    monkeypatch.setattr(
        compiler,
        "_materialize_runtime_inputs",
        lambda resolved_values, **kwargs: resolved_values,
    )
    monkeypatch.setattr(
        compiler,
        "_build_engine_inputs",
        lambda **kwargs: ({}, {}, 0),
    )
    monkeypatch.setattr(
        run_compiler_module,
        "workflow_entrypoint_path",
        lambda workflow: workflow_path,
    )

    payload = RunCreate(project_id=project_id, workflow_id=workflow_id)
    validated = ValidatedRun(
        project=SimpleNamespace(
            id=str(project_id),
            storage_mode="external",
            external_root_path=str(project_home),
        ),
        workflow=SimpleNamespace(
            id=str(workflow_id),
            name="wdl_registry_smoke",
            engine="wdl",
            source="local",
            source_ref="local",
            entrypoint_relpath="workflow.wdl",
            schema_json={
                "workflow_name": "wdl_registry_smoke",
                "tasks": [{"name": "align", "container": "bwa:0.7.17"}],
            },
        ),
        spec=FormSpec(fields=[]),
        submitted_values={},
        resolved_values={},
    )

    compiled = await compiler._compile(payload, validated=validated)

    expected_image = "harbor.example.test/bio/bwa:0.7.17"
    assert compiled.run.config["runtime"]["required_images"] == [
        {
            "full_name": expected_image,
            "name": "bio/bwa",
            "tag": "0.7.17",
            "registry": "harbor.example.test",
            "registry_id": "registry-1",
        }
    ]
    assert "secret" not in str(compiled.run.config)
    assert adapter.pre_submit_config is not None
    assert adapter.pre_submit_config["runtime"]["required_images"] == [
        {
            "full_name": expected_image,
            "name": "bio/bwa",
            "tag": "0.7.17",
            "registry": "harbor.example.test",
            "registry_id": "registry-1",
        }
    ]
    resolved_workflow_path = Path(compiled.run.config["workflow_path"])
    assert compiled.run.config["runtime"]["resolved_workflow_path"] == str(
        resolved_workflow_path
    )
    assert resolved_workflow_path != workflow_path
    assert resolved_workflow_path.exists()
    assert f'docker: "{expected_image}"' in resolved_workflow_path.read_text(
        encoding="utf-8"
    )
    assert compiled.launch.argv == ("miniwdl", "run", str(resolved_workflow_path))


@pytest.mark.asyncio
async def test_compile_nextflow_sets_registry_override_for_unqualified_images(
    monkeypatch, tmp_path
):
    class FakeNextflowAdapter:
        engine_name = "nextflow"
        display_name = "Nextflow"
        binary = "nextflow"
        supports_native_resume = True

        def __init__(self):
            self.pre_submit_config: dict | None = None

        async def pre_submit(self, config: dict, workspace: str) -> dict:
            self.pre_submit_config = config
            return config

        async def build_command(self, config: dict, workspace: str) -> list[str]:
            return ["nextflow", "run", config["pipeline"]]

    adapter = FakeNextflowAdapter()
    project_id = uuid4()
    workflow_id = uuid4()
    project_home = tmp_path / "project-home"
    compiler = _make_compiler(storage=SimpleNamespace(resolve_asset=AsyncMock()))
    monkeypatch.setattr(run_compiler_module, "get_adapter", lambda engine: adapter)
    monkeypatch.setattr(run_compiler_module, "generate_run_id", lambda: "run_nf")
    monkeypatch.setattr(
        compiler,
        "_resolve_workflow_image_registry",
        AsyncMock(
            return_value=WorkflowImageRegistry(
                endpoint="https://harbor.example.test",
                namespace="bio",
                registry_id="registry-1",
                auth_config=None,
            )
        ),
        raising=False,
    )
    monkeypatch.setattr(
        compiler,
        "_materialize_runtime_inputs",
        lambda resolved_values, **kwargs: resolved_values,
    )
    monkeypatch.setattr(
        compiler,
        "_build_engine_inputs",
        lambda **kwargs: ({}, {}, 0),
    )

    payload = RunCreate(project_id=project_id, workflow_id=workflow_id)
    validated = ValidatedRun(
        project=SimpleNamespace(
            id=str(project_id),
            storage_mode="external",
            external_root_path=str(project_home),
        ),
        workflow=SimpleNamespace(
            id=str(workflow_id),
            name="rnaseq",
            engine="nextflow",
            source="nf-core",
            source_ref="nf-core/rnaseq",
            version="3.18.0",
            schema_json={"tasks": [{"name": "align", "container": "bwa:0.7.17"}]},
        ),
        spec=FormSpec(fields=[]),
        submitted_values={},
        resolved_values={},
    )

    compiled = await compiler._compile(
        payload,
        validated=validated,
        config_overrides={"docker.registry": "registry.invalid/old"},
    )

    assert adapter.pre_submit_config is not None
    overrides = adapter.pre_submit_config["config_overrides"]
    assert overrides["docker.registry"] == "harbor.example.test/bio"
    assert adapter.pre_submit_config["request"]["config_overrides"][
        "docker.registry"
    ] == "harbor.example.test/bio"
    assert compiled.run.config["config_overrides"]["docker.registry"] == (
        "harbor.example.test/bio"
    )
    assert compiled.run.config["request"]["config_overrides"]["docker.registry"] == (
        "harbor.example.test/bio"
    )


def _make_compiler(*, storage, project_repo=None) -> RunCompiler:
    compiler = RunCompiler.__new__(RunCompiler)
    compiler.session = SimpleNamespace()
    compiler.storage = storage
    compiler.project_repo = project_repo or SimpleNamespace(
        get=AsyncMock(return_value=SimpleNamespace(id="p"))
    )
    compiler._resolve_workflow_image_registry = AsyncMock(return_value=None)
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
