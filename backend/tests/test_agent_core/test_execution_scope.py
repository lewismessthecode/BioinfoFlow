import pytest

from app.services.agent_core.execution_target import (
    normalize_execution_target,
    normalize_execution_scope,
    selected_remote_connection_ids_from_policy,
    session_metadata_with_execution_scope,
)
from app.services.agent_core.tools import build_default_tool_registry
from app.services.agent_core.tools.toolsets import ToolsetExposure
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


def test_execution_scope_overrides_stale_legacy_target_metadata():
    metadata = {
        "remote_connection_id": "conn-stale",
        "execution_target": {
            "type": "remote_ssh",
            "connection_id": "conn-stale",
        },
        "execution_scope": {"mode": "auto"},
    }

    assert normalize_execution_target(None, metadata=metadata) == {"type": "local"}
    assert selected_remote_connection_ids_from_policy(metadata) == []
    assert (
        selected_remote_connection_ids_from_policy(
            {
                "execution_scope": "auto",
                "execution_target": {
                    "type": "remote_ssh",
                    "connection_id": "conn-stale",
                },
            }
        )
        == []
    )


def test_manual_multi_scope_does_not_fall_back_to_stale_remote_alias():
    metadata = {
        "remote_connection_id": "conn-stale",
        "execution_target": {
            "type": "remote_ssh",
            "connection_id": "conn-stale",
        },
        "execution_scope": {
            "mode": "manual",
            "selected_targets": [
                {"type": "local"},
                {"type": "remote_ssh", "connection_id": "conn-selected"},
            ],
        },
    }

    assert normalize_execution_target(None, metadata=metadata) == {"type": "local"}
    assert selected_remote_connection_ids_from_policy(metadata) == ["conn-selected"]


def test_manual_remote_only_multi_scope_exposes_only_remote_compatible_tools():
    names = ToolsetExposure(build_default_tool_registry()).exposed_names(
        policy={"name": "execution"},
        execution_target={"type": "local"},
        execution_scope={
            "mode": "manual",
            "selected_targets": [
                {"type": "remote_ssh", "connection_id": "conn-a"},
                {"type": "remote_ssh", "connection_id": "conn-b"},
            ],
        },
    )

    assert "remote.exec" in names
    assert "remote.read_file" in names
    assert "bash" not in names
    assert "files.write" not in names


def test_remote_connection_discovery_is_exposed_for_auto_and_manual_remote_scopes():
    exposure = ToolsetExposure(build_default_tool_registry())

    auto_names = exposure.exposed_names(
        policy={"name": "execution"},
        execution_scope={"mode": "auto"},
    )
    manual_names = exposure.exposed_names(
        policy={"name": "execution"},
        execution_scope={
            "mode": "manual",
            "selected_targets": [
                {"type": "remote_ssh", "connection_id": "conn-selected"}
            ],
        },
    )

    assert "remote.connections.list" in auto_names
    assert "remote.connections.list" in manual_names


def test_manual_local_only_scope_hides_all_remote_tools():
    names = ToolsetExposure(build_default_tool_registry()).exposed_names(
        policy={"name": "execution"},
        execution_scope={
            "mode": "manual",
            "selected_targets": [{"type": "local"}],
        },
    )

    assert not {name for name in names if name.startswith("remote.")}
