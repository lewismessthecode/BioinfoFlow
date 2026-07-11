from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.engine.schema_extractor import (
    SchemaExtractor,
    derive_form_spec,
    normalize_extracted_schema,
)


@pytest.mark.asyncio
async def test_schema_extractor_uses_adapter_schema_when_available():
    extractor = SchemaExtractor()
    adapter = SimpleNamespace(
        extract_schema=AsyncMock(
            return_value={
                "tasks": [{"name": "FASTQC"}],
                "dependencies": [],
                "inputs": [],
                "outputs": [],
            }
        )
    )

    with patch("app.engine.schema_extractor.get_adapter", return_value=adapter):
        schema = await extractor.extract("nextflow", source="nf-core/viralrecon")

    assert schema["tasks"] == [{"name": "FASTQC"}]
    adapter.extract_schema.assert_awaited_once_with("nf-core/viralrecon")


@pytest.mark.asyncio
async def test_schema_extractor_falls_back_to_validator_for_content():
    extractor = SchemaExtractor()
    adapter = SimpleNamespace(extract_schema=AsyncMock(return_value=None))
    fallback_schema = {
        "tasks": [{"name": "ALIGNMENT"}],
        "dependencies": [{"source": "FASTQC", "target": "ALIGNMENT"}],
        "inputs": [],
        "outputs": [],
        "workflow_name": "fallback",
        "version": None,
        "description": None,
    }

    with (
        patch("app.engine.schema_extractor.get_adapter", return_value=adapter),
        patch("app.services.workflow_validator.WorkflowValidator") as validator_cls,
    ):
        validator = validator_cls.return_value
        validator.validate.return_value.to_schema_json.return_value = fallback_schema

        schema = await extractor.extract(
            "nextflow",
            source=None,
            content="process ALIGNMENT { script: 'echo hi' } workflow { ALIGNMENT() }",
            file_name="workflow.nf",
        )

    assert schema == fallback_schema
    validator.validate.assert_called_once()


@pytest.mark.asyncio
async def test_schema_extractor_returns_empty_schema_without_source_or_content():
    extractor = SchemaExtractor()
    adapter = SimpleNamespace(extract_schema=AsyncMock(return_value=None))

    with patch("app.engine.schema_extractor.get_adapter", return_value=adapter):
        schema = await extractor.extract("nextflow", source=None)

    assert schema == {
        "tasks": [],
        "dependencies": [],
        "inputs": [],
        "outputs": [],
    }


@pytest.mark.asyncio
async def test_schema_extractor_keeps_non_dag_schema_content_from_adapter():
    extractor = SchemaExtractor()
    adapter = SimpleNamespace(
        extract_schema=AsyncMock(
            return_value={
                "tasks": [],
                "dependencies": [],
                "inputs": [{"name": "reads", "type": "string"}],
                "outputs": [],
            }
        )
    )

    with patch("app.engine.schema_extractor.get_adapter", return_value=adapter):
        schema = await extractor.extract("nextflow", source="nf-core/demo")

    assert schema["inputs"] == [{"name": "reads", "type": "string"}]


@pytest.mark.parametrize(
    "name",
    ["outdir", "output_dir", "publish_dir"],
)
def test_json_schema_managed_run_directories_are_internal(name):
    schema = normalize_extracted_schema(
        {
            "$defs": {},
            "required": [name],
            "properties": {
                name: {
                    "type": "string",
                    "format": "directory-path",
                }
            },
        },
        engine="nextflow",
    )

    assert schema is not None
    inputs = {item["name"]: item for item in schema["inputs"]}
    assert inputs[name].get("is_internal") is True
    assert inputs[name]["optional"] is True


def test_json_schema_work_dir_remains_a_required_user_input():
    schema = normalize_extracted_schema(
        {
            "$defs": {},
            "required": ["work_dir"],
            "properties": {
                "work_dir": {
                    "type": "string",
                    "format": "directory-path",
                }
            },
        },
        engine="nextflow",
    )

    assert schema is not None
    work_dir = next(item for item in schema["inputs"] if item["name"] == "work_dir")
    assert work_dir.get("is_internal") is None
    assert work_dir["optional"] is False

    field = derive_form_spec(schema, "nextflow").fields[0]
    assert field.required is True
    assert field.platform_managed is False


@pytest.mark.asyncio
async def test_schema_extractor_normalizes_nfcore_json_schema_to_inputs():
    extractor = SchemaExtractor()
    adapter = SimpleNamespace(
        extract_schema=AsyncMock(
            return_value={
                "$schema": "http://json-schema.org/draft-07/schema",
                "title": "nf-core/rnaseq pipeline parameters",
                "allOf": [
                    {"$ref": "#/$defs/input_output_options"},
                    {"$ref": "#/$defs/reference_options"},
                    {"$ref": "#/$defs/advanced_options"},
                ],
                "$defs": {
                    "input_output_options": {
                        "title": "Input/output options",
                        "required": ["input", "outdir"],
                        "properties": {
                            "input": {
                                "type": "string",
                                "format": "file-path",
                                "description": "Path to comma-separated samplesheet.",
                            },
                            "outdir": {
                                "type": "string",
                                "format": "directory-path",
                                "description": "Output directory.",
                            },
                        },
                    },
                    "reference_options": {
                        "title": "Reference genome options",
                        "properties": {
                            "genome": {
                                "type": "string",
                                "enum": ["GRCh37", "GRCh38"],
                                "default": "GRCh38",
                            },
                            "fasta": {
                                "type": "string",
                                "format": "path",
                                "description": "Genome FASTA file.",
                            },
                        },
                    },
                    "advanced_options": {
                        "title": "Advanced options",
                        "properties": {
                            "internal_cache": {
                                "type": "string",
                                "hidden": True,
                            }
                        },
                    },
                },
            }
        )
    )

    with patch("app.engine.schema_extractor.get_adapter", return_value=adapter):
        schema = await extractor.extract(
            "nextflow",
            source="nf-core/rnaseq",
            version="3.24.0",
        )

    adapter.extract_schema.assert_awaited_once_with("nf-core/rnaseq", version="3.24.0")
    inputs = {item["name"]: item for item in schema["inputs"]}
    assert {"input", "outdir", "genome", "fasta"} <= set(inputs)
    assert "internal_cache" not in inputs
    assert inputs["input"]["value_kind"] == "file"
    assert inputs["fasta"]["value_kind"] == "file"
    assert inputs["outdir"]["value_kind"] == "directory"
    assert inputs["outdir"]["is_internal"] is True
    assert inputs["genome"]["enum"] == ["GRCh37", "GRCh38"]

    spec = derive_form_spec(schema, "nextflow")
    fields = {field.id: field for field in spec.fields}
    assert fields["input"].kind == "file"
    assert fields["input"].required is True
    assert fields["outdir"].platform_managed is True
    assert fields["genome"].kind == "select"
    assert [option.value for option in fields["genome"].options or []] == [
        "GRCh37",
        "GRCh38",
    ]


def _wdl_schema(workflow_name: str) -> dict:
    return {
        "workflow_name": workflow_name,
        "inputs": [
            {"name": "outdir", "type": "String", "optional": False, "is_internal": True},
            {"name": "flaky_count", "type": "Int", "optional": True, "default": "2"},
            {"name": "fatal_enabled", "type": "Boolean", "optional": False},
            {"name": "sample_id", "type": "String", "optional": False},
        ],
    }
