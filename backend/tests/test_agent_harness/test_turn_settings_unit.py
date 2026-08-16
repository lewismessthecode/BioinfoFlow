from __future__ import annotations

from types import SimpleNamespace

from app.services.agent_harness.turn_settings import effective_turn_session


def test_effective_turn_session_uses_run_snapshot_after_session_changes() -> None:
    session = SimpleNamespace(
        id="session-1",
        model_snapshot={"model": "new"},
        permission_mode="full_access",
        workspace_access="read_write",
        environment_scope={"mode": "manual", "environment_ids": ["remote-2"]},
        settings_revision=4,
    )
    run = SimpleNamespace(
        model_snapshot={"model": "old"},
        turn_execution_config={
            "settings_revision": 3,
            "model": {"model": "old"},
            "permission_mode": "ask_dangerous",
            "workspace_access": "read_only",
            "environment_scope": {
                "mode": "manual",
                "environment_ids": ["remote-1"],
            },
        },
    )

    effective = effective_turn_session(session, run)

    assert effective.id == "session-1"
    assert effective.model_snapshot == {"model": "old"}
    assert effective.permission_mode == "ask_dangerous"
    assert effective.workspace_access == "read_only"
    assert effective.environment_scope == {
        "mode": "manual",
        "environment_ids": ["remote-1"],
    }
    assert effective.settings_revision == 3
