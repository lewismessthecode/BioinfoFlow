from __future__ import annotations

import json

from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.api.error_handler import handle_api_errors
from app.auth.session import AuthUser
from app.schemas.form_spec import to_read_projection
from app.schemas.workflow import WorkflowCreate, WorkflowRead, WorkflowUpdate
from app.services.workflow_form_spec import effective_workflow_form_spec
from app.services.workflow_service import WorkflowService
from app.services.workflow_validator import WorkflowValidator
from app.utils.dag_builder import build_dag_from_schema
from app.utils.authorization import can_select_container_registry
from app.utils.exceptions import PermissionDeniedError
from app.utils.logging import get_logger
from app.utils.responses import error_response, success_response

logger = get_logger(__name__)

router = APIRouter(prefix="/workflows", tags=["workflows"])

MAX_WORKFLOW_CONTENT_BYTES = 50 * 1024 * 1024  # 50 MB


def _serialize(workflow) -> dict:
    return WorkflowRead.model_validate(workflow, from_attributes=True).model_dump(
        mode="json", by_alias=True
    )


def _normalize_workflow_id(workflow_id: str) -> str | None:
    try:
        UUID(str(workflow_id))
    except ValueError:
        return None
    return workflow_id


@router.get("")
async def list_workflows(
    request: Request,
    limit: int = 20,
    cursor: str | None = None,
    search: str | None = None,
    source: str | None = None,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = WorkflowService(db)
    workflows, pagination = await service.list_workflows(
        limit=limit, cursor=cursor, search=search, source=source
    )
    data = [_serialize(workflow) for workflow in workflows]
    return success_response(data, request=request, pagination=pagination)


@router.post("/validate")
async def validate_workflow(
    payload: WorkflowCreate,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Validate workflow content and return parsed schema + DAG without persisting."""
    from app.models.workflow import WorkflowEngine as WE

    engine_raw = payload.engine
    if not engine_raw and payload.file_name:
        fn = payload.file_name.lower()
        if fn.endswith(".wdl"):
            engine_raw = WE.WDL
        elif fn.endswith(".nf"):
            engine_raw = WE.NEXTFLOW
    if not engine_raw:
        engine_raw = WE.NEXTFLOW

    engine_str = engine_raw.value if hasattr(engine_raw, "value") else str(engine_raw)

    if not payload.content:
        return error_response(
            code="VALIDATION_ERROR",
            message="Content is required for validation",
            status_code=400,
            request=request,
        )

    if len(payload.content.encode("utf-8")) > MAX_WORKFLOW_CONTENT_BYTES:
        return error_response(
            code="PAYLOAD_TOO_LARGE",
            message="Workflow content exceeds the 50 MB limit",
            status_code=413,
            request=request,
        )

    validator = WorkflowValidator()
    result = await validator.validate_and_extract(
        content=payload.content,
        engine=engine_str,
        file_name=payload.file_name,
    )

    response_data: dict = {
        "valid": result.valid,
        "errors": [
            {
                "line": e.line,
                "column": e.column,
                "message": e.message,
                "severity": e.severity,
            }
            for e in result.errors
        ],
        "warnings": [
            {
                "line": e.line,
                "column": e.column,
                "message": e.message,
                "severity": e.severity,
            }
            for e in result.warnings
        ],
        "schema": None,
        "dag": None,
    }

    if result.valid:
        schema_json = result.to_schema_json()
        response_data["schema"] = schema_json
        response_data["dag"] = build_dag_from_schema(schema_json)

    return success_response(response_data, request=request)


@router.post("")
@handle_api_errors(
    FileNotFoundError=("FILE_NOT_FOUND", 404),
    ValueError=("VALIDATION_ERROR", 400),
)
async def create_workflow(
    payload: WorkflowCreate,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if payload.container_registry_id and not can_select_container_registry(user.role):
        raise PermissionDeniedError(
            "Only workspace admins can select a configured registry"
        )
    if (
        payload.content
        and len(payload.content.encode("utf-8")) > MAX_WORKFLOW_CONTENT_BYTES
    ):
        return error_response(
            code="PAYLOAD_TOO_LARGE",
            message="Workflow content exceeds the 50 MB limit",
            status_code=413,
            request=request,
        )

    service = WorkflowService(db)
    workflow = await service.create_workflow(payload.model_dump(by_alias=True))
    return success_response(_serialize(workflow), request=request, status_code=201)


@router.post("/local-bundle")
@handle_api_errors(
    FileNotFoundError=("FILE_NOT_FOUND", 404),
    ValueError=("VALIDATION_ERROR", 400),
)
async def create_local_bundle_workflow(
    request: Request,
    name: str | None = Form(None),
    version: str | None = Form(None),
    engine: str | None = Form(None),
    description: str | None = Form(None),
    estimated_time: str | None = Form(None),
    container_registry_id: str | None = Form(None),
    entrypoint_relpath: str | None = Form(None),
    bundle_paths: str = Form(...),
    bundle_files: list[UploadFile] = File(...),
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if container_registry_id and not can_select_container_registry(user.role):
        raise PermissionDeniedError(
            "Only workspace admins can select a configured registry"
        )

    try:
        parsed_paths = json.loads(bundle_paths)
    except json.JSONDecodeError as exc:
        raise ValueError("bundle_paths must be a JSON string array") from exc

    if not isinstance(parsed_paths, list) or any(
        not isinstance(item, str) or not item.strip() for item in parsed_paths
    ):
        raise ValueError("bundle_paths must contain relative file paths")

    if len(parsed_paths) != len(bundle_files):
        raise ValueError("bundle_paths and bundle_files must have the same length")

    uploaded_files: list[dict[str, object]] = []
    total_bytes = 0
    for relpath, upload in zip(parsed_paths, bundle_files, strict=False):
        content = await upload.read()
        total_bytes += len(content)
        if total_bytes > MAX_WORKFLOW_CONTENT_BYTES:
            return error_response(
                code="PAYLOAD_TOO_LARGE",
                message="Workflow bundle exceeds the 50 MB limit",
                status_code=413,
                request=request,
            )
        uploaded_files.append({"relpath": relpath, "content": content})

    service = WorkflowService(db)
    workflow = await service.create_workflow(
        {
            "source": "local",
            "name": name,
            "version": version,
            "engine": engine,
            "description": description,
            "estimated_time": estimated_time,
            "container_registry_id": container_registry_id,
            "entrypoint_relpath": entrypoint_relpath,
            "bundle_files": uploaded_files,
        }
    )
    return success_response(_serialize(workflow), request=request, status_code=201)


@router.get("/{workflow_id}")
async def get_workflow(
    workflow_id: str,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    normalized_workflow_id = _normalize_workflow_id(workflow_id)
    if normalized_workflow_id is None:
        return error_response(
            code="NOT_FOUND",
            message="Workflow not found",
            status_code=404,
            request=request,
        )
    service = WorkflowService(db)
    workflow = await service.get_workflow(normalized_workflow_id)
    if not workflow:
        return error_response(
            code="NOT_FOUND",
            message="Workflow not found",
            status_code=404,
            request=request,
        )
    return success_response(_serialize(workflow), request=request)


@router.patch("/{workflow_id}")
async def update_workflow(
    workflow_id: str,
    payload: WorkflowUpdate,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    normalized_workflow_id = _normalize_workflow_id(workflow_id)
    if normalized_workflow_id is None:
        return error_response(
            code="NOT_FOUND",
            message="Workflow not found",
            status_code=404,
            request=request,
        )
    service = WorkflowService(db)
    workflow = await service.get_workflow(normalized_workflow_id)
    if not workflow:
        return error_response(
            code="NOT_FOUND",
            message="Workflow not found",
            status_code=404,
            request=request,
        )
    updated = await service.update_workflow(
        workflow, payload.model_dump(exclude_unset=True, by_alias=True)
    )
    return success_response(_serialize(updated), request=request)


@router.delete("/{workflow_id}")
async def delete_workflow(
    workflow_id: str,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    normalized_workflow_id = _normalize_workflow_id(workflow_id)
    if normalized_workflow_id is None:
        return error_response(
            code="NOT_FOUND",
            message="Workflow not found",
            status_code=404,
            request=request,
        )
    service = WorkflowService(db)
    workflow = await service.get_workflow(normalized_workflow_id)
    if not workflow:
        return error_response(
            code="NOT_FOUND",
            message="Workflow not found",
            status_code=404,
            request=request,
        )
    await service.delete_workflow(workflow)
    return success_response(None, request=request, status_code=204)


@router.get("/{workflow_id}/dag")
async def get_workflow_dag(
    workflow_id: str,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get workflow DAG data for visualization."""
    normalized_workflow_id = _normalize_workflow_id(workflow_id)
    if normalized_workflow_id is None:
        return error_response(
            code="NOT_FOUND",
            message="Workflow not found",
            status_code=404,
            request=request,
        )
    service = WorkflowService(db)
    workflow = await service.get_workflow(normalized_workflow_id)

    if not workflow:
        return error_response(
            code="NOT_FOUND",
            message="Workflow not found",
            status_code=404,
            request=request,
        )

    if not workflow.schema_json:
        return success_response({"nodes": [], "edges": []}, request=request)

    dag_data = build_dag_from_schema(workflow.schema_json)
    return success_response(dag_data, request=request)


@router.get("/{workflow_id}/form-spec")
async def get_workflow_form_spec(
    workflow_id: str,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the deterministic FormSpec used to render the run wizard.

    Lazily backfills `Workflow.form_spec` if missing, so legacy workflows
    that pre-date the column work without a one-shot migration script.
    """
    normalized_workflow_id = _normalize_workflow_id(workflow_id)
    if normalized_workflow_id is None:
        return error_response(
            code="NOT_FOUND",
            message="Workflow not found",
            status_code=404,
            request=request,
        )
    service = WorkflowService(db)
    workflow = await service.get_workflow(normalized_workflow_id)
    if not workflow:
        return error_response(
            code="NOT_FOUND",
            message="Workflow not found",
            status_code=404,
            request=request,
        )

    spec = effective_workflow_form_spec(workflow)
    spec_dict = spec.model_dump(mode="json")
    if spec_dict != workflow.form_spec:
        await service.update_workflow(workflow, {"form_spec": spec_dict})
    return success_response(
        to_read_projection(spec).model_dump(mode="json"),
        request=request,
    )


@router.get("/{workflow_id}/source")
async def get_workflow_source(
    workflow_id: str,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get workflow source code content."""
    normalized_workflow_id = _normalize_workflow_id(workflow_id)
    if normalized_workflow_id is None:
        return error_response(
            code="NOT_FOUND",
            message="Workflow not found",
            status_code=404,
            request=request,
        )
    service = WorkflowService(db)
    workflow = await service.get_workflow(normalized_workflow_id)

    if not workflow:
        return error_response(
            code="NOT_FOUND",
            message="Workflow not found",
            status_code=404,
            request=request,
        )

    if workflow.source != "local":
        return error_response(
            code="NOT_AVAILABLE",
            message="Source code not available for non-local workflows",
            status_code=400,
            request=request,
        )

    try:
        source_path = service.resolve_source_path(workflow)
        if not source_path.exists():
            return error_response(
                code="FILE_NOT_FOUND",
                message="Workflow source file not found",
                status_code=404,
                request=request,
            )
        content = source_path.read_text()
        return success_response({"content": content}, request=request)
    except PermissionError:
        return error_response(
            code="FORBIDDEN",
            message="Workflow source escapes bundle",
            status_code=403,
            request=request,
        )
    except Exception as exc:
        logger.exception(
            "workflow.source.read_error", path=str(source_path), error=str(exc)
        )
        return error_response(
            code="READ_ERROR",
            message="Failed to read source file",
            status_code=500,
            request=request,
        )
