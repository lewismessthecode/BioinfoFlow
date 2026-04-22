from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from app.engine.schema_extractor import derive_form_spec
from app.path_layout import path_relative_to, safe_join, workflow_bundle_home
from app.schemas.form_spec import FormField, FormSpec

_MISSING = object()
_BUNDLE_DEFAULT_FILES = {
    "nextflow": ("happy.params.json", "happy.inputs.json"),
    "wdl": ("happy.inputs.json", "happy.params.json"),
}
_BUNDLE_FORM_SPEC_OVERRIDE_FILES = (
    "form-spec.overrides.json",
    "form_spec.overrides.json",
)


def effective_workflow_form_spec(workflow) -> FormSpec:
    raw = workflow.form_spec
    if isinstance(raw, dict) and "fields" in raw:
        spec = FormSpec.model_validate(raw)
    else:
        engine = (
            workflow.engine.value
            if hasattr(workflow.engine, "value")
            else str(workflow.engine)
        )
        spec = derive_form_spec(workflow.schema_json, engine)

    return reconcile_workflow_form_spec(
        spec,
        workflow_id=str(workflow.id),
        source=str(getattr(workflow.source, "value", workflow.source)),
        engine=(
            workflow.engine.value
            if hasattr(workflow.engine, "value")
            else str(workflow.engine)
        ),
    )


def reconcile_workflow_form_spec(
    spec: FormSpec,
    *,
    workflow_id: str,
    source: str,
    engine: str,
    bundle_root: Path | None = None,
) -> FormSpec:
    if source != "local":
        return spec

    root = (bundle_root or workflow_bundle_home(workflow_id)).resolve()
    defaults = _load_bundle_defaults(root, engine=engine)
    field_overrides = _load_bundle_field_overrides(root)
    fields: list[FormField] = []
    changed = False

    for field in spec.fields:
        payload = field.model_dump(mode="python")

        if not field.platform_managed:
            overlay = _lookup_bundle_default(defaults, field)
            if overlay is not _MISSING:
                payload["default"] = overlay

        override = _lookup_bundle_field_override(field_overrides, field)
        if isinstance(override, dict):
            for key, value in override.items():
                if key in {"id", "engine_key"}:
                    continue
                if key not in FormField.model_fields:
                    continue
                payload[key] = deepcopy(value)

        if payload.get("materialize_to_run") and field.kind in (
            "file",
            "directory",
            "file_list",
        ):
            # Runtime documents such as manifests should be chosen or uploaded
            # per run, not silently prefilled from bundle fixtures.
            payload["default"] = None

        payload["default"] = _normalize_default(
            payload.get("default"),
            field=field,
            workflow_id=workflow_id,
            bundle_root=root,
        )
        normalized = FormField.model_validate(payload)
        if normalized != field:
            changed = True
        fields.append(normalized)

    return FormSpec(fields=fields) if changed else spec


def _load_bundle_defaults(bundle_root: Path, *, engine: str) -> dict[str, Any]:
    defaults: dict[str, Any] = {}
    for file_name in _BUNDLE_DEFAULT_FILES.get(
        str(engine).lower(), ("happy.inputs.json", "happy.params.json")
    ):
        path = bundle_root / "inputs" / file_name
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            defaults.update(payload)
    return defaults


def _lookup_bundle_default(defaults: dict[str, Any], field: FormField) -> Any:
    keys = [field.engine_key, field.id]
    seen: set[str] = set()
    for key in keys:
        if not key or key in seen:
            continue
        seen.add(key)
        if key in defaults:
            return deepcopy(defaults[key])
    return _MISSING


def _load_bundle_field_overrides(bundle_root: Path) -> dict[str, Any]:
    for file_name in _BUNDLE_FORM_SPEC_OVERRIDE_FILES:
        path = bundle_root / "inputs" / file_name
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        if isinstance(payload.get("fields"), dict):
            return payload["fields"]
        return payload
    return {}


def _lookup_bundle_field_override(
    overrides: dict[str, Any], field: FormField
) -> dict[str, Any] | None:
    keys = [field.engine_key, field.id]
    seen: set[str] = set()
    for key in keys:
        if not key or key in seen:
            continue
        seen.add(key)
        candidate = overrides.get(key)
        if isinstance(candidate, dict):
            return deepcopy(candidate)
    return None


def _normalize_default(
    value: Any,
    *,
    field: FormField,
    workflow_id: str,
    bundle_root: Path,
) -> Any:
    if value is None:
        return None
    if field.kind in ("file", "directory"):
        return _normalize_bundle_path_value(
            value,
            workflow_id=workflow_id,
            bundle_root=bundle_root,
        )
    if field.kind == "file_list" and isinstance(value, list):
        return [
            _normalize_bundle_path_value(
                item,
                workflow_id=workflow_id,
                bundle_root=bundle_root,
            )
            for item in value
        ]
    return value


def _normalize_bundle_path_value(
    value: Any,
    *,
    workflow_id: str,
    bundle_root: Path,
) -> Any:
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text or text.startswith("asset://"):
        return value

    if Path(text).is_absolute():
        candidate = Path(text).expanduser().resolve(strict=False)
        if candidate.exists() and candidate.is_relative_to(bundle_root):
            return (
                f"asset://workflow/{workflow_id}/"
                f"{path_relative_to(bundle_root, candidate)}"
            )
        return value

    resolved = _resolve_bundle_relative_path(bundle_root, text)
    if resolved is None:
        return value
    return f"asset://workflow/{workflow_id}/{resolved}"


def _resolve_bundle_relative_path(bundle_root: Path, raw: str) -> str | None:
    parts = list(Path(raw).parts)
    if not parts:
        return None

    for index in range(len(parts)):
        candidate_rel = str(Path(*parts[index:]))
        try:
            candidate = safe_join(
                bundle_root,
                candidate_rel,
                escape_message="bundle default path escapes workflow bundle",
            )
        except PermissionError:
            continue
        if candidate.exists():
            return path_relative_to(bundle_root, candidate)
    return None
