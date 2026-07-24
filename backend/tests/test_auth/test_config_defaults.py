import pytest

from app.config import Settings


def test_auth_mode_defaults_to_dev_for_local_first_run(monkeypatch) -> None:
    monkeypatch.delenv("AUTH_MODE", raising=False)
    monkeypatch.delenv("AUTH_ENABLED", raising=False)
    settings = Settings(_env_file=None)

    assert settings.resolved_auth_mode == "dev"
    assert settings.auth_enabled_effective is False


def test_legacy_auth_enabled_true_maps_to_personal_mode() -> None:
    settings = Settings(auth_mode="", auth_enabled=True)

    assert settings.resolved_auth_mode == "personal"
    assert settings.auth_enabled_effective is True


def test_better_auth_db_path_defaults_to_state_auth_db() -> None:
    settings = Settings(_env_file=None)

    assert settings.better_auth_db_path.endswith("/data/state/auth/better-auth.db")


def test_legacy_auth_enabled_false_maps_to_dev_mode() -> None:
    settings = Settings(auth_mode="", auth_enabled=False)

    assert settings.resolved_auth_mode == "dev"
    assert settings.auth_enabled_effective is False


def test_explicit_auth_mode_wins_over_legacy_auth_enabled() -> None:
    settings = Settings(auth_mode="team", auth_enabled=False)

    assert settings.resolved_auth_mode == "team"
    assert settings.auth_enabled_effective is True


def test_invalid_auth_mode_is_rejected() -> None:
    with pytest.raises(ValueError, match="AUTH_MODE must be one of"):
        Settings(auth_mode="personl")


def test_relative_sqlite_database_url_is_resolved_to_backend_root() -> None:
    settings = Settings(
        _env_file=None,
        database_url="sqlite+aiosqlite:///./bioinfoflow.db",
    )

    assert settings.database_url.startswith("sqlite+aiosqlite:////")
    assert settings.database_url.endswith("/backend/bioinfoflow.db")


def test_legacy_hermes_agent_settings_are_ignored() -> None:
    settings = Settings(
        _env_file=None,
        agent_hermes_home="~/bioinfoflow-home/hermes-managed",
        agent_hermes_state_db="~/bioinfoflow-home/custom-hermes/runtime.db",
        agent_engine="hermes_service",
        agent_hermes_max_concurrency=12,
    )

    assert not hasattr(settings, "agent_hermes_home")
    assert not hasattr(settings, "agent_hermes_state_db")
    assert not hasattr(settings, "agent_engine")
    assert not hasattr(settings, "agent_hermes_max_concurrency")
