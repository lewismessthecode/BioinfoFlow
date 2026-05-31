from __future__ import annotations

import aiofiles
from fastapi import APIRouter, Depends, Request, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.api.error_handler import handle_api_errors
from app.auth.session import AuthUser
from app.config import settings
from app.schemas.file import FileScanRequest, FileWriteRequest, FileUploadResponse
from app.services.file_service import FileService
from app.utils.responses import error_response, success_response


router = APIRouter(prefix="/files", tags=["files"])


@router.get("")
@handle_api_errors(FileNotFoundError=("FILE_NOT_FOUND", 404))
async def list_files(
    request: Request,
    project_id: str,
    path: str = ".",
    recursive: bool = False,
    pattern: str | None = None,
    data_root: int | None = None,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = FileService(db)
    data = await service.list_files(
        project_id=project_id, path=path, recursive=recursive, pattern=pattern,
        data_root=data_root,
        user_id=user.id,
        workspace_id=user.workspace_id,
    )
    return success_response(
        data.model_dump(mode="json", by_alias=True), request=request
    )


@router.get("/read")
@handle_api_errors(FileNotFoundError=("FILE_NOT_FOUND", 404))
async def read_file(
    request: Request,
    project_id: str,
    path: str,
    lines: int = 100,
    offset: int = 0,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = FileService(db)
    data = await service.read_file(
        project_id=project_id,
        path=path,
        lines=lines,
        offset=offset,
        user_id=user.id,
        workspace_id=user.workspace_id,
    )
    return success_response(
        data.model_dump(mode="json", by_alias=True), request=request
    )


@router.get("/download")
@handle_api_errors(FileNotFoundError=("FILE_NOT_FOUND", 404))
async def download_file(
    request: Request,
    project_id: str,
    path: str,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = FileService(db)
    target, root = await service.resolve_path(
        project_id=project_id,
        path=path,
        user_id=user.id,
        workspace_id=user.workspace_id,
    )

    if target.is_dir():
        return error_response(
            code="VALIDATION_ERROR",
            message="path is a directory",
            status_code=400,
            request=request,
        )

    async def file_iterator():
        async with aiofiles.open(target, "rb") as handle:
            while True:
                chunk = await handle.read(1024 * 1024)
                if not chunk:
                    break
                yield chunk

    return StreamingResponse(
        file_iterator(),
        media_type="application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename={target.name}"},
    )


@router.post("/write")
@handle_api_errors(FileNotFoundError=("FILE_NOT_FOUND", 404))
async def write_file(
    payload: FileWriteRequest,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = FileService(db)
    data = await service.write_file(
        project_id=payload.project_id,
        path=payload.path,
        content=payload.content,
        user_id=user.id,
        workspace_id=user.workspace_id,
    )
    return success_response(data, request=request)


@router.post("/upload")
@handle_api_errors(FileNotFoundError=("FILE_NOT_FOUND", 404))
async def upload_file(
    request: Request,
    project_id: str = Form(...),
    path: str | None = Form(None),
    overwrite: bool = Form(False),
    file: UploadFile = File(...),
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = FileService(db)
    content = await file.read()
    if len(content) > settings.max_upload_size_bytes:
        return error_response(
            code="FILE_TOO_LARGE",
            message=f"File exceeds maximum upload size of {settings.max_upload_size_bytes} bytes",
            status_code=413,
            request=request,
        )
    data = await service.write_upload(
        project_id=project_id,
        path=path,
        filename=file.filename or "upload",
        content=content,
        overwrite=overwrite,
        user_id=user.id,
        workspace_id=user.workspace_id,
    )
    return success_response(
        FileUploadResponse.model_validate(data).model_dump(mode="json", by_alias=True),
        request=request,
        status_code=201,
    )


@router.post("/scan")
@handle_api_errors(FileNotFoundError=("FILE_NOT_FOUND", 404))
async def scan_directory(
    payload: FileScanRequest,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = FileService(db)
    data = await service.scan_directory(
        project_id=payload.project_id,
        path=payload.path,
        file_types=payload.file_types,
        data_root=payload.data_root,
        user_id=user.id,
        workspace_id=user.workspace_id,
    )
    return success_response(
        data.model_dump(mode="json", by_alias=True), request=request
    )


@router.delete("")
@handle_api_errors(FileNotFoundError=("FILE_NOT_FOUND", 404))
async def delete_path(
    request: Request,
    project_id: str,
    path: str,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = FileService(db)
    data = await service.delete_path(
        project_id=project_id,
        path=path,
        user_id=user.id,
        workspace_id=user.workspace_id,
        user_role=user.role,
    )
    return success_response(data, request=request, status_code=200)
