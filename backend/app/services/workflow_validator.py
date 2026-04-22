"""Workflow validation and schema extraction service.

Delegates to language-specific validators for WDL and Nextflow.
Shared dataclasses live in ``validators.types`` and are re-exported here
so that existing callers (``from app.services.workflow_validator import ...``)
continue to work unchanged.
"""

from __future__ import annotations

from typing import Any

from app.engine.schema_extractor import SchemaExtractor
from app.services.validators.nextflow_validator import NextflowValidator
from app.services.validators.types import (
    ValidationError,
    ValidationResult,
    WorkflowDependency,
    WorkflowParameter,
    WorkflowTask,
)
from app.services.validators.wdl_validator import WdlValidator

# Re-export dataclasses for backward compatibility
__all__ = [
    "ValidationError",
    "ValidationResult",
    "WorkflowDependency",
    "WorkflowParameter",
    "WorkflowTask",
    "WorkflowValidator",
]


class WorkflowValidator:
    """Validates WDL and Nextflow workflow files.

    Delegates to language-specific validators and provides schema merging.
    """

    def __init__(self) -> None:
        self._wdl = WdlValidator()
        self._nextflow = NextflowValidator()

    # Delegate private methods for backward compatibility with tests
    def _validate_wdl(
        self, content: str, file_name: str | None
    ) -> ValidationResult:
        return self._wdl.validate(content, file_name)

    def _validate_wdl_basic(
        self, content: str, file_name: str | None
    ) -> ValidationResult:
        return self._wdl._validate_basic(content, file_name)

    def _validate_nextflow(
        self, content: str, file_name: str | None
    ) -> ValidationResult:
        return self._nextflow.validate(content, file_name)

    def validate(
        self, content: str, engine: str, file_name: str | None = None
    ) -> ValidationResult:
        """Validate workflow content and extract schema.

        Args:
            content: The workflow file content
            engine: Either "wdl" or "nextflow"
            file_name: Optional original file name

        Returns:
            ValidationResult with parsed schema or errors
        """
        if engine == "wdl":
            return self._wdl.validate(content, file_name)
        elif engine == "nextflow":
            return self._nextflow.validate(content, file_name)
        return ValidationResult(
            valid=False,
            errors=[ValidationError(None, None, f"Unknown engine: {engine}")],
        )

    async def validate_and_extract(
        self,
        content: str,
        engine: str,
        file_name: str | None = None,
        *,
        source: str | None = None,
    ) -> ValidationResult:
        syntax_result = self.validate(content, engine, file_name)
        if not syntax_result.valid:
            return syntax_result

        schema = await SchemaExtractor().extract(
            engine,
            source,
            content=content,
            file_name=file_name,
        )
        return self._merge_schema(syntax_result, schema)

    def _merge_schema(
        self,
        result: ValidationResult,
        schema: dict[str, Any] | None,
    ) -> ValidationResult:
        if not isinstance(schema, dict):
            return result

        result.workflow_name = schema.get("workflow_name") or result.workflow_name
        result.version = schema.get("version") or result.version
        result.description = schema.get("description") or result.description
        if schema.get("inputs"):
            result.inputs = [
                WorkflowParameter(
                    name=item.get("name", ""),
                    type=item.get("type", "Any"),
                    optional=bool(item.get("optional", False)),
                    default=item.get("default"),
                    description=item.get("description"),
                    value_kind=item.get("value_kind", "scalar"),
                    source_hint=item.get("source_hint"),
                    is_internal=bool(item.get("is_internal", False)),
                )
                for item in schema.get("inputs", [])
                if item.get("name")
            ]
        if schema.get("outputs"):
            result.outputs = [
                WorkflowParameter(
                    name=item.get("name", ""),
                    type=item.get("type", "Any"),
                    optional=bool(item.get("optional", False)),
                    default=item.get("default"),
                    description=item.get("description"),
                    value_kind=item.get("value_kind", "scalar"),
                    source_hint=item.get("source_hint"),
                    is_internal=bool(item.get("is_internal", False)),
                )
                for item in schema.get("outputs", [])
                if item.get("name")
            ]
        if schema.get("tasks"):
            result.tasks = [
                WorkflowTask(
                    name=item.get("name", ""),
                    inputs=list(item.get("inputs", [])),
                    outputs=list(item.get("outputs", [])),
                    container=item.get("container"),
                )
                for item in schema.get("tasks", [])
                if item.get("name")
            ]
        if schema.get("dependencies"):
            result.dependencies = [
                WorkflowDependency(
                    source=item.get("source", ""),
                    target=item.get("target", ""),
                )
                for item in schema.get("dependencies", [])
                if item.get("source") and item.get("target")
            ]
        return result
