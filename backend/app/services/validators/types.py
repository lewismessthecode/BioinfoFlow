"""Shared types and utilities for workflow validators."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


_REFERENCE_HINT_TOKENS = (
    "reference",
    "genome",
    "fasta",
    "fa",
    "fna",
    "bed",
    "gtf",
    "gff",
    "index",
    "known_sites",
    "dbsnp",
)

_INTERNAL_PARAM_NAMES = {"outdir", "output_dir", "publish_dir", "work_dir"}


@dataclass
class ValidationError:
    """Represents a validation error with location info."""

    line: int | None
    column: int | None
    message: str
    severity: str = "error"


@dataclass
class WorkflowParameter:
    """Represents a workflow input or output parameter."""

    name: str
    type: str
    optional: bool = False
    default: str | None = None
    description: str | None = None
    value_kind: str = "scalar"
    source_hint: str | None = None
    is_internal: bool = False


@dataclass
class WorkflowTask:
    """Represents a task/process in the workflow."""

    name: str
    inputs: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    container: str | None = None


@dataclass
class WorkflowDependency:
    """Represents a dependency between tasks."""

    source: str
    target: str


@dataclass
class ValidationResult:
    """Complete validation result with parsed schema."""

    valid: bool
    errors: list[ValidationError] = field(default_factory=list)
    warnings: list[ValidationError] = field(default_factory=list)
    workflow_name: str | None = None
    version: str | None = None
    description: str | None = None
    inputs: list[WorkflowParameter] = field(default_factory=list)
    outputs: list[WorkflowParameter] = field(default_factory=list)
    tasks: list[WorkflowTask] = field(default_factory=list)
    dependencies: list[WorkflowDependency] = field(default_factory=list)

    def to_schema_json(self) -> dict[str, Any]:
        """Convert to JSON format for database storage."""
        return {
            "workflow_name": self.workflow_name,
            "version": self.version,
            "description": self.description,
            "inputs": [
                {
                    "name": p.name,
                    "type": p.type,
                    "optional": p.optional,
                    "default": p.default,
                    "description": p.description,
                    "value_kind": p.value_kind,
                    "source_hint": p.source_hint,
                    "is_internal": p.is_internal,
                }
                for p in self.inputs
            ],
            "outputs": [
                {
                    "name": p.name,
                    "type": p.type,
                    "optional": p.optional,
                    "default": p.default,
                    "description": p.description,
                    "value_kind": p.value_kind,
                    "source_hint": p.source_hint,
                    "is_internal": p.is_internal,
                }
                for p in self.outputs
            ],
            "tasks": [
                {
                    "name": t.name,
                    "inputs": t.inputs,
                    "outputs": t.outputs,
                    "container": t.container,
                }
                for t in self.tasks
            ],
            "dependencies": [
                {"source": d.source, "target": d.target} for d in self.dependencies
            ],
        }


def find_matching_brace(content: str, start: int) -> int:
    """Find the matching closing brace for an opening brace."""
    if start >= len(content) or content[start] != "{":
        return -1
    depth = 0
    i = start
    while i < len(content):
        if content[i] == "{":
            depth += 1
        elif content[i] == "}":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def find_matching_paren(content: str, start: int) -> int:
    """Find the matching closing parenthesis for an opening paren."""
    if start >= len(content) or content[start] != "(":
        return -1
    depth = 0
    i = start
    while i < len(content):
        if content[i] == "(":
            depth += 1
        elif content[i] == ")":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def infer_value_kind(type_name: str | None, *, name: str = "", default: str | None = None) -> str:
    lowered_type = str(type_name or "").lower()
    lowered_name = str(name or "").lower()
    lowered_default = _normalized_default_text(default)
    combined = f"{lowered_type} {lowered_name} {lowered_default}"

    if "directory" in lowered_type or lowered_name.endswith("_dir"):
        return "directory"
    if "array[file" in lowered_type or "list[file" in lowered_type:
        return "file_list"
    if any(token in lowered_type for token in ("file", "path")):
        return "file"
    if _contains_name_hint(lowered_name, _REFERENCE_HINT_TOKENS) and (
        not lowered_default or _default_looks_pathlike(lowered_default)
    ):
        return "file"
    if any(marker in lowered_default for marker in ("*.fastq", "*.fq", "*.bam", "*.vcf", "*.fa")):
        return "file_list"
    if any(token in combined for token in ("reads", "fastq", "bam", "vcf", "cram", "samplesheet", "manifest", "sequence_list")):
        if lowered_default and not _default_looks_pathlike(lowered_default):
            return "scalar"
        return "file_list" if "reads" in combined else "file"
    return "scalar"


def _contains_name_hint(name: str, tokens: tuple[str, ...]) -> bool:
    name_tokens = {
        token for token in re.split(r"[^a-z0-9]+", name) if token
    }
    return any(token in name_tokens for token in tokens)


def _normalized_default_text(default: str | None) -> str:
    text = str(default or "").strip().lower()
    if "?:" in text:
        text = text.split("?:", 1)[1].strip()
    return text.strip("'\"")


def _default_looks_pathlike(default: str) -> bool:
    if default in {"", "null", "none", "nil"}:
        return True
    if re.match(r"^[a-z][a-z0-9+.-]*://", default):
        return True
    if default.startswith(("./", "../", "~")):
        return True
    if any(marker in default for marker in ("/", "\\", "*", "?", "[", "]", "{", "}")):
        return True
    return bool(
        re.search(
            r"\.(fa|fasta|fna|fastq|fq|bam|cram|vcf|bcf|csv|tsv|txt|json|yaml|yml|bed|gtf|gff|gz|zip)$",
            default,
        )
    )


def infer_source_hint(
    *,
    name: str,
    description: str | None = None,
    value_kind: str = "scalar",
) -> str | None:
    if value_kind not in {"file", "file_list", "directory"}:
        return None
    combined = f"{name} {description or ''}".lower()
    if any(token in combined for token in _REFERENCE_HINT_TOKENS):
        return "reference"
    return "project"


def infer_is_internal(name: str) -> bool:
    return str(name or "").strip().lower() in _INTERNAL_PARAM_NAMES
