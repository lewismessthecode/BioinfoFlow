from __future__ import annotations

import pytest

from app.services.agent_harness.environment_scope import (
    EnvironmentDescriptor,
    EnvironmentSelectionError,
    EnvironmentScopeRequest,
    ResolvedEnvironmentScope,
    resolve_environment_scope,
)


def test_auto_scope_freezes_all_authorized_environments() -> None:
    authorized = [
        EnvironmentDescriptor(
            environment_id="local:primary",
            kind="local",
            display_name="Local",
        ),
        EnvironmentDescriptor(
            environment_id="ssh:opaque-7fd1",
            kind="ssh",
            display_name="GPU cluster",
        ),
    ]

    resolved = resolve_environment_scope(
        EnvironmentScopeRequest(mode="auto"),
        authorized,
    )
    authorized.clear()

    assert resolved.mode == "auto"
    assert resolved.environment_ids == ("local:primary", "ssh:opaque-7fd1")
    assert resolved.require("ssh:opaque-7fd1").display_name == "GPU cluster"
    with pytest.raises(TypeError):
        resolved.environments["ssh:opaque-7fd1"] = authorized  # type: ignore[index]


def test_manual_scope_freezes_only_the_authorized_selected_subset() -> None:
    authorized = [
        EnvironmentDescriptor("local:primary", "local", "Local"),
        EnvironmentDescriptor("ssh:alpha", "ssh", "Alpha"),
        EnvironmentDescriptor("ssh:beta", "ssh", "Beta"),
    ]

    resolved = resolve_environment_scope(
        EnvironmentScopeRequest(
            mode="manual",
            selected_environment_ids=("ssh:beta", "local:primary"),
        ),
        authorized,
    )

    assert resolved.environment_ids == ("ssh:beta", "local:primary")


def test_manual_scope_rejects_an_environment_outside_authorized_choices() -> None:
    authorized = [EnvironmentDescriptor("local:primary", "local", "Local")]

    with pytest.raises(EnvironmentSelectionError) as exc_info:
        resolve_environment_scope(
            EnvironmentScopeRequest(
                mode="manual",
                selected_environment_ids=("ssh:not-authorized",),
            ),
            authorized,
        )

    assert exc_info.value.environment_ids == ("ssh:not-authorized",)
    assert exc_info.value.code == "environment_not_authorized"


def test_resolved_scope_copies_mutable_inputs() -> None:
    local = EnvironmentDescriptor("local:primary", "local", "Local")
    source = {local.environment_id: local}

    resolved = ResolvedEnvironmentScope(mode="auto", environments=source)
    source.clear()

    assert resolved.environment_ids == ("local:primary",)
