import pytest

from app.services.agent_core.execution_target import (
    normalize_execution_scope,
    selected_remote_connection_ids_from_policy,
    session_metadata_with_execution_scope,
)
from app.utils.exceptions import BadRequestError


def test_normalize_auto_execution_scope_keeps_scope_unexpanded():
    assert normalize_execution_scope({"mode": "auto"}) == {"mode": "auto"}


def test_normalize_manual_execution_scope_accepts_local_and_remote_targets():
    assert normalize_execution_scope(
        {
            "mode": "manual",
            "selected_targets": [
                {"kind": "local"},
                {"kind": "remote_ssh", "remote_connection_id": "conn-1"},
                {"type": "remote", "connection_id": "conn-1"},
                {"type": "remote_ssh", "connection_id": "conn-2"},
            ],
        }
    ) == {
        "mode": "manual",
        "selected_targets": [
            {"type": "local"},
            {"type": "remote_ssh", "connection_id": "conn-1"},
            {"type": "remote_ssh", "connection_id": "conn-2"},
        ],
    }


def test_manual_execution_scope_requires_at_least_one_target():
    with pytest.raises(BadRequestError, match="selected_targets"):
        normalize_execution_scope({"mode": "manual", "selected_targets": []})


def test_manual_execution_scope_rejects_remote_without_connection_id():
    with pytest.raises(BadRequestError, match="connection_id"):
        normalize_execution_scope(
            {"mode": "manual", "selected_targets": [{"type": "remote_ssh"}]}
        )


def test_session_metadata_with_execution_scope_preserves_existing_target():
    metadata = session_metadata_with_execution_scope(
        {"execution_target": {"type": "remote_ssh", "connection_id": "conn-active"}},
        {
            "mode": "manual",
            "selected_targets": [
                {"type": "local"},
                {"type": "remote_ssh", "connection_id": "conn-1"},
            ],
        },
    )

    assert metadata == {
        "execution_target": {"type": "remote_ssh", "connection_id": "conn-active"},
        "execution_scope": {
            "mode": "manual",
            "selected_targets": [
                {"type": "local"},
                {"type": "remote_ssh", "connection_id": "conn-1"},
            ],
        },
    }


def test_selected_remote_connection_ids_includes_manual_scope_targets():
    assert selected_remote_connection_ids_from_policy(
        {
            "execution_scope": {
                "mode": "manual",
                "selected_targets": [
                    {"type": "local"},
                    {"type": "remote_ssh", "connection_id": "conn-1"},
                    {"type": "remote_ssh", "connection_id": "conn-2"},
                ],
            },
        }
    ) == ["conn-1", "conn-2"]
