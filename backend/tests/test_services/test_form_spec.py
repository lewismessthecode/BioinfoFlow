"""Tests for the deterministic FormSpec derivation that drives the run wizard."""

from __future__ import annotations

import json

import pytest

from app.engine.schema_extractor import derive_form_spec
from app.schemas.form_spec import FormSpec, to_read_projection
from app.services.workflow_form_spec import reconcile_workflow_form_spec
from app.services.validators.types import infer_source_hint, infer_value_kind


def _wdl_schema(inputs: list[dict]) -> dict:
    return {"workflow_name": "Demo", "inputs": inputs}


def _nf_schema(inputs: list[dict]) -> dict:
    return {"inputs": inputs}


def _by_id(spec: FormSpec) -> dict:
    return {field.id: field for field in spec.fields}


@pytest.mark.unit
def test_wdl_file_input_qualifies_engine_key_and_picks_data_section():
    spec = derive_form_spec(
        _wdl_schema(
            [
                {
                    "name": "reads",
                    "type": "File",
                    "value_kind": "file",
                    "optional": False,
                    "description": "Input reads",
                }
            ]
        ),
        "wdl",
    )
    fields = _by_id(spec)
    assert "reads" in fields
    field = fields["reads"]
    assert field.kind == "file"
    assert field.section == "data"
    assert field.required is True
    assert field.engine_key == "Demo.reads"
    assert field.allow_roots is not None and "project_data" in field.allow_roots


@pytest.mark.unit
def test_wdl_array_file_becomes_file_list():
    spec = derive_form_spec(
        _wdl_schema(
            [
                {
                    "name": "samples",
                    "type": "Array[File]",
                    "value_kind": "file_list",
                    "optional": True,
                }
            ]
        ),
        "wdl",
    )
    field = _by_id(spec)["samples"]
    assert field.kind == "file_list"
    assert field.required is False
    assert field.engine_key == "Demo.samples"


@pytest.mark.unit
def test_internal_input_marked_platform_managed_and_lives_in_advanced():
    spec = derive_form_spec(
        _wdl_schema(
            [
                {
                    "name": "outdir",
                    "type": "String",
                    "value_kind": "scalar",
                    "is_internal": True,
                    "optional": False,
                    "default": "results",
                }
            ]
        ),
        "wdl",
    )
    field = _by_id(spec)["outdir"]
    assert field.platform_managed is True
    assert field.section == "advanced"
    # platform-managed inputs are not user-required
    assert field.required is False


@pytest.mark.unit
def test_nextflow_file_param_keeps_unqualified_engine_key():
    spec = derive_form_spec(
        _nf_schema(
            [
                {
                    "name": "reads",
                    "type": "File",
                    "value_kind": "file",
                    "optional": False,
                }
            ]
        ),
        "nextflow",
    )
    field = _by_id(spec)["reads"]
    assert field.engine_key == "reads"
    assert field.kind == "file"


@pytest.mark.unit
def test_scalar_types_resolve_to_typed_kinds():
    spec = derive_form_spec(
        _nf_schema(
            [
                {
                    "name": "threads",
                    "type": "Int",
                    "value_kind": "scalar",
                    "default": "8",
                },
                {"name": "ratio", "type": "Float", "value_kind": "scalar"},
                {
                    "name": "skip",
                    "type": "Boolean",
                    "value_kind": "scalar",
                    "default": "false",
                },
                {"name": "mode", "type": "String", "value_kind": "scalar"},
            ]
        ),
        "nextflow",
    )
    fields = _by_id(spec)
    assert fields["threads"].kind == "int"
    assert fields["threads"].default == 8
    assert fields["ratio"].kind == "float"
    assert fields["skip"].kind == "bool"
    assert fields["skip"].default is False
    assert fields["mode"].kind == "string"


@pytest.mark.unit
def test_short_reference_substrings_do_not_turn_scalar_names_into_files():
    spec = derive_form_spec(
        _wdl_schema(
            [
                {
                    "name": "fanout",
                    "type": "Int",
                    "value_kind": "scalar",
                    "default": "30",
                },
                {
                    "name": "fatal_enabled",
                    "type": "Boolean",
                    "value_kind": "scalar",
                    "default": "false",
                },
            ]
        ),
        "wdl",
    )
    fields = _by_id(spec)
    assert fields["fanout"].kind == "int"
    assert fields["fatal_enabled"].kind == "bool"


@pytest.mark.unit
def test_infer_value_kind_does_not_treat_fa_substrings_as_reference_files():
    assert infer_value_kind("Int", name="fanout", default="30") == "scalar"
    assert (
        infer_value_kind("Boolean", name="fatal_enabled", default="false") == "scalar"
    )


@pytest.mark.unit
def test_infer_value_kind_keeps_null_reference_params_as_files():
    assert infer_value_kind("Any", name="reference", default="null") == "file"


@pytest.mark.unit
def test_infer_value_kind_treats_genome_build_names_as_scalars():
    assert infer_value_kind("Any", name="genome", default='"GRCh38"') == "scalar"
    assert (
        infer_value_kind("Any", name="genome", default="params.genome ?: 'GRCh38'")
        == "scalar"
    )


