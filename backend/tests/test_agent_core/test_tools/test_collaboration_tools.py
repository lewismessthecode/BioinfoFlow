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


def test_task4_collaboration_tools_have_precise_model_visible_contracts() -> None:
    registry = build_default_tool_registry()

    spawn = registry.get("spawn_agent").spec
    assert spawn.write_scope == [
        "agent_sessions",
        "agent_turns",
        "agent_messages",
        "agent_attachments",
    ]

    send = registry.get("send_message").spec
    assert send.input_schema["required"] == ["target", "message"]
    assert send.write_scope == ["agent_messages"]

    followup = registry.get("followup_task").spec
    assert followup.input_schema["required"] == ["target", "message"]
    assert followup.write_scope == [
        "agent_messages",
        "agent_turns",
        "agent_sessions",
    ]

    wait = registry.get("wait_agent").spec
    assert wait.input_schema["required"] == []
    assert wait.input_schema["properties"]["timeout_ms"] == {
        "type": "integer",
        "minimum": 0,
        "maximum": 60000,
        "default": 30000,
    }
    assert wait.risk_level == "act_low"
    assert wait.write_scope == ["agent_sessions"]

    interrupt = registry.get("interrupt_agent").spec
    assert interrupt.input_schema["required"] == ["target"]
    assert interrupt.write_scope == ["agent_turns", "agent_sessions"]
