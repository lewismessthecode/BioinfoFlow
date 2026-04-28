from __future__ import annotations

from os import cpu_count
from pathlib import Path
from typing import Any

from app.utils.logging import get_logger


_PROVIDER_KEY_FIELDS = (
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


def build_startup_summary(settings: Any) -> dict[str, Any]:
    """Build a redacted startup summary for logs.

    This deliberately logs configuration shape and path choices, not secrets.
    It is meant to be visible in local terminals and `docker compose logs`.
    """
    return {
        "app": {
            "name": settings.app_name,
            "version": settings.app_version,
            "debug": bool(settings.debug),
        },
        "auth": {
            "mode": settings.resolved_auth_mode,
            "enabled": bool(settings.auth_enabled_effective),
            "better_auth_db_path": str(settings.better_auth_db_path),
        },
        "database": {
            "url": _redact_database_url(str(settings.database_url)),
        },
        "storage": {
            "bioinfoflow_home": str(settings.bioinfoflow_home),
            "bioinfoflow_home_host": str(settings.bioinfoflow_home_host or ""),
            "identity_mount_required": bool(settings.bioinfoflow_home_host),
            "path_translation_enabled": bool(settings.allow_path_translation),
            "roots": {
                "state": str(settings.state_root),
                "projects": str(settings.projects_root),
                "sources": str(settings.sources_root),
                "deliveries": str(settings.deliveries_root),
                "reference": str(settings.reference_root),
                "database": str(settings.database_root),
                "workflow_registry": str(settings.workflow_registry_root),
                "engine_cache": str(settings.engine_cache_root),
            },
        },
        "workflow_engines": {
            "nextflow_bin": str(settings.nextflow_bin),
            "miniwdl_bin": str(settings.miniwdl_bin),
            "docker_socket": str(settings.docker_socket),
        },
        "scheduler": {
            "total_slots": int(settings.scheduler_total_slots),
            "effective_total_slots": _effective_total_slots(settings),
            "max_workers": int(settings.scheduler_max_workers),
            "max_concurrency": int(settings.scheduler_max_concurrency),
            "max_queue_depth": int(settings.scheduler_max_queue_depth),
            "resource_check_enabled": bool(settings.scheduler_resource_check_enabled),
            "safety_cpu": int(settings.scheduler_safety_cpu),
            "safety_memory_gb": float(settings.scheduler_safety_memory_gb),
            "safety_disk_gb": float(settings.scheduler_safety_disk_gb),
        },
        "agent": {
            "provider": str(settings.agent_provider),
            "engine": str(settings.agent_engine),
            "model": str(settings.agent_model),
            "max_tokens": int(settings.agent_max_tokens),
            "observability": bool(settings.agent_observability),
            "hermes_max_concurrency": int(settings.agent_hermes_max_concurrency),
            "hermes_state_db": str(settings.agent_hermes_state_db),
            "langsmith_tracing": bool(
                settings.langsmith_tracing or settings.langsmith_tracing_v2
            ),
        },
        "providers": {
            field: _presence(getattr(settings, field, ""))
            for field in _PROVIDER_KEY_FIELDS
        },
        "network": {
            "cors_origins": list(settings.cors_origins),
            "cors_origin_regex": str(settings.cors_origin_regex),
            "trusted_hosts": list(settings.trusted_hosts),
        },
        "uploads": {
            "max_file_upload_mb": _bytes_to_mb(settings.max_upload_size_bytes),
            "max_image_upload_mb": _bytes_to_mb(settings.max_image_upload_size_bytes),
        },
    }


def log_startup_summary(settings: Any, *, logger: Any | None = None) -> None:
    active_logger = logger or get_logger(__name__)
    active_logger.info("startup.config", **build_startup_summary(settings))


def _presence(value: str | None) -> str:
    return "set" if value else "unset"


def _bytes_to_mb(value: int) -> int:
    return int(round(int(value) / (1024 * 1024)))


def _effective_total_slots(settings: Any) -> int:
    if int(settings.scheduler_total_slots) > 0:
        return int(settings.scheduler_total_slots)
    if int(settings.scheduler_max_concurrency) > 0:
        return int(settings.scheduler_max_concurrency)
    return cpu_count() or 4


def _redact_database_url(url: str) -> str:
    if "://" not in url:
        return url
    scheme, rest = url.split("://", 1)
    if "@" not in rest:
        return url
    credentials, host = rest.split("@", 1)
    if ":" not in credentials:
        return f"{scheme}://***@{host}"
    user, _password = credentials.split(":", 1)
    return f"{scheme}://{user}:***@{host}"


def path_exists(path: str | Path) -> bool:
    return Path(path).expanduser().exists()