@pytest.mark.unit
def test_ambiguous_input_falls_back_to_string_no_inference():
    """If an input has no value_kind and no recognizable type, never guess
    that it's a samplesheet/CSV/path. Render as plain string."""
    spec = derive_form_spec(
        _nf_schema(
            [
                {
                    "name": "samplesheet",
                    "type": "",
                    "optional": False,
                    "default": "samplesheet.csv",
                }
            ]
        ),
        "nextflow",
    )
    field = _by_id(spec)["samplesheet"]
    assert field.kind == "string"
    # crucially, no `columns` was inferred
    assert field.columns is None


@pytest.mark.unit
def test_source_hint_orders_but_does_not_narrow_allow_roots():
    spec = derive_form_spec(
        _nf_schema(
            [
                {
                    "name": "genome",
                    "type": "File",
                    "value_kind": "file",
                    "source_hint": "reference",
                }
            ]
        ),
        "nextflow",
    )
    field = _by_id(spec)["genome"]
    assert field.allow_roots == ["reference", "shared_data", "database", "project_data"]


@pytest.mark.unit
def test_declared_allow_roots_override_source_hint_defaults():
    spec = derive_form_spec(
        _nf_schema(
            [
                {
                    "name": "genome",
                    "type": "File",
                    "value_kind": "file",
                    "source_hint": "reference",
                    "allow_roots": ["reference"],
                }
            ]
        ),
        "nextflow",
    )
    field = _by_id(spec)["genome"]
    assert field.allow_roots == ["reference"]


@pytest.mark.unit
def test_file_fields_default_to_all_browsable_input_roots():
    spec = derive_form_spec(
        _wdl_schema(
            [
                {
                    "name": "fastq_r1",
                    "type": "File",
                    "value_kind": "file",
                    "source_hint": "project",
                },
                {
                    "name": "reference",
                    "type": "File",
                    "value_kind": "file",
                    "source_hint": "reference",
                },
            ]
        ),
        "wdl",
    )

    fields = _by_id(spec)
    assert fields["fastq_r1"].allow_roots == [
        "shared_data",
        "reference",
        "database",
        "project_data",
    ]
    assert fields["reference"].allow_roots == [
        "reference",
        "shared_data",
        "database",
        "project_data",
    ]


@pytest.mark.unit
def test_source_hint_does_not_treat_fastq_fa_substring_as_reference():
    assert infer_source_hint(name="fastq_r1", value_kind="file") == "project"
    assert (
        infer_source_hint(name="reference_indexes", value_kind="file_list")
        == "reference"
    )


@pytest.mark.unit
def test_reference_side_inputs_and_extra_args_infer_stable_kinds():
    assert infer_value_kind("Any", name="known_sites", default="null") == "file"
    assert (
        infer_value_kind("Any", name="known_sites_indexes", default="[]") == "file_list"
    )
    assert (
        infer_value_kind("String", name="fq2bam_extra_args", default='""') == "scalar"
    )


@pytest.mark.unit
def test_jsonish_defaults_are_normalized_for_form_values():
    spec = derive_form_spec(
        _nf_schema(
            [
                {
                    "name": "samplesheet",
                    "type": "Any",
                    "value_kind": "file",
                    "default": '"samplesheet.csv"',
                },
                {
                    "name": "reference",
                    "type": "Any",
                    "value_kind": "file",
                    "default": "null",
                },
                {
                    "name": "reference_indexes",
                    "type": "Any",
                    "value_kind": "file_list",
                    "default": "[]",
                },
            ]
        ),
        "nextflow",
    )

    fields = _by_id(spec)
    assert fields["samplesheet"].default == "samplesheet.csv"
    assert fields["reference"].default is None
    assert fields["reference_indexes"].default == []


@pytest.mark.unit
def test_local_bundle_form_spec_can_override_allow_roots(tmp_path):
    bundle_root = tmp_path / "bundle"
    inputs_dir = bundle_root / "inputs"
    inputs_dir.mkdir(parents=True, exist_ok=True)
    (inputs_dir / "form-spec.overrides.json").write_text(
        json.dumps(
            {
                "samplesheet": {
                    "allow_roots": ["project_data", "shared_data"],
                }
            }
        ),
        encoding="utf-8",
    )

    spec = derive_form_spec(
        _nf_schema(
            [
                {
                    "name": "samplesheet",
                    "type": "File",
                    "value_kind": "file",
                    "source_hint": "project",
                }
            ]
        ),
        "nextflow",
    )

    reconciled = reconcile_workflow_form_spec(
        spec,
        workflow_id="wf-local",
        source="local",
        engine="nextflow",
        bundle_root=bundle_root,
    )

    field = _by_id(reconciled)["samplesheet"]
    assert field.allow_roots == ["project_data", "shared_data"]


@pytest.mark.unit
def test_read_projection_strips_engine_key():
    spec = derive_form_spec(
        _wdl_schema(
            [
                {"name": "reads", "type": "File", "value_kind": "file"},
            ]
        ),
        "wdl",
    )
    projection = to_read_projection(spec)
    payload = projection.model_dump()
    assert all("engine_key" not in field for field in payload["fields"])


@pytest.mark.unit
def test_empty_schema_yields_empty_spec():
    spec = derive_form_spec({}, "wdl")
    assert spec.fields == []
    spec = derive_form_spec(None, "nextflow")
    assert spec.fields == []
