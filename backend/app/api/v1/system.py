from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Request

from app.api.deps import require_admin
from app.schemas.system import DirectoryEntry, DirectoryListResponse
from app.services.docker_service import DockerService
from app.services.gpu_service import get_gpu_service
from app.utils.repo_paths import resolve_repo_path
from app.utils.responses import error_response, success_response

router = APIRouter(prefix="/system", tags=["system"])

_BLOCKLISTED_PATHS = frozenset({"/proc", "/sys", "/dev", "/boot"})


@router.get("/ping")
async def ping():
    """Lightweight liveness probe. No external calls — suitable for Docker HEALTHCHECK."""
    return {"status": "ok"}


@router.get("/health")
async def health_check(request: Request):
    """System health check endpoint."""
    docker_service = DockerService()
    docker_available = await docker_service.is_available()
    nvidia_runtime = (
        await docker_service.check_nvidia_runtime() if docker_available else False
    )
    parabricks_image = (
        await docker_service.get_parabricks_image() if docker_available else None
    )

    gpu_service = get_gpu_service()
    gpu_status = await gpu_service.get_status()

    return success_response(
        {
            "status": "healthy",
            "docker": {
                "available": docker_available,
                "nvidia_runtime": nvidia_runtime,
            },
            "gpu": {
                "available": gpu_status.available,
                "parabricks_compatible": gpu_status.parabricks_compatible,
            },
            "parabricks": {
                "image_available": parabricks_image is not None,
                "image_name": parabricks_image.full_name if parabricks_image else None,
            },
        },
        request=request,
    )


@router.get("/gpu")
async def get_gpu_status(request: Request):
    """Get detailed GPU status and compatibility info."""
    gpu_service = get_gpu_service()
    status = await gpu_service.get_status()

    return success_response(
        {
            "available": status.available,
            "nvidia_smi_found": status.nvidia_smi_found,
            "docker_nvidia_runtime": status.docker_nvidia_runtime,
            "parabricks_compatible": status.parabricks_compatible,
            "recommendation": status.recommendation,
            "error": status.error,
            "gpus": [
                {
                    "index": gpu.index,
                    "name": gpu.name,
                    "memory_total_mb": gpu.memory_total_mb,
                    "memory_free_mb": gpu.memory_free_mb,
                    "driver_version": gpu.driver_version,
                    "cuda_version": gpu.cuda_version,
                    "compute_capability": gpu.compute_capability,
                    "gpu_type": gpu.gpu_type,
                }
                for gpu in status.gpus
            ],
        },
        request=request,
    )


@router.get("/gpu/metrics")
async def get_gpu_metrics(request: Request):
    """Get real-time GPU metrics for monitoring."""
    gpu_service = get_gpu_service()
    metrics = await gpu_service.get_gpu_metrics()

    return success_response(
        {"metrics": metrics},
        request=request,
    )


@router.get("/directories")
async def list_directories(
    request: Request,
    path: str = "/",
    show_hidden: bool = False,
    _user=Depends(require_admin),
):
    """Browse local filesystem directories for admin-only external roots."""
    raw = Path(path).expanduser()
    if raw.is_absolute():
        resolved = raw.resolve()
    else:
        resolved = resolve_repo_path(path)

    for blocked in _BLOCKLISTED_PATHS:
        if str(resolved) == blocked or str(resolved).startswith(blocked + "/"):
            return error_response(
                code="DIRECTORY_BLOCKED",
                message=f"Access to {resolved} is not allowed",
                status_code=403,
                request=request,
            )

    if not resolved.is_dir():
        return error_response(
            code="DIRECTORY_NOT_FOUND",
            message=f"Directory not found: {resolved}",
            status_code=404,
            request=request,
        )

    try:
        entries = sorted(
            (
                DirectoryEntry(name=item.name, path=str(item))
                for item in resolved.iterdir()
                if item.is_dir() and (show_hidden or not item.name.startswith("."))
            ),
            key=lambda e: e.name.lower(),
        )
    except PermissionError:
        return error_response(
            code="DIRECTORY_PERMISSION_DENIED",
            message=f"Permission denied: {resolved}",
            status_code=403,
            request=request,
        )

    parent = str(resolved.parent) if resolved.parent != resolved else None
    result = DirectoryListResponse(
        path=str(resolved),
        parent=parent,
        directories=entries,
    )

    return success_response(
        result.model_dump(),
        request=request,
    )
