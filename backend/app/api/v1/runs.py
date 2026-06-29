from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.api.error_handler import handle_api_errors
from app.auth.session import AuthUser
from app.config import settings
from app.path_layout import project_run_uploads_root
from app.repositories.project_repo import ProjectRepository
from app.schemas.run import (
    RunCreate,
    RunRead,
    RunResumeRequest,
    RunRetryRequest,
    RunUploadRead,
)
from app.services.run_compiler import (
    CompileError,
    RunCompiler,
    WorkflowNotEnabledError,
)
from app.services.run_service import RunService
from app.utils.project_access import can_access_project
from app.utils.responses import error_response, success_response


router = APIRouter(prefix="/runs", tags=["runs"])


def _serialize(run) -> dict:
    return RunRead.model_validate(run, from_attributes=True).model_dump(
        mode="json", by_alias=True
    )


def _workflow_not_enabled_response(request: Request):
    return error_response(
        code="WORKFLOW_NOT_ENABLED_FOR_PROJECT",
        message="Workflow is not enabled for this project",
        status_code=403,
        request=request,
    )


@router.get("")
async def list_runs(
    request: Request,
    limit: int = 20,
    cursor: str | None = None,
    project_id: str | None = None,
    workflow_id: str | None = None,
    status: str | None = None,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = RunService(db)
    statuses = [s.strip() for s in status.split(",")] if status else None
    runs, pagination = await service.list_runs(
        limit=limit,
        cursor=cursor,
        project_id=project_id,
        workflow_id=workflow_id,
        status=statuses,
        user_id=user.id,
        workspace_id=user.workspace_id,
    )
    data = [_serialize(run) for run in runs]
    return success_response(data, request=request, pagination=pagination)


@router.post("")
@handle_api_errors
async def create_run(
    payload: RunCreate,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Submit a run via the canonical envelope.

    Accepts only ``{project_id, workflow_id, values, options}``. Values are
    keyed by the form-field ids in ``GET /workflows/{id}/form-spec``; paths,
    tables, and scalars are native JSON. The server resolves ``asset://``
    URIs to absolute paths during translation.
    """
    compiler = RunCompiler(db)
    try:
        run = await compiler.create_run(
            payload,
            user_id=user.id,
            workspace_id=user.workspace_id,
        )
    except FileNotFoundError as exc:
        return error_response(
            code="NOT_FOUND",
            message=str(exc),
            status_code=404,
            request=request,
        )
    except WorkflowNotEnabledError:
        return _workflow_not_enabled_response(request)
    except CompileError as exc:
        return error_response(
            code=exc.code,
            message=str(exc),
            status_code=422,
            request=request,
            details={"hint": exc.hint} if exc.hint else None,
        )

    return success_response(_serialize(run), request=request, status_code=202)


@router.post("/uploads")
@handle_api_errors(FileNotFoundError=("FILE_NOT_FOUND", 404))
async def upload_run_document(
    request: Request,
    project_id: str = Form(...),
    file: UploadFile = File(...),
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    payload = await file.read()
    if len(payload) > settings.max_upload_size_bytes:
        return error_response(
            code="PAYLOAD_TOO_LARGE",
            message=(
                "File exceeds maximum upload size of "
                f"{settings.max_upload_size_bytes} bytes"
            ),
            status_code=413,
            request=request,
        )

    project = await ProjectRepository(db).get(project_id)
    if project is None or not can_access_project(
        project,
        user_id=user.id,
        workspace_id=user.workspace_id,
    ):
        return error_response(
            code="NOT_FOUND",
            message="project not found",
            status_code=404,
            request=request,
        )

    filename = Path(file.filename or "upload").name
    upload_id = uuid4().hex
    target = project_run_uploads_root(project) / upload_id / filename
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)

    data = RunUploadRead(
        uri=f"asset://run_upload/{upload_id}/{filename}",
        path=f"{upload_id}/{filename}",
        filename=filename,
    )
    return success_response(data.model_dump(mode="json"), request=request, status_code=201)


@router.get("/{run_id}")
@handle_api_errors
async def get_run(
    run_id: str,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = RunService(db)
    run = await service.get_run(
        run_id,
        user_id=user.id,
        workspace_id=user.workspace_id,
    )
    if not run:
        return error_response(
            code="NOT_FOUND", message="Run not found", status_code=404, request=request
        )
    return success_response(_serialize(run), request=request)


@router.get("/{run_id}/logs")
@handle_api_errors
async def get_run_logs(
    run_id: str,
    request: Request,
    tail: int = 100,
    task: str | None = None,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = RunService(db)
    data = await service.get_logs(
        run_id,
        tail=tail,
        task=task,
        user_id=user.id,
        workspace_id=user.workspace_id,
    )
    return success_response(data, request=request)


@router.get("/{run_id}/dag")
@handle_api_errors
async def get_run_dag(
    run_id: str,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = RunService(db)
    data = await service.get_dag(
        run_id,
        user_id=user.id,
        workspace_id=user.workspace_id,
    )
    return success_response(data, request=request)


@router.post("/{run_id}/repair-dag")
@handle_api_errors
async def repair_run_dag(
    run_id: str,
    request: Request,
    dry_run: bool = False,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = RunService(db)
    data = await service.repair_run_dag(
        run_id,
        dry_run=dry_run,
        user_id=user.id,
        workspace_id=user.workspace_id,
    )
    return success_response(data, request=request)


@router.post("/repair-dags")
@handle_api_errors
async def repair_run_dags(
    request: Request,
    run_ids: str | None = None,
    project_id: str | None = None,
    dry_run: bool = False,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = RunService(db)
    parsed_run_ids = [item.strip() for item in run_ids.split(",")] if run_ids else None
    data = await service.repair_run_dags(
        run_ids=parsed_run_ids,
        project_id=project_id,
        dry_run=dry_run,
        user_id=user.id,
        workspace_id=user.workspace_id,
    )
    return success_response(data, request=request)


@router.post("/{run_id}/mock-dag-variants")
@handle_api_errors
async def create_mock_dag_variants(
    run_id: str,
    request: Request,
    variants: str | None = None,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = RunService(db)
    parsed_variants = (
        [item.strip() for item in variants.split(",")] if variants else None
    )
    data = await service.create_mock_dag_variants(
        run_id,
        variants=parsed_variants,
        user_id=user.id,
        workspace_id=user.workspace_id,
    )
    return success_response(data, request=request, status_code=201)


@router.get("/{run_id}/outputs")
@handle_api_errors
async def get_run_outputs(
    run_id: str,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = RunService(db)
    data = await service.list_outputs(
        run_id,
        user_id=user.id,
        workspace_id=user.workspace_id,
    )
    return success_response(data, request=request)


@router.get("/{run_id}/outputs/download")
@handle_api_errors(FileNotFoundError=("FILE_NOT_FOUND", 404))
async def download_run_outputs(
    run_id: str,
    request: Request,
    file: str | None = None,
    format: str = "tar.gz",
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = RunService(db)
    archive_bytes, media_type = await service.build_output_archive(
        run_id,
        file_path=file,
        archive_format=format,
        user_id=user.id,
        workspace_id=user.workspace_id,
    )
    return StreamingResponse(iter([archive_bytes]), media_type=media_type)


@router.post("/{run_id}/cancel")
@handle_api_errors(ValueError=("CONFLICT", 409))
async def cancel_run(
    run_id: str,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = RunService(db)
    run = await service.cancel_run(
        run_id,
        user_id=user.id,
        workspace_id=user.workspace_id,
    )
    return success_response(_serialize(run), request=request)


@router.post("/{run_id}/resume")
@handle_api_errors(ValueError=("CONFLICT", 409))
async def resume_run(
    run_id: str,
    request: Request,
    payload: RunResumeRequest | None = None,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = RunService(db)
    try:
        run = await service.resume_run(
            run_id,
            config_overrides=payload.config_overrides if payload else None,
            user_id=user.id,
            workspace_id=user.workspace_id,
        )
    except WorkflowNotEnabledError:
        return _workflow_not_enabled_response(request)
    except CompileError as exc:
        return error_response(
            code=exc.code,
            message=str(exc),
            status_code=422,
            request=request,
            details={"hint": exc.hint} if exc.hint else None,
        )
    data = {
        "run_id": run_id,
        "new_run_id": run.run_id,
        "status": getattr(run.status, "value", run.status),
        "message": "Run resumed",
        "resume_type": run.config.get("resume_type", "native"),
    }
    return success_response(data, request=request, status_code=202)


@router.post("/{run_id}/retry")
@handle_api_errors(ValueError=("CONFLICT", 409))
async def retry_run(
    run_id: str,
    request: Request,
    payload: RunRetryRequest | None = None,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = RunService(db)
    try:
        run = await service.retry_run(
            run_id,
            values=payload.values if payload else None,
            config_overrides=payload.config_overrides if payload else None,
            user_id=user.id,
            workspace_id=user.workspace_id,
        )
    except WorkflowNotEnabledError:
        return _workflow_not_enabled_response(request)
    except CompileError as exc:
        return error_response(
            code=exc.code,
            message=str(exc),
            status_code=422,
            request=request,
            details={"hint": exc.hint} if exc.hint else None,
        )
    data = {
        "run_id": run_id,
        "new_run_id": run.run_id,
        "status": getattr(run.status, "value", run.status),
        "message": "Run retried",
    }
    return success_response(data, request=request, status_code=202)


@router.post("/{run_id}/cleanup")
@handle_api_errors
async def cleanup_run(
    run_id: str,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = RunService(db)
    data = await service.cleanup_run(
        run_id,
        user_id=user.id,
        workspace_id=user.workspace_id,
        user_role=user.role,
    )
    return success_response(data, request=request)


@router.get("/{run_id}/audit")
@handle_api_errors
async def get_run_audit(
    run_id: str,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = RunService(db)
    data = await service.get_run_audit(
        run_id,
        user_id=user.id,
        workspace_id=user.workspace_id,
    )
    return success_response(data, request=request)


@router.delete("/{run_id}")
@handle_api_errors
async def delete_run(
    run_id: str,
    request: Request,
    delete_outputs: bool = False,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = RunService(db)
    await service.delete_run(
        run_id,
        delete_outputs=delete_outputs,
        user_id=user.id,
        workspace_id=user.workspace_id,
        user_role=user.role,
    )
    return success_response(None, request=request, status_code=204)
