from __future__ import annotations

import json
from typing import Any

from app.engine.registry import get_adapter
from app.schemas.form_spec import FormField, FormSpec, OptionSpec
from app.services.run_input_policy import is_managed_run_directory_name


class SchemaExtractor:
    async def extract(
        self,
        engine: str,
        source: str | None,
        **kwargs,
    ) -> dict:
        adapter = get_adapter(engine)
        schema = await adapter.extract_schema(source, **kwargs)
        schema = normalize_extracted_schema(schema, engine=engine)
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


def normalize_extracted_schema(schema: dict | None, *, engine: str) -> dict | None:
    """Normalize supported engine-native schema shapes to the internal contract."""
    if not isinstance(schema, dict):
        return schema
    if (engine or "").lower() != "nextflow":
        return schema
    if schema.get("inputs"):
        return schema

    inputs = _inputs_from_json_schema(schema)
    if not inputs:
        return schema

    normalized = dict(schema)
    normalized["inputs"] = inputs
    normalized.setdefault("tasks", [])
    normalized.setdefault("dependencies", [])
    normalized.setdefault("outputs", [])
    return normalized


# ---------------------------------------------------------------------------
# Form spec derivation: maps each WorkflowParameter to one FormField with
# explicit kind, section, allow_roots and engine_key. No samplesheet/column
# auto-detection — ambiguous inputs become free-text strings rather than
# guessed structures. The frontend renders the spec verbatim.
# ---------------------------------------------------------------------------

_DEFAULT_FILE_ROOTS = ["shared_data", "reference", "database", "project_data"]
_VALID_ALLOW_ROOTS = {
    "project_data",
    "shared_data",
    "reference",
    "database",
    "any_allowed_root",
}
_SOURCE_HINT_TO_ROOTS = {
    "project": _DEFAULT_FILE_ROOTS,
    "deliveries": ["shared_data", "reference", "database", "project_data"],
    "reference": ["reference", "shared_data", "database", "project_data"],
    "mixed": _DEFAULT_FILE_ROOTS,
}


def derive_form_spec(schema_json: dict | None, engine: str) -> FormSpec:
    """Build a deterministic FormSpec from extracted workflow schema."""
    schema_json = normalize_extracted_schema(schema_json, engine=engine) or {}
    inputs = schema_json.get("inputs") or []
    is_wdl = (engine or "").lower() == "wdl"
    workflow_name = str(schema_json.get("workflow_name") or "") if is_wdl else ""

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

        options = _enum_options(inp)
        kind = "select" if options else _resolve_kind(value_kind, type_name)
        declared_section = str(inp.get("section") or "").lower()
        if declared_section in {"data", "params", "advanced"}:
            section = declared_section
        elif is_internal:
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
            options=options,
            engine_key=_qualify_engine_key(name, workflow_name, is_wdl),
        )

        if kind in ("file", "file_list", "directory"):
            field.allow_roots = _resolve_allow_roots(inp, source_hint)  # type: ignore[assignment]

        fields.append(field)

    return FormSpec(fields=fields)


def _inputs_from_json_schema(schema: dict) -> list[dict[str, Any]]:
    if not isinstance(schema.get("$defs"), dict) and not isinstance(
        schema.get("definitions"), dict
    ):
        return []

    inputs: list[dict[str, Any]] = []
    seen: set[str] = set()
    root_required = _required_names(schema)
    for section in _iter_json_schema_sections(schema):
        properties = section.get("properties")
        if not isinstance(properties, dict):
            continue
        required = root_required | _required_names(section)
        section_title = _optional_text(section.get("title"))
        for raw_name, raw_prop in properties.items():
            name = str(raw_name).strip()
            if not name or name in seen or not isinstance(raw_prop, dict):
                continue
            if bool(raw_prop.get("hidden") or raw_prop.get("ui:hidden")):
                continue
            seen.add(name)
            inputs.append(
                _input_from_json_schema_property(
                    name,
                    raw_prop,
                    required=required,
                    section_title=section_title,
                )
            )
    return inputs


def _iter_json_schema_sections(schema: dict) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    refs = schema.get("allOf")
    if isinstance(refs, list):
        for item in refs:
            if not isinstance(item, dict):
                continue
            resolved = _resolve_json_schema_ref(schema, item.get("$ref"))
            if isinstance(resolved, dict):
                sections.append(resolved)
            elif isinstance(item.get("properties"), dict):
                sections.append(item)
    if isinstance(schema.get("properties"), dict):
        sections.append(schema)
    return sections


