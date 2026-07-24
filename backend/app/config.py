from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    """Application configuration via environment variables."""

    # Precedence:
    # 1. Shell-exported env vars
    # 2. backend/.env (optional backend-only override)
    # 3. repo-root .env (shared defaults for Docker and local dev)
    # 4. code defaults below
    model_config = SettingsConfigDict(
        env_file=(str(REPO_ROOT / ".env"), str(BACKEND_ROOT / ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application
    app_name: str = "Bioinfoflow"
    app_version: str = "0.2.0"  # x-release-please-version
    debug: bool = False
    repo_root: str = str(REPO_ROOT)
    bioinfoflow_home: str = "data"
    bioinfoflow_skills_root: str = ""
    # Path Contract v3: identity-mount invariant. When the backend runs in a
    # container, BIOINFOFLOW_HOME_HOST must equal BIOINFOFLOW_HOME (the compose
    # volume must be `-v ${BIOINFOFLOW_HOME}:${BIOINFOFLOW_HOME}`). Leave empty
    # on bare-metal/`uv run uvicorn` to skip the assertion.
    bioinfoflow_home_host: str = ""
    # Escape hatch for emergency debugging only. When enabled, legacy
    # host↔container path translation via Docker API is restored. Normal
    # deployments must rely on identity mount and keep this off.
    allow_path_translation: bool = False

    @field_validator("repo_root", mode="before")
    @classmethod
    def normalize_repo_root(cls, value: Any) -> str:
        """Fall back to computed default when REPO_ROOT is empty or unset."""
        if not value or not str(value).strip():
            return str(REPO_ROOT)
        return str(value).strip()

    @field_validator("bioinfoflow_home", mode="before")
    @classmethod
    def normalize_bioinfoflow_home(cls, value: Any) -> str:
        candidate = Path(str(value).strip()) if value else Path("data")
        if not candidate.is_absolute():
            candidate = REPO_ROOT / candidate
        return str(candidate.expanduser().resolve())

    @field_validator("bioinfoflow_skills_root", mode="before")
    @classmethod
    def normalize_bioinfoflow_skills_root(cls, value: Any) -> str:
        if value is None or not str(value).strip():
            return ""
        candidate = Path(str(value).strip()).expanduser()
        if not candidate.is_absolute():
            candidate = REPO_ROOT / candidate
        return str(candidate.resolve())

    # Auth (Better Auth shared DB)
    better_auth_db_path: str = ""
    auth_mode: str = ""
    auth_enabled: bool = True

    # Database (SQLite MVP)
    database_url: str = ""

    # Nextflow
    nextflow_bin: str = Field(
        default="/usr/local/bin/nextflow",
        description="Path to nextflow binary - customize via NEXTFLOW_BIN environment variable",
    )

    # MiniWDL (WDL)
    miniwdl_bin: str = Field(
        default="/usr/local/bin/miniwdl",
        description="Path to miniwdl binary - customize via MINIWDL_BIN environment variable",
    )

    # Docker
    docker_socket: str = "unix:///var/run/docker.sock"
    bioinfoflow_gpu_mode: str = "auto"
    bioinfoflow_gpu_devices: str = "all"
    gpu_probe_timeout_seconds: float = 10.0
    gpu_inventory_cache_seconds: float = 30.0

    # Agent / LLM
    agent_sandbox_enabled: bool = False  # Enable OS-level sandboxing for code execution
    # When sandboxing is enabled but no OS sandbox binary is available, refuse to
    # run unconfined (fail closed) rather than silently dropping the boundary.
    agent_sandbox_fail_closed: bool = True
    # Allow the sandboxed process to reach the network. Off by default.
    agent_sandbox_allow_network: bool = False
    # Permit a bash call to opt out of the sandbox via dangerously_disable_sandbox.
    agent_sandbox_allow_unsandboxed: bool = False
    agent_max_tokens: int = 16384
    agent_observability: bool = True
    agent_log_truncate_chars: int = 1200
    agent_max_iterations: int = 90  # Per-turn loop safety limit
    removed_agent_max_rounds: str | None = Field(
        default=None,
        validation_alias="AGENT_MAX_ROUNDS",
        exclude=True,
    )
    agent_retry_max_attempts: int = 3
    agent_retry_base_delay_seconds: float = 0.25
    agent_retry_max_delay_seconds: float = 2.0
    agent_model_attempt_timeout_seconds: float = 120.0
    agent_turn_lease_seconds: int = 300
    agent_compact_threshold: int = 50000  # Auto-compact token threshold
    agent_project_instructions_max_bytes: int = 32768
    agent_attachment_file_max_bytes: int = 25 * 1024 * 1024
    agent_attachment_image_max_bytes: int = 20 * 1024 * 1024
    agent_attachment_folder_max_bytes: int = 100 * 1024 * 1024
    agent_attachment_folder_max_files: int = 1000
    agent_attachment_turn_max_images: int = 10
    agent_attachment_text_max_bytes: int = 64 * 1024
    agent_attachment_pdf_max_pages: int = 200
    agent_attachment_orphan_ttl_seconds: int = 24 * 60 * 60

    # Provider API keys used by LLM catalog bootstrap.
    # UI-configured providers are stored in the LLM catalog and take precedence.
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    gemini_api_key: str = ""
    openrouter_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"
    deepseek_api_key: str = ""
    xai_api_key: str = ""
    qwen_api_key: str = ""
    kimi_api_key: str = ""
    minimax_api_key: str = ""
    bioinfoflow_credential_key: str = ""

    # OpenAI-compatible speech recognition. Empty base URL keeps voice dictation
    # disabled; the backend never loads an ASR model itself.
    asr_provider: str = ""
    asr_base_url: str = ""
    asr_api_key: str = ""
    asr_model: str = ""
    asr_language: str = "zh"
    asr_context_terms: list[str] = ["Bioinfoflow", "Nextflow", "MiniWDL", "FASTQ"]
    asr_max_upload_size_bytes: int = 20 * 1024 * 1024
    asr_timeout_seconds: float = 90.0

    # Extended thinking
    agent_thinking_enabled: bool = True
    agent_thinking_budget: int = 10000
    agent_thinking_effort: str = "medium"
    agent_thinking_level: str = "medium"

    scheduler_total_slots: int = 0  # 0 = auto-detect (cpu_count)
    scheduler_max_workers: int = 0  # 0 = same as total_slots
    scheduler_max_concurrency: int = 4
    scheduler_max_queue_depth: int = 500
    scheduler_poll_interval: float = 1.0
    scheduler_stale_timeout_minutes: int = 30
    scheduler_resource_check_enabled: bool = True
    scheduler_resource_sample_interval: float = 30.0
    scheduler_safety_cpu: int = 2
    scheduler_safety_memory_gb: float = 2.0
    scheduler_safety_disk_gb: float = 10.0
    scheduler_worker_heartbeat_grace_seconds: int = 90
    langsmith_tracing: bool = False
    langsmith_tracing_v2: bool = False
    langsmith_api_key: str = ""
    langsmith_project: str = "bioinfoflow"
    langsmith_endpoint: str = "https://api.smith.langchain.com"

    # CORS
    cors_origins: list[str] = ["http://localhost:3000"]
    cors_origin_regex: str = r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"
    trusted_hosts: list[str] = [
        "localhost",
        "127.0.0.1",
        "::1",
        "test",
        "testserver",
    ]

    # Upload limits (bytes)
    max_upload_size_bytes: int = 100 * 1024 * 1024  # 100 MB for file uploads
    max_image_upload_size_bytes: int = 500 * 1024 * 1024  # 500 MB for container images

    @field_validator("auth_mode", mode="before")
    @classmethod
    def normalize_auth_mode(cls, value: Any) -> str:
        if value is None:
            return ""
        normalized = str(value).strip().lower()
        if normalized in {"personal", "team", "dev"}:
            return normalized
        return ""

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: Any) -> list[str]:
        return cls._parse_str_list(value)

    @field_validator("trusted_hosts", mode="before")
    @classmethod
    def parse_trusted_hosts(cls, value: Any) -> list[str]:
        return cls._parse_str_list(value)

    @field_validator("asr_context_terms", mode="before")
    @classmethod
    def parse_asr_context_terms(cls, value: Any) -> list[str]:
        return cls._parse_str_list(value)

    @classmethod
    def _parse_str_list(cls, value: Any) -> list[str]:
        if isinstance(value, str):
            cleaned = value.strip()
            if not cleaned:
                return []
            try:
                parsed = json.loads(cleaned)
            except json.JSONDecodeError:
                return [item.strip() for item in cleaned.split(",") if item.strip()]
            if isinstance(parsed, list):
                return [str(item) for item in parsed]
        return list(value)

    @field_validator("database_url", mode="before")
    @classmethod
    def normalize_database_url(cls, value: Any) -> str:
        if value is None:
            return ""
        return _resolve_sqlite_url(str(value).strip())

    @field_validator("better_auth_db_path", mode="before")
    @classmethod
    def normalize_better_auth_db_path(cls, value: Any) -> str:
        if value is None:
            return ""
        candidate = Path(str(value).strip()).expanduser()
        if not str(value).strip():
            return ""
        if not candidate.is_absolute():
            candidate = REPO_ROOT / candidate
        return str(candidate.resolve())

    @model_validator(mode="after")
    def reject_removed_agent_max_rounds(self) -> Settings:
        if self.removed_agent_max_rounds is not None:
            raise ValueError(
                "AGENT_MAX_ROUNDS was removed. Use AGENT_MAX_ITERATIONS instead."
            )
        return self

    @model_validator(mode="after")
    def apply_path_defaults(self) -> Settings:
        if not self.database_url:
            self.database_url = _resolve_sqlite_url(
                f"sqlite+aiosqlite:///{(self.state_root / 'bioinfoflow.db').resolve()}"
            )
        if not self.better_auth_db_path:
            self.better_auth_db_path = str(
                (self.state_root / "auth" / "better-auth.db").resolve()
            )
        return self

    @property
    def resolved_auth_mode(self) -> str:
        if self.auth_mode:
            return self.auth_mode
        return "personal" if self.auth_enabled else "dev"

    @property
    def auth_enabled_effective(self) -> bool:
        return self.resolved_auth_mode != "dev"

    @property
    def auth_is_team(self) -> bool:
        return self.resolved_auth_mode == "team"

    @property
    def auth_is_personal(self) -> bool:
        return self.resolved_auth_mode == "personal"

    @property
    def state_root(self) -> Path:
        return Path(self.bioinfoflow_home) / "state"

    @property
    def skills_root(self) -> Path:
        if self.bioinfoflow_skills_root:
            return Path(self.bioinfoflow_skills_root)
        return Path(self.bioinfoflow_home) / "skills"

    @property
    def projects_root(self) -> Path:
        return Path(self.bioinfoflow_home) / "projects"

    @property
    def sources_root(self) -> Path:
        return Path(self.bioinfoflow_home) / "sources"

    @property
    def deliveries_root(self) -> Path:
        return self.sources_root / "deliveries"

    @property
    def reference_root(self) -> Path:
        return self.sources_root / "reference"

    @property
    def database_root(self) -> Path:
        return self.sources_root / "database"

    @property
    def workflow_registry_root(self) -> Path:
        return self.state_root / "workflows"

    @property
    def engine_cache_root(self) -> Path:
        return self.state_root / "engine" / "cache"

    @property
    def nextflow_cache_root(self) -> Path:
        return self.engine_cache_root / "nextflow"

    @property
    def miniwdl_cache_root(self) -> Path:
        return self.engine_cache_root / "miniwdl"


def _resolve_sqlite_url(url: str) -> str:
    prefixes = ("sqlite+aiosqlite:///", "sqlite:///")
    if not url.startswith(prefixes):
        return url

    relative_path = None
    prefix = ""
    for candidate in prefixes:
        if url.startswith(candidate):
            prefix = candidate
            relative_path = url[len(candidate) :]
            break

    if relative_path is None:
        return url

    if not relative_path or relative_path in {":memory:"}:
        return url

    if relative_path.startswith("/") or relative_path.startswith("file:"):
        return url

    backend_root = Path(__file__).resolve().parents[1]
    normalized = (backend_root / relative_path).resolve()
    return f"{prefix}/{normalized}"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
