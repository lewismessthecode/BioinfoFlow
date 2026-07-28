from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from app.startup_logging import build_startup_summary, log_startup_summary
from app.services.agent_core.sandbox import SandboxAvailability


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
        agent_max_iterations=90,
        agent_compact_threshold=50000,
        agent_sandbox_enabled=False,
        agent_sandbox_fail_closed=True,
        agent_sandbox_allow_network=False,
        agent_sandbox_allow_unsandboxed=False,
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
    assert summary["agent_core"]["max_iterations"] == 90
    assert summary["agent_core"]["sandbox"] == {
        "enabled": False,
        "fail_closed": True,
        "adapter": None,
        "executable": None,
        "available": None,
        "category": None,
        "message": None,
    }
    assert "max_rounds" not in summary["agent_core"]
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


def test_build_startup_summary_reports_sandbox_probe_diagnostic(tmp_path, monkeypatch):
    source = _settings(tmp_path)
    source.agent_sandbox_enabled = True
    diagnostic = SandboxAvailability(
        adapter="bubblewrap",
        executable="/usr/bin/bwrap",
        available=False,
        failure_category="probe_exit",
        failure_message="bwrap: No permissions to create new namespace",
    )
    monkeypatch.setattr(
        "app.startup_logging.SandboxRunner.available_adapter",
        lambda _runner: None,
    )
    monkeypatch.setattr(
        "app.startup_logging.SandboxRunner.availability",
        lambda _runner: diagnostic,
    )

    summary = build_startup_summary(source)

    assert summary["agent_core"]["sandbox"] == {
        "enabled": True,
        "fail_closed": True,
        "adapter": "bubblewrap",
        "executable": "/usr/bin/bwrap",
        "available": False,
        "category": "probe_exit",
        "message": "bwrap: No permissions to create new namespace",
    }


def test_build_startup_summary_does_not_raise_when_sandbox_probe_crashes(
    tmp_path, monkeypatch
):
    source = _settings(tmp_path)
    source.agent_sandbox_enabled = True
    monkeypatch.setattr(
        "app.startup_logging.SandboxRunner.availability",
        lambda _runner: (_ for _ in ()).throw(RuntimeError("unexpected probe error")),
    )

    summary = build_startup_summary(source)

    assert summary["agent_core"]["sandbox"]["enabled"] is True
    assert summary["agent_core"]["sandbox"]["available"] is False
    assert summary["agent_core"]["sandbox"]["category"] == "probe_os_error"
    assert summary["agent_core"]["sandbox"]["message"] == "unexpected probe error"


def test_log_startup_summary_emits_named_structured_event(tmp_path):
    calls: list[tuple[str, dict]] = []
    logger = SimpleNamespace(info=lambda event, **kwargs: calls.append((event, kwargs)))

    log_startup_summary(_settings(tmp_path), logger=logger)

    assert calls
    event, payload = calls[0]
    assert event == "startup.config"
    assert payload["app"]["name"] == "Bioinfoflow"
    assert payload["providers"]["anthropic_api_key"] == "set"
