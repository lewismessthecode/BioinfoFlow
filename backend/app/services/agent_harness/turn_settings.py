from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class EffectiveTurnSession:
    """Session facade whose mutable settings are frozen to one started Run."""

    session: Any
    model_snapshot: dict | None
    permission_mode: str
    workspace_access: str
    environment_scope: dict
    environment_targets: dict[str, dict[str, Any]]
    settings_revision: int

    def __getattr__(self, name: str) -> Any:
        return getattr(self.session, name)


def effective_turn_session(session: Any, run: Any) -> EffectiveTurnSession:
    config = run.turn_execution_config or {}
    return EffectiveTurnSession(
        session=session,
        model_snapshot=config.get(
            "model", run.model_snapshot or session.model_snapshot
        ),
        permission_mode=str(config.get("permission_mode", session.permission_mode)),
        workspace_access=str(config.get("workspace_access", session.workspace_access)),
        environment_scope=dict(
            config.get("environment_scope")
            or getattr(session, "environment_scope", None)
            or {"mode": "auto"}
        ),
        environment_targets=dict(config.get("environment_targets") or {}),
        settings_revision=int(
            config.get("settings_revision") or getattr(session, "settings_revision", 1)
        ),
    )


__all__ = ["EffectiveTurnSession", "effective_turn_session"]
