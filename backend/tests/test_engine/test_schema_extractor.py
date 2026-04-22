from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.engine.schema_extractor import (
    SchemaExtractor,
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
