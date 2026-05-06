from app.config import Settings
from app.scheduler.config import SchedulerConfig


def test_settings_use_root_env_when_no_backend_override(tmp_path, monkeypatch):
    root_home = (tmp_path / "root-home").resolve()
    root_env = tmp_path / "root.env"
    backend_env = tmp_path / "backend.env"
    root_env.write_text(f"BIOINFOFLOW_HOME={root_home}\n", encoding="utf-8")
    backend_env.write_text("", encoding="utf-8")

    monkeypatch.delenv("BIOINFOFLOW_HOME", raising=False)

    settings = Settings(_env_file=(root_env, backend_env))

    assert settings.bioinfoflow_home == str(root_home)


def test_settings_prefer_backend_override_over_root_env(tmp_path, monkeypatch):
    root_home = (tmp_path / "root-home").resolve()
    backend_home = (tmp_path / "backend-home").resolve()
    root_env = tmp_path / "root.env"
    backend_env = tmp_path / "backend.env"
    root_env.write_text(f"BIOINFOFLOW_HOME={root_home}\n", encoding="utf-8")
    backend_env.write_text(f"BIOINFOFLOW_HOME={backend_home}\n", encoding="utf-8")

    monkeypatch.delenv("BIOINFOFLOW_HOME", raising=False)

    settings = Settings(_env_file=(root_env, backend_env))

    assert settings.bioinfoflow_home == str(backend_home)


def test_shell_env_has_highest_precedence(tmp_path, monkeypatch):
    shell_home = (tmp_path / "shell-home").resolve()
    root_home = (tmp_path / "root-home").resolve()
    backend_home = (tmp_path / "backend-home").resolve()
    root_env = tmp_path / "root.env"
    backend_env = tmp_path / "backend.env"
    root_env.write_text(f"BIOINFOFLOW_HOME={root_home}\n", encoding="utf-8")
    backend_env.write_text(f"BIOINFOFLOW_HOME={backend_home}\n", encoding="utf-8")

    monkeypatch.setenv("BIOINFOFLOW_HOME", str(shell_home))

    settings = Settings(_env_file=(root_env, backend_env))

    assert settings.bioinfoflow_home == str(shell_home)


def test_scheduler_worker_heartbeat_grace_seconds_binds_from_env(
    tmp_path, monkeypatch
):
    root_home = (tmp_path / "root-home").resolve()
    root_env = tmp_path / "root.env"
    backend_env = tmp_path / "backend.env"
    root_env.write_text(
        f"BIOINFOFLOW_HOME={root_home}\n"
        "SCHEDULER_WORKER_HEARTBEAT_GRACE_SECONDS=5\n",
        encoding="utf-8",
    )
    backend_env.write_text("", encoding="utf-8")

    monkeypatch.delenv("BIOINFOFLOW_HOME", raising=False)
    monkeypatch.delenv("SCHEDULER_WORKER_HEARTBEAT_GRACE_SECONDS", raising=False)

    settings = Settings(_env_file=(root_env, backend_env))

    assert settings.scheduler_worker_heartbeat_grace_seconds == 5
    assert (
        SchedulerConfig.from_settings(settings).worker_heartbeat_grace_seconds
        == 5
    )
