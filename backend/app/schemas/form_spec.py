from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

FormFieldKind = Literal[
    "file",
    "file_list",
    "directory",
    "table",
    "string",
    "int",
    "float",
    "bool",
    "select",
]

FormFieldSection = Literal["data", "params", "advanced"]

AllowRoot = Literal[
    "project_data",
    "shared_data",
    "reference",
    "database",
    "any_allowed_root",
]


class ColumnSpec(BaseModel):
    name: str
    required: bool = False
    kind: Literal["string", "int", "float", "bool", "path"] = "string"
    suffixes: list[str] | None = None


class OptionSpec(BaseModel):
    value: str
    label: str | None = None


class FormField(BaseModel):
    """Canonical server-side form field. Includes engine_key for the compiler."""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    label: str
    section: FormFieldSection
    kind: FormFieldKind
    required: bool = False
    default: Any | None = None
    help: str | None = None
    platform_managed: bool = False

    accept: list[str] | None = None
    allow_roots: list[AllowRoot] | None = None
    materialize_to_run: bool = False
    columns: list[ColumnSpec] | None = None
    options: list[OptionSpec] | None = None

    engine_key: str = Field(default="")


class FormSpec(BaseModel):
    """Full server-side form spec for a workflow."""

    fields: list[FormField] = Field(default_factory=list)


class FormFieldRead(BaseModel):
    """Frontend projection — omits server-only engine_key."""

    id: str
    label: str
    section: FormFieldSection
    kind: FormFieldKind
    required: bool
    default: Any | None = None
    help: str | None = None
    platform_managed: bool = False
    accept: list[str] | None = None
    allow_roots: list[AllowRoot] | None = None
    materialize_to_run: bool = False
    columns: list[ColumnSpec] | None = None
    options: list[OptionSpec] | None = None


class FormSpecRead(BaseModel):
    fields: list[FormFieldRead]


def to_read_projection(spec: FormSpec) -> FormSpecRead:
    """Strip server-only fields for the public form-spec endpoint."""
    return FormSpecRead(
        fields=[
            FormFieldRead.model_validate(field.model_dump(exclude={"engine_key"}))
            for field in spec.fields
        ]
    )
