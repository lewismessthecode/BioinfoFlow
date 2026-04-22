from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.schema_extractor import (
    SchemaExtractor,
    derive_form_spec,
)
from app.models.workflow import WorkflowEngine, WorkflowSource
from app.path_layout import (
    safe_join,
    workflow_bundle_home,
    workflow_home,
    workflow_metadata_path,
)
from app.repositories.workflow_repo import WorkflowRepository
from app.services.workflow_form_spec import reconcile_workflow_form_spec
from app.services.workflow_validator import WorkflowValidator
from app.utils.repo_paths import normalize_repo_path


class WorkflowService:
    def __init__(self, session: AsyncSession):
        self.repo = WorkflowRepository(session)

    async def list_workflows(
        self,
        *,
        limit: int = 20,
        cursor: str | None = None,
        search: str | None = None,
        source: str | None = None,
    ):
        return await self.repo.list(
            limit=limit, cursor=cursor, search=search, source=source
        )

    async def get_workflow(self, workflow_id: str):
        return await self.repo.get(workflow_id)

    async def create_workflow(self, payload: dict[str, Any]):
        source = _normalize_enum(payload.get("source"), WorkflowSource)
        engine = _normalize_enum(payload.get("engine"), WorkflowEngine)
        name = payload.get("name")
        version = payload.get("version")
        description = payload.get("description")
        estimated_time = payload.get("estimated_time")
        weight = payload.get("weight", 1)

        source_ref = payload.get("source_ref")
        entrypoint_relpath = payload.get("entrypoint_relpath")
        file_name = payload.get("file_name")
        bundle_path = payload.get("bundle_path")
        bundle_files = payload.get("bundle_files")
        content = payload.get("content")

        schema_json: dict[str, Any] | None = None
        workflow_content: str | None = None
        bundle_kind: str | None = None
        workflow_id = str(payload.get("id") or uuid4())

        if source == WorkflowSource.NFCORE:
            if not name:
                raise ValueError("name is required for nf-core workflows")
            version = version or "latest"
            engine = engine or WorkflowEngine.NEXTFLOW
            source_ref = source_ref or f"nf-core/{name}"
            bundle_kind = "remote_ref"

        elif source == WorkflowSource.GITHUB:
            if not source_ref:
                raise ValueError("source_ref is required for github workflows")
            version = version or "main"
            engine = engine or WorkflowEngine.NEXTFLOW
            if not name:
                name = Path(str(source_ref)).name.replace(".git", "")
            bundle_kind = "remote_ref"

        elif source == WorkflowSource.LOCAL:
            version = version or "local"
            bundle_kind = "local_bundle"
            bundle_root = workflow_bundle_home(workflow_id)
            bundle_root.parent.mkdir(parents=True, exist_ok=True)

            src_bundle = normalize_repo_path(str(bundle_path)) if bundle_path else None
            src_entry = normalize_repo_path(str(source_ref)) if source_ref else None

            if src_bundle:
                src_bundle_path = Path(src_bundle)
                if not src_bundle_path.exists() or not src_bundle_path.is_dir():
                    raise FileNotFoundError("local workflow bundle path not found")
                if bundle_root.exists():
                    shutil.rmtree(bundle_root)
                shutil.copytree(src_bundle_path, bundle_root)
                if not entrypoint_relpath:
                    if file_name:
                        entrypoint_relpath = file_name
                    else:
                        entrypoint_relpath = _detect_bundle_entrypoint(bundle_root)
                if not entrypoint_relpath:
                    raise ValueError("entrypoint_relpath is required for local bundles")
            elif bundle_files:
                _write_uploaded_bundle(bundle_root, bundle_files)
                if not entrypoint_relpath:
                    if file_name:
                        entrypoint_relpath = file_name
                    else:
                        entrypoint_relpath = _detect_bundle_entrypoint(bundle_root)
                if not entrypoint_relpath:
                    raise ValueError("entrypoint_relpath is required for local bundles")
            elif content:
                if not file_name and not entrypoint_relpath:
                    raise ValueError(
                        "file_name or entrypoint_relpath is required for inline local workflows"
                    )
                entrypoint_relpath = entrypoint_relpath or file_name
                target_path = bundle_root / str(entrypoint_relpath)
                target_path.parent.mkdir(parents=True, exist_ok=True)
                target_path.write_text(content, encoding="utf-8")
            elif src_entry:
                source_path = Path(src_entry)
                if not source_path.exists() or not source_path.is_file():
                    raise FileNotFoundError("local workflow source not found")
                entrypoint_relpath = entrypoint_relpath or file_name or source_path.name
                target_path = bundle_root / str(entrypoint_relpath)
                target_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_path, target_path)
            else:
                raise ValueError(
                    "local workflows require bundle_path, content, or source_ref"
                )

            entrypoint_relpath = _normalize_entrypoint(entrypoint_relpath)
            target_path = bundle_root / entrypoint_relpath
            if not target_path.exists() or not target_path.is_file():
                raise FileNotFoundError("workflow entrypoint not found in bundle")

            if not engine:
                engine = _infer_engine_from_name(target_path.name)
            if not name:
                name = target_path.stem

            workflow_content = target_path.read_text(encoding="utf-8")
            validation = await WorkflowValidator().validate_and_extract(
                content=workflow_content,
                engine=engine.value,
                file_name=target_path.name,
                source=str(target_path),
            )
            if not validation.valid:
                shutil.rmtree(workflow_home(workflow_id), ignore_errors=True)
                error_messages = "; ".join(e.message for e in validation.errors)
                raise ValueError(f"Workflow validation failed: {error_messages}")

            schema_json = validation.to_schema_json()
            if validation.workflow_name and not payload.get("name"):
                name = validation.workflow_name
            if validation.description and not description:
                description = validation.description
            existing = await self.repo.get_by_unique(
                source=source.value, name=name, version=version
            )
            if existing:
                shutil.rmtree(workflow_home(workflow_id), ignore_errors=True)
                raise FileExistsError("workflow already exists")
            source_ref = "local"
            _write_workflow_metadata(
                workflow_id=workflow_id,
                payload={
                    "workflow_id": workflow_id,
                    "source": source.value,
                    "source_ref": source_ref,
                    "entrypoint_relpath": entrypoint_relpath,
                    "bundle_kind": bundle_kind,
                    "name": name,
                    "engine": engine.value,
                    "version": version,
                },
            )
        else:
            raise ValueError("workflow source is required")

        if source != WorkflowSource.LOCAL:
            if not name or not version or not engine:
                raise ValueError("workflow requires name, version, and engine")
            schema_json = await SchemaExtractor().extract(engine.value, str(source_ref))

        if not name or not version or not engine:
            raise ValueError("workflow requires name, version, and engine")

        if source != WorkflowSource.LOCAL:
            existing = await self.repo.get_by_unique(
                source=source.value, name=name, version=version
            )
            if existing:
                raise FileExistsError("workflow already exists")

        bundle_root = (
            workflow_bundle_home(workflow_id)
            if source == WorkflowSource.LOCAL
            else None
        )
        form_spec = reconcile_workflow_form_spec(
            derive_form_spec(schema_json, engine.value),
            workflow_id=workflow_id,
            source=source.value,
            engine=engine.value,
            bundle_root=bundle_root,
        ).model_dump(mode="json")

        return await self.repo.create(
            id=workflow_id,
            name=name,
            description=description,
            source=source.value,
            engine=engine.value,
            source_ref=source_ref,
            entrypoint_relpath=entrypoint_relpath,
            bundle_kind=bundle_kind,
            version=version,
            estimated_time=estimated_time,
            schema_json=schema_json,
            form_spec=form_spec,
            weight=weight,
        )

    async def update_workflow(self, workflow, payload: dict[str, Any]):
        if "schema_json" in payload and payload["schema_json"] is not None:
            engine_value = (
                workflow.engine.value
                if hasattr(workflow.engine, "value")
                else str(workflow.engine)
            )
            payload["form_spec"] = reconcile_workflow_form_spec(
                derive_form_spec(payload["schema_json"], engine_value),
                workflow_id=str(workflow.id),
                source=str(getattr(workflow.source, "value", workflow.source)),
                engine=engine_value,
            ).model_dump(mode="json")
        return await self.repo.update(workflow, **payload)

    async def delete_workflow(self, workflow):
        if (
            str(getattr(workflow.source, "value", workflow.source))
            == WorkflowSource.LOCAL.value
        ):
            shutil.rmtree(workflow_home(str(workflow.id)), ignore_errors=True)
        await self.repo.delete(workflow)

    def resolve_source_path(self, workflow) -> Path:
        if (
            str(getattr(workflow.source, "value", workflow.source))
            != WorkflowSource.LOCAL.value
        ):
            raise ValueError("source code is only available for local workflows")
        if not workflow.entrypoint_relpath:
            raise FileNotFoundError("workflow entrypoint not configured")
        return safe_join(
            workflow_bundle_home(str(workflow.id)),
            workflow.entrypoint_relpath,
            escape_message="workflow entrypoint escapes bundle",
        )


