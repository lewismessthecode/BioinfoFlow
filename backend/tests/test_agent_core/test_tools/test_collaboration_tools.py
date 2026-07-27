from __future__ import annotations

from app.services.agent_core.tools import build_default_tool_registry
from app.services.agent_core.tools.toolsets import ToolsetExposure


COLLABORATION_NAMES = {
    "spawn_agent",
    "send_message",
    "followup_task",
    "wait_agent",
    "list_agents",
    "interrupt_agent",
}


def test_default_registry_replaces_legacy_subagent_tools() -> None:
    registry = build_default_tool_registry()
    names = {spec.name for spec in registry.list_specs()}

    assert COLLABORATION_NAMES <= names
    assert "task" not in names
    assert "subagent.analyze" not in names


def test_root_execution_toolset_exposes_all_collaboration_tools() -> None:
    exposure = ToolsetExposure(build_default_tool_registry())

    names = exposure.exposed_names(policy={"name": "execution"})

    assert COLLABORATION_NAMES <= names


def test_child_toolset_hides_spawn_and_interaction_but_keeps_coordination() -> None:
    exposure = ToolsetExposure(build_default_tool_registry())

    names = exposure.exposed_names(
        policy={"name": "execution"},
        role="subagent",
    )

    assert "spawn_agent" not in names
    assert "ask_user" not in names
    assert "exit_plan_mode" not in names
    assert COLLABORATION_NAMES - {"spawn_agent"} <= names

    remote_names = exposure.exposed_names(
        policy={"name": "execution"},
        role="subagent",
        execution_target={"type": "remote_ssh", "connection_id": "remote-1"},
    )
    assert COLLABORATION_NAMES - {"spawn_agent"} <= remote_names
