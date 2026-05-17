from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_admin
from app.config import settings
from app.models.project import Project
from app.models.project_workflow_binding import ProjectWorkflowBinding
from app.models.workflow import Workflow
from app.services.run_dispatch import get_run_scheduler
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


def _provider_key_configured() -> bool:
    return any(
        bool(getattr(settings, key, "").strip())
        for key in (
            "anthropic_api_key",
            "openai_api_key",
            "gemini_api_key",
            "openrouter_api_key",
            "deepseek_api_key",
            "xai_api_key",
            "qwen_api_key",
            "kimi_api_key",
            "minimax_api_key",
        )
    )


def _check(
    check_id: str,
    label: str,
    status: str,
    detail: str,
    *,
    severity: str = "blocking",
    hint: str | None = None,
    docs_link: str | None = None,
    action_label: str | None = None,
    action_href: str | None = None,
) -> dict[str, str]:
    payload = {
        "id": check_id,
        "label": label,
        "status": status,
        "severity": severity,
        "detail": detail,
    }
    if hint:
        payload["hint"] = hint
    if docs_link:
        payload["docs_link"] = docs_link
    if action_label:
        payload["action_label"] = action_label
    if action_href:
        payload["action_href"] = action_href
    return payload


def _next_action(checks: list[dict[str, str]]) -> dict[str, str]:
    for check in checks:
        if check["status"] == "fail" and check["severity"] == "blocking":
            return {
                "label": check.get("action_label") or "Resolve first-run blocker",
                "href": check.get("action_href") or "/dashboard",
            }
    return {
        "label": "Run a workflow",
        "href": "/workflows?scope=project",
    }


@router.get("/readiness")
async def get_readiness(request: Request, db: AsyncSession = Depends(get_db)):
    """First-run readiness checklist for web onboarding and ``bif doctor``."""
    docker_service = DockerService()
    docker_available = await docker_service.is_available()
    nvidia_runtime = (
        await docker_service.check_nvidia_runtime() if docker_available else False
    )
    parabricks_image = (
        await docker_service.get_parabricks_image() if docker_available else None
    )

    gpu_status = await get_gpu_service().get_status()
    scheduler = get_run_scheduler()

    project_count = await db.scalar(select(func.count()).select_from(Project))
    workflow_count = await db.scalar(select(func.count()).select_from(Workflow))
    binding_count = await db.scalar(
        select(func.count()).select_from(ProjectWorkflowBinding)
    )

    provider_ready = _provider_key_configured()
    checks = [
        _check(
            "backend",
            "Backend API",
            "pass",
            "Backend is responding",
            severity="info",
            docs_link="/docs/getting-started/docker",
        ),
        _check(
            "provider_key",
            "AI provider key",
            "pass" if provider_ready else "fail",
            "At least one AI provider key is configured"
            if provider_ready
            else "No AI provider key is configured",
            hint=None
            if provider_ready
            else "Set ANTHROPIC_API_KEY, OPENAI_API_KEY, GEMINI_API_KEY, or another supported provider key.",
            docs_link="/docs/getting-started/docker",
            action_label="Add an AI provider key",
            action_href="/settings",
        ),
        _check(
            "docker",
            "Docker",
            "pass" if docker_available else "fail",
            "Docker is available"
            if docker_available
            else "Docker is not reachable from the backend",
            hint=None
            if docker_available
            else "Start Docker Desktop or the Docker daemon, then re-run readiness.",
            docs_link="/docs/getting-started/docker",
            action_label="Open image inventory",
            action_href="/images",
        ),
        _check(
            "scheduler",
            "Scheduler",
            "pass" if scheduler is not None else "fail",
            "Persistent scheduler is active"
            if scheduler is not None
            else "Persistent scheduler is not available",
            hint=None
            if scheduler is not None
            else "Restart the backend and check scheduler startup logs.",
            docs_link="/docs/operations/runbook",
            action_label="Open scheduler",
            action_href="/scheduler",
        ),
        _check(
            "gpu",
            "GPU",
            "pass" if getattr(gpu_status, "available", False) else "warn",
            "GPU is available"
            if getattr(gpu_status, "available", False)
            else "No GPU detected; CPU workflows can still run",
            severity="optional",
            hint=None
            if getattr(gpu_status, "available", False)
            else "Install NVIDIA drivers/runtime only if this workflow requires GPU acceleration.",
            docs_link="/docs/operations/runbook",
        ),
        _check(
            "parabricks_image",
            "Parabricks image",
            "pass" if parabricks_image is not None else "warn",
            "Parabricks image is available"
            if parabricks_image is not None
            else "Parabricks image is not available; non-Parabricks workflows are unaffected",
            severity="optional",
            docs_link="/docs/workflows/parabricks-wgs",
            action_label="Open images",
            action_href="/images",
        ),
        _check(
            "project",
            "Project",
            "pass" if (project_count or 0) > 0 else "fail",
            f"{project_count or 0} project(s) exist"
            if (project_count or 0) > 0
            else "No project exists yet",
            hint=None
            if (project_count or 0) > 0
            else "Create a project before launching the first run.",
            action_label="Create a project",
            action_href="/dashboard",
        ),
        _check(
            "workflow_registry",
            "Workflow registry",
            "pass" if (workflow_count or 0) > 0 else "fail",
            f"{workflow_count or 0} workflow(s) registered"
            if (workflow_count or 0) > 0
            else "No workflows are registered yet",
            hint=None
            if (workflow_count or 0) > 0
            else "Register or import a workflow from the workflow hub.",
            action_label="Open workflow hub",
            action_href="/workflows?scope=hub",
        ),
        _check(
            "workflow_binding",
            "Project workflow binding",
            "pass" if (binding_count or 0) > 0 else "fail",
            f"{binding_count or 0} project workflow binding(s) exist"
            if (binding_count or 0) > 0
            else "No workflow is enabled for a project yet",
            hint=None
            if (binding_count or 0) > 0
            else "Bind a workflow to a project before submitting a run.",
            action_label="Enable a workflow",
            action_href="/workflows?scope=hub",
        ),
    ]

    blocked = any(
        check["status"] == "fail" and check["severity"] == "blocking"
        for check in checks
    )
    return success_response(
        {
            "severity": "blocked" if blocked else "ready",
            "next_action": _next_action(checks),
            "checks": checks,
            "summary": {
                "docker_available": docker_available,
                "nvidia_runtime": nvidia_runtime,
                "gpu_available": getattr(gpu_status, "available", False),
                "parabricks_image_available": parabricks_image is not None,
                "projects": project_count or 0,
                "workflows": workflow_count or 0,
                "workflow_bindings": binding_count or 0,
            },
        },
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