def _normalize_enum(value: Any, enum_cls):
    if value is None:
        return None
    if isinstance(value, enum_cls):
        return value
    raw = getattr(value, "value", value)
    return enum_cls(raw)


def _normalize_entrypoint(value: str | None) -> str:
    if not value or not str(value).strip():
        raise ValueError("entrypoint_relpath is required")
    normalized = str(Path(str(value).strip())).replace("\\", "/")
    if normalized.startswith("../") or normalized == "..":
        raise ValueError("entrypoint_relpath escapes bundle")
    return normalized


def _infer_engine_from_name(filename: str) -> WorkflowEngine:
    suffix = Path(filename).suffix.lower()
    if suffix == ".wdl":
        return WorkflowEngine.WDL
    if suffix == ".nf":
        return WorkflowEngine.NEXTFLOW
    raise ValueError("Unsupported file type. Only .wdl and .nf files are supported.")


def _detect_bundle_entrypoint(bundle_root: Path) -> str | None:
    for candidate in ("main.nf", "main.wdl", "workflow.nf", "workflow.wdl"):
        if (bundle_root / candidate).exists():
            return candidate
    matches = [
        path
        for path in bundle_root.rglob("*")
        if path.is_file() and path.suffix.lower() in {".nf", ".wdl"}
    ]
    matches.sort()
    if matches:
        return str(matches[0].relative_to(bundle_root))
    return None


def _write_uploaded_bundle(bundle_root: Path, bundle_files: list[dict[str, Any]]) -> None:
    if bundle_root.exists():
        shutil.rmtree(bundle_root)
    bundle_root.mkdir(parents=True, exist_ok=True)

    for item in bundle_files:
        relpath = _normalize_entrypoint(item.get("relpath"))
        content = item.get("content")
        if content is None:
            raise ValueError(f"missing bundle file content for {relpath}")
        if isinstance(content, str):
            payload = content.encode("utf-8")
        else:
            payload = bytes(content)
        target_path = bundle_root / relpath
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(payload)


def _write_workflow_metadata(*, workflow_id: str, payload: dict[str, Any]) -> None:
    path = workflow_metadata_path(workflow_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
