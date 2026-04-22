from __future__ import annotations

from app.engine.registry import get_adapter
from app.schemas.form_spec import FormField, FormSpec


class SchemaExtractor:
    async def extract(
        self,
        engine: str,
        source: str | None,
        **kwargs,
    ) -> dict:
        adapter = get_adapter(engine)
        schema = await adapter.extract_schema(source, **kwargs)
        if _has_schema_content(schema):
            return schema

        content = kwargs.get("content")
        if isinstance(content, str) and content.strip():
            from app.services.workflow_validator import WorkflowValidator

            validator = WorkflowValidator()
            result = validator.validate(
                content,
                engine,
                file_name=kwargs.get("file_name"),
            )
            if result.valid:
                return result.to_schema_json()

        return {
            "tasks": [],
            "dependencies": [],
            "inputs": [],
            "outputs": [],
        }


def _has_schema_content(schema: dict | None) -> bool:
    if not isinstance(schema, dict):
        return False
    return any(
        schema.get(key) for key in ("tasks", "dependencies", "inputs", "outputs")
    )


# ---------------------------------------------------------------------------
# Form spec derivation: maps each WorkflowParameter to one FormField with
# explicit kind, section, allow_roots and engine_key. No samplesheet/column
# auto-detection — ambiguous inputs become free-text strings rather than
# guessed structures. The frontend renders the spec verbatim.
# ---------------------------------------------------------------------------

_DEFAULT_FILE_ROOTS = ["project_data", "shared_data", "reference"]
_SOURCE_HINT_TO_ROOTS = {
    "project": ["project_data"],
    "deliveries": ["shared_data"],
    "reference": ["reference"],
    "mixed": _DEFAULT_FILE_ROOTS,
}


def derive_form_spec(schema_json: dict | None, engine: str) -> FormSpec:
    """Build a deterministic FormSpec from extracted workflow schema."""
    inputs = (schema_json or {}).get("inputs") or []
    is_wdl = (engine or "").lower() == "wdl"
    workflow_name = str((schema_json or {}).get("workflow_name") or "") if is_wdl else ""

    fields: list[FormField] = []
    for inp in inputs:
        name = str(inp.get("name") or "").strip()
        if not name:
            continue

        value_kind = str(inp.get("value_kind") or "scalar").lower()
        type_name = str(inp.get("type") or "").lower()
        is_internal = bool(inp.get("is_internal"))
        optional = bool(inp.get("optional", False))
        source_hint = inp.get("source_hint")

        kind = _resolve_kind(value_kind, type_name)
        if is_internal:
            section = "advanced"
        elif kind in ("file", "file_list", "directory", "table"):
            section = "data"
        else:
            section = "params"

        field = FormField(
            id=name,
            label=_humanize(name),
            section=section,  # type: ignore[arg-type]
            kind=kind,
            required=(not optional) and (not is_internal),
            default=_normalize_default(inp.get("default"), kind),
            help=inp.get("description") or None,
            platform_managed=is_internal,
            engine_key=_qualify_engine_key(name, workflow_name, is_wdl),
        )

        if kind in ("file", "file_list", "directory"):
            field.allow_roots = _SOURCE_HINT_TO_ROOTS.get(
                str(source_hint or ""), list(_DEFAULT_FILE_ROOTS)
            )  # type: ignore[assignment]

        fields.append(field)

    return FormSpec(fields=fields)


def _resolve_kind(value_kind: str, type_name: str) -> str:
    """Map (value_kind, type) -> FormFieldKind."""
    if value_kind == "file":
        return "file"
    if value_kind == "file_list":
        return "file_list"
    if value_kind == "directory":
        return "directory"
    # value_kind == "scalar" (or unknown): infer primitive from type
    if "bool" in type_name:
        return "bool"
    if "int" in type_name and "boolean" not in type_name:
        return "int"
    if any(token in type_name for token in ("float", "double", "number")):
        return "float"
    return "string"


def _qualify_engine_key(name: str, workflow_name: str, is_wdl: bool) -> str:
    if not is_wdl or not workflow_name or "." in name:
        return name
    return f"{workflow_name}.{name}"


def _humanize(name: str) -> str:
    cleaned = name.replace("_", " ").replace("-", " ").strip()
    if not cleaned:
        return name
    return cleaned[0].upper() + cleaned[1:]


def _normalize_default(default: object, kind: str) -> object:
    if default is None:
        return None
    text = str(default)
    if "?:" in text:
        text = text.split("?:")[1].strip().strip("'\"")
    if text == "":
        return None
    if kind == "bool":
        lowered = text.lower()
        if lowered in ("true", "1", "yes"):
            return True
        if lowered in ("false", "0", "no"):
            return False
        return None
    if kind == "int":
        try:
            return int(text)
        except (TypeError, ValueError):
            return None
    if kind == "float":
        try:
            return float(text)
        except (TypeError, ValueError):
            return None
    return text
