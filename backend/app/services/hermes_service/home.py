from __future__ import annotations

import os
import sys
from pathlib import Path

from app.config import settings

_MANAGED_DIR_NAMES = ("sessions", "logs", "cache", "memories")


def _resolve_path(value: str | Path) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = (Path(settings.repo_root) / path).resolve()
    return path


def resolve_hermes_home_path(home_path: str | Path | None = None) -> Path:
    return _resolve_path(home_path or settings.agent_hermes_home)


def resolve_hermes_state_db_path(db_path: str | Path | None = None) -> Path:
    return _resolve_path(db_path or settings.agent_hermes_state_db)


def _sync_loaded_hermes_modules(*, home: Path, state_db: Path) -> None:
    hermes_state_module = sys.modules.get("hermes_state")
    if hermes_state_module is not None:
        setattr(hermes_state_module, "DEFAULT_DB_PATH", state_db)

    run_agent_module = sys.modules.get("run_agent")
    if run_agent_module is not None:
        setattr(run_agent_module, "_hermes_home", home)


def ensure_hermes_home_environment(
    *,
    home_path: str | Path | None = None,
    state_db_path: str | Path | None = None,
) -> Path:
    if state_db_path is not None:
        resolved_state_db = resolve_hermes_state_db_path(state_db_path)
        resolved_home = resolved_state_db.parent
    else:
        resolved_home = resolve_hermes_home_path(home_path)
        resolved_state_db = resolve_hermes_state_db_path(resolved_home / "state.db")

    resolved_home.mkdir(parents=True, exist_ok=True)
    for dirname in _MANAGED_DIR_NAMES:
        (resolved_home / dirname).mkdir(parents=True, exist_ok=True)

    os.environ["HERMES_HOME"] = str(resolved_home)
    _sync_loaded_hermes_modules(home=resolved_home, state_db=resolved_state_db)
    return resolved_home
