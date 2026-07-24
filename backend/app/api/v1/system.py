from __future__ import annotations

import os
from pathlib import PurePosixPath

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, require_admin
from app.config import settings
from app.models.llm import LlmProvider, LlmProviderCredential
from app.models.project import Project
from app.models.project_workflow_binding import ProjectWorkflowBinding
from app.models.workflow import Workflow
from app.services.run_dispatch import get_run_scheduler
from app.schemas.system import DirectoryEntry, DirectoryListResponse
from app.services.docker_service import DockerService
from app.services.gpu_service import get_gpu_service
from app.services.llm.catalog import _provider_requires_credential
from app.services.llm.credentials import credential_available
from app.utils.repo_paths import allowed_local_path_roots, repo_root
from app.utils.responses import error_response, success_response

router = APIRouter(prefix="/system", tags=["system"])

_BLOCKLISTED_PATHS = frozenset({"/proc", "/sys", "/dev", "/boot"})


def _list_allowed_directories(
    path: str, *, show_hidden: bool
) -> tuple[str, list[DirectoryEntry]]:
    raw = str(path or "/").strip() or "/"
    if "\x00" in raw:
        raise ValueError("local path is not allowed")

    normalized = raw.replace("\\", "/")
    if ".." in PurePosixPath(normalized).parts:
        raise ValueError("local path is not allowed")

    expanded = os.path.expanduser(raw)
    if os.path.isabs(expanded):
        fullpath = os.path.realpath(expanded)
    else:
        fullpath = os.path.realpath(os.path.join(str(repo_root()), expanded))

    for root in allowed_local_path_roots():
        base_path = os.path.realpath(str(root))
        if fullpath.startswith(base_path):
            if os.path.commonpath([base_path, fullpath]) != base_path:
                continue
            for blocked in _BLOCKLISTED_PATHS:
                if fullpath == blocked or fullpath.startswith(blocked + "/"):
                    raise ValueError("local path is not allowed")
            if not os.path.isdir(fullpath):
                raise FileNotFoundError(fullpath)
            entries = sorted(
                (
                    DirectoryEntry(name=item.name, path=item.path)
                    for item in os.scandir(fullpath)
                    if item.is_dir() and (show_hidden or not item.name.startswith("."))
                ),
                key=lambda e: e.name.lower(),
            )
            return fullpath, entries
    raise ValueError("local path is not allowed")


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
            "detected": getattr(status, "detected", status.available),
            "mode": getattr(status, "mode", "auto"),
            "state": getattr(status, "state", "ready"),
            "container_toolkit_available": getattr(
                status, "container_toolkit_available", status.docker_nvidia_runtime
            ),
            "detected_count": getattr(status, "detected_count", len(status.gpus)),
            "selected_count": getattr(status, "selected_count", len(status.gpus)),
            "selected_gpu_uuids": list(getattr(status, "selected_gpu_uuids", ())),
            "stale": getattr(status, "stale", False),
            "nvidia_smi_found": status.nvidia_smi_found,
            "docker_nvidia_runtime": status.docker_nvidia_runtime,
            "runtime_visible_to_backend": getattr(
                status, "runtime_visible_to_backend", bool(status.gpus)
            ),
            "usable_for_gpu_workflows": getattr(
                status, "usable_for_gpu_workflows", status.parabricks_compatible
            ),
            "parabricks_compatible": status.parabricks_compatible,
            "recommendation": status.recommendation,
            "error": status.error,
            "gpus": [
                {
                    "index": gpu.index,
                    "uuid": getattr(gpu, "uuid", ""),
                    "name": gpu.name,
                    "selected": getattr(gpu, "selected", True),
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


def _env_provider_key_configured() -> bool:
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
    ) or bool(os.getenv("VLLM_BASE_URL") or os.getenv("OPENAI_COMPATIBLE_BASE_URL"))


async def _catalog_provider_configured(db: AsyncSession) -> bool:
    result = await db.execute(
        select(LlmProvider, LlmProviderCredential)
        .outerjoin(
            LlmProviderCredential,
            LlmProviderCredential.provider_id == LlmProvider.id,
        )
        .where(LlmProvider.enabled.is_(True))
    )
    for provider, credential in result.all():
        if credential_available(
            credential,
            credential_required=_provider_requires_credential(provider),
        ):
            return True
    return False


async def _provider_key_configured(db: AsyncSession) -> bool:
    return _env_provider_key_configured() or await _catalog_provider_configured(db)


def _check(
    check_id: str,
    status: str,
    *,
    severity: str = "blocking",
    facts: dict | None = None,
    docs_link: str | None = None,
    action: dict | None = None,
) -> dict:
    payload = {
        "id": check_id,
        "status": status,
        "severity": severity,
        "facts": facts or {},
    }
    if docs_link:
        payload["docs_link"] = docs_link
    if action:
        payload["action"] = action
    return payload


def _route_action(href: str) -> dict[str, str]:
    return {"kind": "route", "href": href}


def _dialog_action(dialog: str) -> dict[str, str]:
    return {"kind": "dialog", "dialog": dialog}


def _gpu_readiness_check(gpu_status) -> dict:
    available = bool(getattr(gpu_status, "available", False))
    detected = bool(getattr(gpu_status, "detected", available))
    nvidia_smi_found = bool(getattr(gpu_status, "nvidia_smi_found", False))
    docker_nvidia_runtime = bool(getattr(gpu_status, "docker_nvidia_runtime", False))
    runtime_visible_to_backend = bool(
        getattr(gpu_status, "runtime_visible_to_backend", False)
    )
    usable_for_gpu_workflows = bool(
        getattr(gpu_status, "usable_for_gpu_workflows", False)
    )
    parabricks_compatible = bool(getattr(gpu_status, "parabricks_compatible", False))
    recommendation = getattr(gpu_status, "recommendation", None)
    error = getattr(gpu_status, "error", None)
    mode = getattr(gpu_status, "mode", "auto")
    state = getattr(gpu_status, "state", "ready")
    selected_gpu_uuids = list(getattr(gpu_status, "selected_gpu_uuids", ()) or ())
    gpus = list(getattr(gpu_status, "gpus", []) or [])
    gpu_names = [
        str(getattr(gpu, "name", "")).strip()
        for gpu in gpus
        if str(getattr(gpu, "name", "")).strip()
    ]

    host_signal = "none"
    if nvidia_smi_found:
        host_signal = "nvidia_smi"
    if docker_nvidia_runtime:
        host_signal = "nvidia_runtime"
    if detected or gpu_names:
        host_signal = "gpu_detected"

    if usable_for_gpu_workflows:
        status = "pass"
    elif detected and runtime_visible_to_backend and gpus:
        status = "warn"
    elif detected and runtime_visible_to_backend:
        status = "warn"
    elif docker_nvidia_runtime:
        status = "warn"
    elif nvidia_smi_found:
        status = "warn"
    elif error and error != "nvidia-smi not found":
        status = "warn"
    else:
        status = "warn"

    return _check(
        "gpu",
        status,
        severity="optional",
        facts={
            "available": available,
            "mode": mode,
            "state": state,
            "detected": detected,
            "host_signal": host_signal,
            "nvidia_smi_found": nvidia_smi_found,
            "docker_nvidia_runtime": docker_nvidia_runtime,
            "runtime_visible_to_backend": runtime_visible_to_backend,
            "backend_visibility": "visible" if runtime_visible_to_backend else "hidden",
            "usable_for_gpu_workflows": usable_for_gpu_workflows,
            "workflow_usability": "ready" if usable_for_gpu_workflows else "optional",
            "parabricks_compatible": parabricks_compatible,
            "gpu_count": len(gpus),
            "gpu_names": gpu_names,
            "detected_count": len(gpus),
            "selected_count": len(selected_gpu_uuids),
            "selected_gpu_uuids": selected_gpu_uuids,
            "recommendation": recommendation,
            "error": error,
        },
        docs_link="/docs/operations/runbook",
        action=_route_action("/scheduler"),
    )


def _next_action(checks: list[dict]) -> dict[str, str]:
    for check in checks:
        if check["status"] == "fail" and check["severity"] == "blocking":
            action = check.get("action") or {}
            return {
                "label": "Resolve first-run blocker",
                "href": action.get("href") or "/dashboard",
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

    gpu_status = await get_gpu_service().get_status()
    scheduler = get_run_scheduler()

    project_count = await db.scalar(select(func.count()).select_from(Project))
    workflow_count = await db.scalar(select(func.count()).select_from(Workflow))
    binding_count = await db.scalar(
        select(func.count()).select_from(ProjectWorkflowBinding)
    )

    provider_ready = await _provider_key_configured(db)
    checks = [
        _check(
            "backend",
            "pass",
            severity="info",
            facts={"available": True},
            docs_link="/docs/getting-started/docker",
        ),
        _check(
            "provider_key",
            "pass" if provider_ready else "fail",
            facts={"configured": provider_ready},
            docs_link="/docs/getting-started/docker",
            action=_route_action("/settings?section=providers"),
        ),
        _check(
            "docker",
            "pass" if docker_available else "fail",
            facts={"available": docker_available},
            docs_link="/docs/getting-started/docker",
            action=_route_action("/images"),
        ),
        _check(
            "scheduler",
            "pass" if scheduler is not None else "fail",
            facts={"available": scheduler is not None},
            docs_link="/docs/operations/runbook",
            action=_route_action("/scheduler"),
        ),
        _gpu_readiness_check(gpu_status),
        _check(
            "project",
            "pass" if (project_count or 0) > 0 else "fail",
            facts={"count": project_count or 0},
            action=_dialog_action("create_project"),
        ),
        _check(
            "workflow_registry",
            "pass" if (workflow_count or 0) > 0 else "fail",
            facts={"count": workflow_count or 0},
            action=_route_action("/workflows?scope=hub"),
        ),
        _check(
            "workflow_binding",
            "pass" if (binding_count or 0) > 0 else "fail",
            facts={"count": binding_count or 0},
            action=_route_action("/workflows?scope=hub"),
        ),
    ]

    blocked = any(
        check["status"] == "fail" and check["severity"] == "blocking"
        for check in checks
    )
    required_checks = [check for check in checks if check["severity"] == "blocking"]
    required_completed = sum(
        1 for check in required_checks if check["status"] == "pass"
    )
    optional_checks = [check for check in checks if check["severity"] == "optional"]
    return success_response(
        {
            "severity": "blocked" if blocked else "ready",
            "next_action": _next_action(checks),
            "checks": checks,
            "summary": {
                "required_total": len(required_checks),
                "required_completed": required_completed,
                "optional_total": len(optional_checks),
                "optional_warnings": sum(
                    1 for check in optional_checks if check["status"] != "pass"
                ),
                "docker_available": docker_available,
                "nvidia_runtime": nvidia_runtime,
                "gpu_available": getattr(gpu_status, "available", False),
                "gpu_detected": getattr(
                    gpu_status, "detected", getattr(gpu_status, "available", False)
                ),
                "gpu_runtime_visible_to_backend": getattr(
                    gpu_status, "runtime_visible_to_backend", False
                ),
                "gpu_usable_for_workflows": getattr(
                    gpu_status, "usable_for_gpu_workflows", False
                ),
                "provider_key_configured": provider_ready,
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
    try:
        resolved, entries = _list_allowed_directories(path, show_hidden=show_hidden)
    except ValueError:
        return error_response(
            code="DIRECTORY_BLOCKED",
            message="Directory is outside the allowed local roots",
            status_code=403,
            request=request,
        )
    except FileNotFoundError as exc:
        resolved = str(exc)
        return error_response(
            code="DIRECTORY_NOT_FOUND",
            message=f"Directory not found: {resolved}",
            status_code=404,
            request=request,
        )
    except PermissionError:
        return error_response(
            code="DIRECTORY_PERMISSION_DENIED",
            message="Permission denied",
            status_code=403,
            request=request,
        )

    parent_path = os.path.dirname(resolved)
    parent = parent_path if parent_path != resolved else None
    result = DirectoryListResponse(
        path=resolved,
        parent=parent,
        directories=entries,
    )

    return success_response(
        result.model_dump(),
        request=request,
    )
