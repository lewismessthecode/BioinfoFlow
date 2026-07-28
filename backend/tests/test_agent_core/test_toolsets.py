import pytest

from app.services.agent_core.tools import build_default_tool_registry
from app.services.agent_core.tools.toolsets import (
    EXECUTION_TOOLSET_POLICY,
    ToolsetExposure,
)
from app.utils.exceptions import NotFoundError


RETIRED_AGENT_TOOL_NAMES = frozenset(
    {
        "attachments.read",
        "attachments.search",
        "files.apply_patch",
        "files.edit",
        "files.read",
        "files.write",
        "glob",
        "grep",
        "images.build",
        "images.delete",
        "images.get",
        "images.list",
        "images.pull",
    }
)


def test_canonical_execution_policy_exposes_platform_lifecycle_tools() -> None:
    assert EXECUTION_TOOLSET_POLICY == {
        "name": "execution",
        "capabilities": ["bioinfo.read", "bioinfo.manage"],
    }

    exposed = ToolsetExposure(build_default_tool_registry()).exposed_names(
        policy=EXECUTION_TOOLSET_POLICY
    )

    assert {
        "workflows.create",
        "projects.workflows.bind",
        "runs.submit",
        "runs.inspect",
        "workflows.inspect",
    } <= exposed


def test_default_uses_explicit_small_core_surface() -> None:
    exposure = ToolsetExposure(build_default_tool_registry())

    assert exposure.exposed_names(policy={"name": "default"}) == {
        "ask_user",
        "projects.list",
        "runs.inspect",
        "skills.load",
        "web.search",
        "workflows.inspect",
    }


def test_plan_derives_registered_read_platform_surface() -> None:
    exposure = ToolsetExposure(build_default_tool_registry())

    exposed = exposure.exposed_names(
        policy={"name": "plan"},
        execution_scope={
            "mode": "manual",
            "selected_targets": [{"type": "local"}],
        },
    )

    assert {
        "ask_user",
        "bash",
        "exit_plan_mode",
        "projects.get",
        "projects.list",
        "projects.workflows.list",
        "runs.inspect",
        "runs.list",
        "scheduler.resources",
        "scheduler.status",
        "skills.load",
        "web.search",
        "workflows.inspect",
        "workflows.list",
    } <= exposed
    assert {
        "edit",
        "followup_task",
        "interrupt_agent",
        "memory.propose",
        "runs.submit",
        "send_message",
        "spawn_agent",
        "todo_write",
        "write",
    }.isdisjoint(exposed)


def test_plan_model_visible_and_host_callable_static_surfaces_match() -> None:
    exposure = ToolsetExposure(build_default_tool_registry())
    kwargs = {
        "policy": {"name": "plan"},
        "execution_scope": {
            "mode": "manual",
            "selected_targets": [{"type": "local"}],
        },
    }

    assert exposure.exposed_names(**kwargs) == exposure.callable_names(**kwargs)


@pytest.mark.parametrize("role", ["worker", "subagent"])
def test_plan_keeps_worker_surfaces_narrow_and_static(role: str) -> None:
    exposure = ToolsetExposure(build_default_tool_registry())
    kwargs = {
        "policy": {"name": "plan"},
        "role": role,
        "execution_scope": {
            "mode": "manual",
            "selected_targets": [{"type": "local"}],
        },
    }

    exposed = exposure.exposed_names(**kwargs)

    assert exposed == exposure.callable_names(**kwargs)
    assert "scheduler.status" not in exposed
    assert "bash" not in exposed
    assert {
        "followup_task",
        "interrupt_agent",
        "send_message",
        "todo_write",
    }.isdisjoint(exposed)


def test_exposed_specs_hide_skill_loader_when_no_skills_are_available() -> None:
    exposure = ToolsetExposure(build_default_tool_registry())

    specs = exposure.exposed_specs(
        policy={"name": "default"},
        skills_available=False,
    )

    assert "skills.load" not in {spec.name for spec in specs}
    assert "skills.load" in exposure.exposed_names(policy={"name": "default"})


def test_exposed_specs_keep_skill_loader_when_skills_are_available() -> None:
    specs = ToolsetExposure(build_default_tool_registry()).exposed_specs(
        policy={"name": "default"},
        skills_available=True,
    )

    assert "skills.load" in {spec.name for spec in specs}


