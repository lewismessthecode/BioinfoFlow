from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from app.startup_logging import build_startup_summary, log_startup_summary


def _settings(tmp_path: Path):
    home = tmp_path / "bioinfoflow"
    return SimpleNamespace(
        app_name="Bioinfoflow",
        app_version="0.1.0",
        debug=False,
        repo_root=str(tmp_path / "repo"),
        bioinfoflow_home=str(home),
        bioinfoflow_home_host=str(home),
        allow_path_translation=False,
        database_url=f"sqlite+aiosqlite:///{home}/state/bioinfoflow.db",
        better_auth_db_path=str(home / "state" / "auth" / "better-auth.db"),
        resolved_auth_mode="personal",
        auth_enabled_effective=True,
        nextflow_bin="/usr/local/bin/nextflow",
        miniwdl_bin="/usr/local/bin/miniwdl",
        docker_socket="unix:///var/run/docker.sock",
        scheduler_total_slots=0,
        scheduler_max_workers=0,
        scheduler_max_concurrency=4,
        scheduler_max_queue_depth=500,
        scheduler_resource_check_enabled=True,
        scheduler_safety_cpu=2,
        scheduler_safety_memory_gb=2.0,
        scheduler_safety_disk_gb=10.0,
        agent_max_tokens=16384,
        agent_max_rounds=50,
        agent_compact_threshold=50000,
        agent_sandbox_enabled=False,
        agent_observability=True,
        langsmith_tracing=True,
        cors_origins=["http://localhost:5173"],
        cors_origin_regex=r"^https?://localhost",
        trusted_hosts=["localhost", "example.com"],
        max_upload_size_bytes=104857600,
        max_image_upload_size_bytes=524288000,
        anthropic_api_key="sk-ant-secret",
        openai_api_key="sk-openai-secret",
        gemini_api_key="",
        openrouter_api_key="",
        deepseek_api_key="",
        xai_api_key="",
        qwen_api_key="",
        kimi_api_key="",
        minimax_api_key="",
        projects_root=home / "projects",
        state_root=home / "state",
        sources_root=home / "sources",
        deliveries_root=home / "sources" / "deliveries",
        reference_root=home / "sources" / "reference",
        database_root=home / "sources" / "database",
        workflow_registry_root=home / "state" / "workflows",
        engine_cache_root=home / "state" / "engine" / "cache",
    )


def test_build_startup_summary_surfaces_operational_config_without_secrets(tmp_path):
    summary = build_startup_summary(_settings(tmp_path))

    assert summary["app"] == {
        "name": "Bioinfoflow",
        "version": "0.1.0",
        "debug": False,
    }
    assert summary["auth"] == {
        "mode": "personal",
        "enabled": True,
        "better_auth_db_path": str(
            tmp_path / "bioinfoflow" / "state" / "auth" / "better-auth.db"
        ),
    }
    assert summary["storage"]["roots"]["deliveries"].endswith("/sources/deliveries")
    assert summary["workflow_engines"]["nextflow_bin"] == "/usr/local/bin/nextflow"
    assert summary["scheduler"]["max_concurrency"] == 4
    assert summary["agent_core"]["runtime"] == "agent_core"
    assert summary["agent_core"]["model_source"] == "llm_catalog"
    assert "agent" not in summary
    assert "hermes" not in repr(summary).lower()
    assert "legacy" not in repr(summary).lower()
    assert summary["network"]["cors_origins"] == ["http://localhost:5173"]
    assert summary["uploads"]["max_file_upload_mb"] == 100
    assert summary["providers"]["anthropic_api_key"] == "set"
    assert summary["providers"]["openai_api_key"] == "set"
    assert summary["providers"]["gemini_api_key"] == "unset"
    assert "sk-ant-secret" not in repr(summary)
    assert "sk-openai-secret" not in repr(summary)


def test_log_startup_summary_emits_named_structured_event(tmp_path):
    calls: list[tuple[str, dict]] = []
    logger = SimpleNamespace(info=lambda event, **kwargs: calls.append((event, kwargs)))

    log_startup_summary(_settings(tmp_path), logger=logger)

    assert calls
    event, payload = calls[0]
    assert event == "startup.config"
    assert payload["app"]["name"] == "Bioinfoflow"
    assert payload["providers"]["anthropic_api_key"] == "set"
