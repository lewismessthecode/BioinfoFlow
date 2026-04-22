from __future__ import annotations

from pathlib import Path
from typing import Any

from app.services.hermes_service.home import (
    ensure_hermes_home_environment,
    resolve_hermes_state_db_path,
)
from app.utils.logging import get_logger

logger = get_logger(__name__)

ensure_hermes_home_environment()

try:  # pragma: no cover - exercised indirectly when dependency is installed
    from hermes_state import SessionDB
except Exception:  # pragma: no cover - graceful fallback in dev/test
    SessionDB = None


_SESSION_STORE: Any | None = None
_SESSION_STORES: dict[str, Any] = {}


def _resolve_state_db_path(db_path: str | Path | None = None) -> Path:
    return resolve_hermes_state_db_path(db_path)


def get_hermes_session_store(db_path: str | Path | None = None):
    if SessionDB is None:
        raise RuntimeError(
            "Hermes Agent SDK is not installed. Configure the backend dependency before enabling agent_engine=hermes_service."
        )

    resolved_path = _resolve_state_db_path(db_path)
    ensure_hermes_home_environment(state_db_path=resolved_path)
    resolved_path.parent.mkdir(parents=True, exist_ok=True)
    cache_key = str(resolved_path)

    if db_path is not None and cache_key in _SESSION_STORES:
        return _SESSION_STORES[cache_key]

    global _SESSION_STORE
    if cache_key not in _SESSION_STORES:
        logger.info("hermes.session_store.init", db_path=cache_key)
        _SESSION_STORES[cache_key] = SessionDB(resolved_path)

    if db_path is None:
        _SESSION_STORE = _SESSION_STORES[cache_key]
        return _SESSION_STORE

    return _SESSION_STORES[cache_key]
