from __future__ import annotations

import aiofiles
from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.api.error_handler import handle_api_errors
from app.auth.session import AuthUser
from app.config import settings
from app.schemas.storage import StorageScanRequest
from app.services.storage_service import StorageService
from app.utils.responses import success_response


router = APIRouter(prefix="/storage", tags=["storage"])


@router.get("/sources")
@handle_api_errors(FileNotFoundError=("FILE_NOT_FOUND", 404))
async def list_sources(
    request: Request,
    project_id: str,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    del user
    service = StorageService(db)
    data = await service.list_sources(project_id=project_id)
    return success_response([item.model_dump(mode="json") for item in data], request=request)


@router.get("/browse")
@handle_api_errors(FileNotFoundError=("FILE_NOT_FOUND", 404))
async def browse_storage(
    request: Request,
    project_id: str,
    source_id: str = "project",
    path: str = ".",
    recursive: bool = False,
    pattern: str | None = None,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    del user
    service = StorageService(db)
    data = await service.browse(
        project_id=project_id,
        source_id=source_id,
        path=path,
        recursive=recursive,
        pattern=pattern,
    )
    return success_response(data.model_dump(mode="json"), request=request)


@router.get("/read")
@handle_api_errors(FileNotFoundError=("FILE_NOT_FOUND", 404))
async def read_storage(
    request: Request,
    project_id: str,
    uri: str,
    lines: int = 100,
    offset: int = 0,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    del user
    service = StorageService(db)
    data = await service.read(
        project_id=project_id,
        uri=uri,
        lines=lines,
        offset=offset,
    )
    return success_response(data.model_dump(mode="json"), request=request)


@router.get("/download")
@handle_api_errors(FileNotFoundError=("FILE_NOT_FOUND", 404))
async def download_storage(
    request: Request,
    project_id: str,
    uri: str,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    del user
    service = StorageService(db)
    resolved = await service.resolve_asset(project_id=project_id, uri=uri)
    target = resolved.path
    if not target.is_file():
        raise ValueError("asset is a directory")

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


@router.post("/upload")
@handle_api_errors(FileNotFoundError=("FILE_NOT_FOUND", 404))
async def upload_storage(
    request: Request,
    project_id: str = Form(...),
    source_id: str = Form("project"),
    path: str | None = Form(None),
    overwrite: bool = Form(False),
    file: UploadFile = File(...),
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    del user
    content = await file.read()
    if len(content) > settings.max_upload_size_bytes:
        raise ValueError(
            f"File exceeds maximum upload size of {settings.max_upload_size_bytes} bytes"
        )
    service = StorageService(db)
    data = await service.upload(
        project_id=project_id,
        source_id=source_id,
        path=path,
        filename=file.filename or "upload",
        content=content,
        overwrite=overwrite,
    )
    return success_response(data.model_dump(mode="json"), request=request, status_code=201)


@router.post("/scan")
@handle_api_errors(FileNotFoundError=("FILE_NOT_FOUND", 404))
async def scan_storage(
    payload: StorageScanRequest,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    del user
    service = StorageService(db)
    data = await service.scan(
        project_id=payload.project_id,
        source_id=payload.source_id,
        path=payload.path,
        file_types=payload.file_types,
    )
    return success_response(data.model_dump(mode="json"), request=request)
