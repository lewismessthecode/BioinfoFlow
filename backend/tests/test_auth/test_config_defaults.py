from app.config import Settings


def test_auth_mode_defaults_to_personal(monkeypatch) -> None:
    monkeypatch.delenv("AUTH_MODE", raising=False)
    monkeypatch.delenv("AUTH_ENABLED", raising=False)
    settings = Settings(_env_file=None)

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


def test_relative_sqlite_database_url_is_resolved_to_backend_root() -> None:
    settings = Settings(
        _env_file=None,
        database_url="sqlite+aiosqlite:///./bioinfoflow.db",
    )

    assert settings.database_url.startswith("sqlite+aiosqlite:////")
    assert settings.database_url.endswith("/backend/bioinfoflow.db")


def test_hermes_home_derives_state_db_when_state_db_is_unset() -> None:
    settings = Settings(
        _env_file=None,
        agent_hermes_home="~/bioinfoflow-home/hermes-managed",
        agent_hermes_state_db="",
    )

    assert settings.agent_hermes_home.endswith("/bioinfoflow-home/hermes-managed")
    assert settings.agent_hermes_state_db.endswith(
        "/bioinfoflow-home/hermes-managed/state.db"
    )


def test_explicit_hermes_state_db_becomes_the_managed_home_root() -> None:
    settings = Settings(
        _env_file=None,
        agent_hermes_home="~/ignored-home",
        agent_hermes_state_db="~/bioinfoflow-home/custom-hermes/runtime.db",
    )

    assert settings.agent_hermes_home.endswith("/bioinfoflow-home/custom-hermes")
    assert settings.agent_hermes_state_db.endswith(
        "/bioinfoflow-home/custom-hermes/runtime.db"
    )
