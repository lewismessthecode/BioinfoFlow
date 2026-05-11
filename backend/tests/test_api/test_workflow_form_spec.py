"""Tests for GET /workflows/{id}/form-spec — covers fresh creation and lazy backfill."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.schemas.form_spec import FormSpec
from app.path_layout import project_data_root, reference_root
from app.services.run_dispatch import set_run_dispatcher
from tests.support.path_contract import bind_workflow, create_project

REPO_ROOT = Path(__file__).resolve().parents[3]


class NoopDispatcher:
    def dispatch(self, run_id: str, *, priority: str = "normal") -> None:
        del run_id, priority


@pytest.mark.asyncio
async def test_form_spec_endpoint_returns_projected_spec(async_client):
    schema = {
        "workflow_name": "Demo",
        "inputs": [
            {
                "name": "reads",
                "type": "File",
                "value_kind": "file",
                "optional": False,
                "description": "Input reads",
            },
            {
                "name": "threads",
                "type": "Int",
                "value_kind": "scalar",
                "optional": True,
                "default": "8",
            },
            {
                "name": "outdir",
                "type": "String",
                "value_kind": "scalar",
                "is_internal": True,
                "default": "results",
            },
        ],
    }
    with patch(
        "app.services.workflow_service.SchemaExtractor.extract",
        new_callable=AsyncMock,
        return_value=schema,
    ):
        create = await async_client.post(
            "/api/v1/workflows",
            json={
                "source": "nf-core",
                "name": "demo-wf",
                "version": "1.0.0",
                "engine": "wdl",
            },
        )
    assert create.status_code == 201
    workflow_id = create.json()["data"]["id"]

    resp = await async_client.get(f"/api/v1/workflows/{workflow_id}/form-spec")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert "fields" in data
    field_ids = [field["id"] for field in data["fields"]]
    assert {"reads", "threads", "outdir"} <= set(field_ids)
    # Frontend projection must omit engine_key
    assert all("engine_key" not in field for field in data["fields"])

    reads = next(field for field in data["fields"] if field["id"] == "reads")
    assert reads["kind"] == "file"
    assert reads["section"] == "data"
    assert reads["required"] is True

    outdir = next(field for field in data["fields"] if field["id"] == "outdir")
    assert outdir["platform_managed"] is True
    assert outdir["section"] == "advanced"


@pytest.mark.asyncio
async def test_form_spec_lazy_backfill_for_legacy_workflow(async_client, db_session):
    """Workflows that were created before the form_spec column existed get
    a spec generated on first GET, persisted, then served."""
    from app.models.workflow import Workflow

    legacy = Workflow(
        name="legacy-wf",
        source="local",
        engine="nextflow",
        version="0.0.1",
        schema_json={
            "inputs": [{"name": "input", "type": "File", "value_kind": "file"}]
        },
        form_spec=None,
    )
    db_session.add(legacy)
    await db_session.commit()
    await db_session.refresh(legacy)

    resp = await async_client.get(f"/api/v1/workflows/{legacy.id}/form-spec")
    assert resp.status_code == 200
    fields = resp.json()["data"]["fields"]
    assert any(field["id"] == "input" for field in fields)

    # second call should return the persisted spec without rebuilding
    await db_session.refresh(legacy)
    assert isinstance(legacy.form_spec, dict)
    assert "fields" in legacy.form_spec


@pytest.mark.asyncio
async def test_form_spec_lazy_backfill_normalizes_nfcore_json_schema(
    async_client,
    db_session,
):
    from app.models.workflow import Workflow

    legacy = Workflow(
        name="nf-core/rnaseq",
        source="nf-core",
        engine="nextflow",
        version="3.24.0",
        source_ref="nf-core/rnaseq",
        schema_json={
            "allOf": [{"$ref": "#/$defs/input_output_options"}],
            "$defs": {
                "input_output_options": {
                    "required": ["input", "outdir"],
                    "properties": {
                        "input": {
                            "type": "string",
                            "format": "file-path",
                            "description": "Samplesheet.",
                        },
                        "outdir": {
                            "type": "string",
                            "format": "directory-path",
                        },
                    },
                }
            },
        },
        form_spec=None,
    )
    db_session.add(legacy)
    await db_session.commit()
    await db_session.refresh(legacy)

    resp = await async_client.get(f"/api/v1/workflows/{legacy.id}/form-spec")

    assert resp.status_code == 200, resp.json()
    fields = {field["id"]: field for field in resp.json()["data"]["fields"]}
    assert fields["input"]["kind"] == "file"
    assert fields["input"]["required"] is True
    assert fields["outdir"]["kind"] == "directory"
    assert fields["outdir"]["platform_managed"] is True


@pytest.mark.asyncio
async def test_form_spec_404_for_unknown_workflow(async_client):
    resp = await async_client.get(
        "/api/v1/workflows/00000000-0000-0000-0000-000000000000/form-spec"
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("engine", "file_name", "content", "expected_field", "input_value"),
    [
        (
            "wdl",
            "demo.wdl",
            "version 1.0\nworkflow demo {\n  input {\n    File reads\n  }\n}\n",
            "reads",
            "asset://project/reads/sample.fastq.gz",
        ),
        (
            "nextflow",
            "main.nf",
            "nextflow.enable.dsl=2\nparams.reference = null\nworkflow { }\n",
            "reference",
            "asset://reference/hg38.fa",
        ),
    ],
)
async def test_newly_registered_local_workflow_can_render_form_spec_and_submit_run(
    async_client,
    db_session,
    engine,
    file_name,
    content,
    expected_field,
    input_value,
):
    project = await create_project(db_session, name=f"{engine}-registration-project")
    if input_value.startswith("asset://reference/"):
        target = reference_root() / input_value.removeprefix("asset://reference/")
    else:
        target = project_data_root(project) / input_value.removeprefix(
            "asset://project/"
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("demo", encoding="utf-8")

    dispatcher = NoopDispatcher()
    set_run_dispatcher(dispatcher)
    try:
        create_resp = await async_client.post(
            "/api/v1/workflows",
            json={
                "source": "local",
                "engine": engine,
                "file_name": file_name,
                "content": content,
            },
        )
        assert create_resp.status_code == 201, create_resp.json()
        workflow_id = create_resp.json()["data"]["id"]

        await bind_workflow(
            db_session, project_id=str(project.id), workflow_id=str(workflow_id)
        )

        form_spec_resp = await async_client.get(
            f"/api/v1/workflows/{workflow_id}/form-spec"
        )
        assert form_spec_resp.status_code == 200, form_spec_resp.json()
        spec = FormSpec.model_validate(form_spec_resp.json()["data"])
        assert any(field.id == expected_field for field in spec.fields)

        submit_resp = await async_client.post(
            "/api/v1/runs",
            json={
                "project_id": str(project.id),
                "workflow_id": workflow_id,
                "values": {expected_field: input_value},
            },
        )
        assert submit_resp.status_code == 202, submit_resp.json()
        assert submit_resp.json()["data"]["status"] == "queued"
    finally:
        set_run_dispatcher(None)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("engine", "bundle_relpath", "field_id"),
    [
        ("nextflow", "demo/rnaseq-quant-mini", "samplesheet"),
        ("wdl", "demo/variant-fanout-mini", "samples_tsv"),
    ],
)
async def test_local_bundle_form_spec_marks_manifest_fields_for_run_materialization(
    async_client,
    engine,
    bundle_relpath,
    field_id,
):
    create_resp = await async_client.post(
        "/api/v1/workflows",
        json={
            "source": "local",
            "engine": engine,
            "bundle_path": str(REPO_ROOT / bundle_relpath),
        },
    )
    assert create_resp.status_code == 201, create_resp.json()
    workflow_id = create_resp.json()["data"]["id"]

    spec_resp = await async_client.get(f"/api/v1/workflows/{workflow_id}/form-spec")
    assert spec_resp.status_code == 200, spec_resp.json()

    fields = {field["id"]: field for field in spec_resp.json()["data"]["fields"]}
    assert fields[field_id]["default"] is None
    assert fields[field_id]["materialize_to_run"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("engine", "bundle_relpath", "field_id"),
    [
        ("nextflow", "demo/rnaseq-quant-mini", "samplesheet"),
        ("wdl", "demo/variant-fanout-mini", "samples_tsv"),
    ],
)
async def test_local_bundle_form_spec_returns_declared_allow_roots(
    async_client,
    tmp_path,
    engine,
    bundle_relpath,
    field_id,
):
    source_bundle = REPO_ROOT / bundle_relpath
    bundle_root = tmp_path / source_bundle.name
    shutil.copytree(source_bundle, bundle_root)
    inputs_dir = bundle_root / "inputs"
    inputs_dir.mkdir(parents=True, exist_ok=True)
    (inputs_dir / "form-spec.overrides.json").write_text(
        json.dumps(
            {
                field_id: {
                    "allow_roots": ["project_data", "shared_data"],
                }
            }
        ),
        encoding="utf-8",
    )

    create_resp = await async_client.post(
        "/api/v1/workflows",
        json={
            "source": "local",
            "engine": engine,
            "bundle_path": str(bundle_root),
        },
    )
    assert create_resp.status_code == 201, create_resp.json()
    workflow_id = create_resp.json()["data"]["id"]

    spec_resp = await async_client.get(f"/api/v1/workflows/{workflow_id}/form-spec")
    assert spec_resp.status_code == 200, spec_resp.json()

    fields = {field["id"]: field for field in spec_resp.json()["data"]["fields"]}
    assert fields[field_id]["allow_roots"] == ["project_data", "shared_data"]