def _resolve_json_schema_ref(schema: dict, ref: object) -> dict[str, Any] | None:
    if not isinstance(ref, str) or not ref.startswith("#/"):
        return None
    current: Any = schema
    for part in ref.removeprefix("#/").split("/"):
        key = part.replace("~1", "/").replace("~0", "~")
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current if isinstance(current, dict) else None


def _required_names(section: dict) -> set[str]:
    required = section.get("required")
    if not isinstance(required, list):
        return set()
    return {str(item) for item in required if str(item).strip()}


def _input_from_json_schema_property(
    name: str,
    prop: dict[str, Any],
    *,
    required: set[str],
    section_title: str | None,
) -> dict[str, Any]:
    type_name, nullable = _json_schema_type(prop)
    value_kind = _json_schema_value_kind(type_name, prop)
    payload: dict[str, Any] = {
        "name": name,
        "type": type_name,
        "value_kind": value_kind,
        "optional": (name not in required) or nullable,
    }

    description = _optional_text(prop.get("description") or prop.get("help_text"))
    if description:
        payload["description"] = description
    if "default" in prop:
        payload["default"] = prop.get("default")
    enum_values = _json_schema_enum(prop)
    if enum_values:
        payload["enum"] = enum_values
    if section_title:
        payload["section_title"] = section_title
    if is_managed_run_directory_name(name):
        payload["is_internal"] = True
        payload["optional"] = True
    if value_kind in {"file", "file_list", "directory"}:
        payload["source_hint"] = _path_source_hint(name, section_title)
    return payload


def _json_schema_type(prop: dict[str, Any]) -> tuple[str, bool]:
    raw = prop.get("type")
    nullable = False
    if isinstance(raw, list):
        nullable = "null" in raw
        non_null = [str(item) for item in raw if item != "null"]
        raw = non_null[0] if non_null else "string"
    text = str(raw or "string")
    if text == "array":
        items = prop.get("items")
        if isinstance(items, dict):
            item_type, _ = _json_schema_type(items)
            return f"array<{item_type}>", nullable
    return text, nullable


def _json_schema_value_kind(type_name: str, prop: dict[str, Any]) -> str:
    fmt = str(prop.get("format") or "").lower()
    if fmt == "directory-path":
        return "directory"
    if fmt in {"file-path", "path"}:
        return "file"
    if type_name.startswith("array<"):
        items = prop.get("items")
        if isinstance(items, dict):
            item_fmt = str(items.get("format") or "").lower()
            if item_fmt in {"file-path", "path"}:
                return "file_list"
        return "scalar"
    return "scalar"


def _json_schema_enum(prop: dict[str, Any]) -> list[str]:
    raw = prop.get("enum")
    if not isinstance(raw, list):
        return []
    values: list[str] = []
    seen: set[str] = set()
    for item in raw:
        if item is None:
            continue
        value = str(item)
        if value in seen:
            continue
        seen.add(value)
        values.append(value)
    return values


def _path_source_hint(name: str, section_title: str | None) -> str:
    lowered = f"{name} {section_title or ''}".lower()
    if any(token in lowered for token in ("reference", "genome", "fasta", "gtf", "gff")):
        return "reference"
    return "project"


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _enum_options(inp: dict) -> list[OptionSpec] | None:
    raw = inp.get("enum") or inp.get("options")
    if not isinstance(raw, list):
        return None
    options: list[OptionSpec] = []
    seen: set[str] = set()
    for item in raw:
        if isinstance(item, dict):
            value = str(item.get("value") or "").strip()
            label = _optional_text(item.get("label"))
        else:
            value = str(item).strip()
            label = None
        if not value or value in seen:
            continue
        seen.add(value)
        options.append(OptionSpec(value=value, label=label))
    return options or None


def _resolve_allow_roots(inp: dict, source_hint: object) -> list[str]:
    declared = inp.get("allow_roots")
    if isinstance(declared, list):
        roots: list[str] = []
        seen: set[str] = set()
        for item in declared:
            value = str(item).strip()
            if value not in _VALID_ALLOW_ROOTS or value in seen:
                continue
            seen.add(value)
            roots.append(value)
        if roots:
            return roots
    return list(_SOURCE_HINT_TO_ROOTS.get(str(source_hint or ""), _DEFAULT_FILE_ROOTS))


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
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        text = text[1:-1]
    if text == "":
        return None
    if text.lower() in {"null", "none", "nil"}:
        return None
    if kind == "file_list" and text == "[]":
        return []
    if kind == "file_list" and text.startswith("[") and text.endswith("]"):
        try:
            parsed = json.loads(text)
        except (TypeError, ValueError):
            parsed = None
        if isinstance(parsed, list):
            return parsed
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