def test_execution_uses_only_unnamespaced_general_purpose_tools() -> None:
    registry = build_default_tool_registry()
    exposed = ToolsetExposure(registry).exposed_names(policy={"name": "execution"})

    assert exposed == {
        "ask_user",
        "bash",
        "edit",
        "followup_task",
        "interrupt_agent",
        "list_agents",
        "projects.list",
        "runs.inspect",
        "send_message",
        "skills.load",
        "spawn_agent",
        "todo_write",
        "wait_agent",
        "web.search",
        "workflows.inspect",
        "write",
    }
    assert {"write", "edit"} <= registry.names()
    assert {"files.write", "files.edit"}.isdisjoint(registry.names())


def test_registry_rejects_retired_file_action_aliases() -> None:
    registry = build_default_tool_registry()

    with pytest.raises(NotFoundError, match="Agent tool not found: files.write"):
        registry.get("files.write")
    with pytest.raises(NotFoundError, match="Agent tool not found: files.edit"):
        registry.get("files.edit")
    assert RETIRED_AGENT_TOOL_NAMES.isdisjoint(registry.names())


def test_capability_bundles_progressively_disclose_registered_tools() -> None:
    registry = build_default_tool_registry()
    exposure = ToolsetExposure(registry)

    base = exposure.exposed_names(policy={"name": "execution"})
    bioinfo_read = exposure.exposed_names(
        policy={"name": "execution", "capabilities": ["bioinfo.read"]}
    )
    bioinfo_manage = exposure.exposed_names(
        policy={"name": "execution", "capabilities": ["bioinfo.manage"]}
    )
    remote = exposure.exposed_names(
        policy={"name": "execution", "capabilities": ["remote"]}
    )

    assert {"projects.get", "runs.list", "scheduler.status"} <= bioinfo_read - base
    assert {"projects.create", "runs.submit", "workflows.update"} <= (
        bioinfo_manage - base
    )
    assert {"remote.connections.list", "remote.exec", "remote.read_file"} <= (
        remote - base
    )
    assert bioinfo_read | bioinfo_manage | remote <= registry.names()


def test_explicit_allowed_tools_remains_an_authoritative_compatibility_path() -> None:
    exposed = ToolsetExposure(build_default_tool_registry()).exposed_names(
        policy={
            "name": "execution",
            "allowed_tools": ["projects.create", "runs.submit"],
        }
    )

    assert exposed == {"projects.create", "runs.submit"}


def test_retired_model_tools_cannot_be_revived_by_any_exposure_path() -> None:
    exposure = ToolsetExposure(build_default_tool_registry())
    retired = RETIRED_AGENT_TOOL_NAMES | {"web.fetch"}
    policies = (
        {"name": "default", "allowed_tools": sorted(retired)},
        {"name": "plan", "capabilities": ["bioinfo.read", "bioinfo.manage"]},
        {
            "name": "execution",
            "capabilities": ["bioinfo.read", "bioinfo.manage", "remote"],
        },
    )

    for policy in policies:
        assert retired.isdisjoint(exposure.exposed_names(policy=policy))

    assert retired.isdisjoint(
        exposure.exposed_names(
            policy={"name": "execution", "allowed_tools": sorted(retired)},
            role="worker",
        )
    )
    assert retired.isdisjoint(
        exposure.exposed_names(
            policy={"name": "execution"},
            execution_target={"type": "remote_ssh", "connection_id": "conn-1"},
        )
    )


def test_remote_target_never_widens_explicit_allowed_tools() -> None:
    exposure = ToolsetExposure(build_default_tool_registry())
    target = {"type": "remote_ssh", "connection_id": "conn-1"}

    assert exposure.exposed_names(
        policy={"name": "execution", "allowed_tools": ["remote.read_file"]},
        execution_target=target,
    ) == {"remote.read_file"}
    assert exposure.exposed_names(
        policy={"name": "default", "allowed_tools": ["remote.read_file"]},
        role="worker",
        execution_target=target,
    ) == {"remote.read_file"}
    assert (
        exposure.exposed_names(
            policy={"name": "default", "allowed_tools": ["projects.list"]},
            role="worker",
            execution_target=target,
        )
        == set()
    )


def test_plan_capabilities_never_disclose_mutating_tools() -> None:
    exposed = ToolsetExposure(build_default_tool_registry()).exposed_names(
        policy={
            "name": "plan",
            "capabilities": ["bioinfo.read", "bioinfo.manage", "remote"],
        }
    )

    assert {"projects.get", "runs.list", "remote.read_file"} <= exposed
    assert {
        "projects.delete",
        "runs.submit",
        "workflows.update",
    }.isdisjoint(exposed)


def test_retired_agent_tools_are_not_registered() -> None:
    registry = build_default_tool_registry()

    assert RETIRED_AGENT_TOOL_NAMES.isdisjoint(registry.names())
