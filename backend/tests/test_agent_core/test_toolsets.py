import pytest

from app.services.agent_core.tools import build_default_tool_registry
from app.services.agent_core.tools.registry import AgentToolRegistry
from app.services.agent_core.tools.specs import AgentToolSpec
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


class _CustomReadTool:
    spec = AgentToolSpec(
        name="custom.inspect",
        description="Inspect custom state.",
        input_schema={"type": "object", "additionalProperties": False},
        output_schema={"type": "object"},
        risk_level="read",
    )

    async def run(self, input, context):
        del input, context
        return {}


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


@pytest.mark.parametrize(
    "kwargs",
    [
        pytest.param(
            {
                "execution_scope": {
                    "mode": "manual",
                    "selected_targets": [{"type": "local"}],
                }
            },
            id="local-scope",
        ),
        pytest.param(
            {
                "execution_target": {"type": "local"},
                "execution_scope": {
                    "mode": "manual",
                    "selected_targets": [
                        {"type": "remote_ssh", "connection_id": "conn-1"}
                    ],
                },
            },
            id="remote-only-scope",
        ),
        pytest.param(
            {"execution_target": {"type": "remote_ssh", "connection_id": "conn-1"}},
            id="remote-target",
        ),
    ],
)
def test_plan_model_visible_and_host_callable_static_surfaces_match(
    kwargs: dict,
) -> None:
    exposure = ToolsetExposure(build_default_tool_registry())
    kwargs = {"policy": {"name": "plan"}, **kwargs}

    assert exposure.exposed_names(**kwargs) == exposure.callable_names(**kwargs)


@pytest.mark.parametrize("include_custom", [False, True])
def test_plan_surfaces_include_only_registered_tools(include_custom: bool) -> None:
    registry = AgentToolRegistry()
    if include_custom:
        registry.register(_CustomReadTool())
    exposure = ToolsetExposure(registry)
    kwargs = {
        "policy": {"name": "plan"},
        "execution_scope": {
            "mode": "manual",
            "selected_targets": [{"type": "local"}],
        },
    }

    expected = {"custom.inspect"} if include_custom else set()

    assert exposure.exposed_names(**kwargs) == expected
    assert exposure.callable_names(**kwargs) == expected


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


def test_plan_and_execution_tool_schemas_keep_stable_shared_prefix() -> None:
    exposure = ToolsetExposure(build_default_tool_registry())
    execution_scope = {
        "mode": "manual",
        "selected_targets": [{"type": "local"}],
    }

    plan_specs = exposure.exposed_specs(
        policy={"name": "plan"},
        execution_scope=execution_scope,
    )
    execution_specs = exposure.exposed_specs(
        policy=EXECUTION_TOOLSET_POLICY,
        execution_scope=execution_scope,
    )
    shared_names = {spec.name for spec in plan_specs} & {
        spec.name for spec in execution_specs
    }
    plan_shared = [spec for spec in plan_specs if spec.name in shared_names]
    execution_shared = [spec for spec in execution_specs if spec.name in shared_names]

    assert plan_shared == execution_shared
    assert plan_specs[: len(plan_shared)] == plan_shared
    assert execution_specs[: len(execution_shared)] == execution_shared
    assert {spec.name for spec in plan_specs[len(plan_shared) :]} == {"exit_plan_mode"}
    assert execution_specs[len(execution_shared) :]


def test_exposed_specs_order_is_independent_of_registry_registration_order() -> None:
    default_registry = build_default_tool_registry()
    reversed_registry = AgentToolRegistry()
    for name in reversed(sorted(default_registry.names())):
        reversed_registry.register(default_registry.get(name))
    execution_scope = {
        "mode": "manual",
        "selected_targets": [{"type": "local"}],
    }

    for policy in ({"name": "plan"}, EXECUTION_TOOLSET_POLICY):
        default_specs = ToolsetExposure(default_registry).exposed_specs(
            policy=policy,
            execution_scope=execution_scope,
        )
        reversed_specs = ToolsetExposure(reversed_registry).exposed_specs(
            policy=policy,
            execution_scope=execution_scope,
        )

        assert default_specs == reversed_specs


def test_remote_subagent_plan_and_execution_keep_stable_shared_prefix() -> None:
    exposure = ToolsetExposure(build_default_tool_registry())
    kwargs = {
        "role": "subagent",
        "execution_target": {
            "type": "remote_ssh",
            "connection_id": "conn-1",
        },
    }

    plan_specs = exposure.exposed_specs(policy={"name": "plan"}, **kwargs)
    execution_specs = exposure.exposed_specs(policy={"name": "execution"}, **kwargs)
    shared_names = {spec.name for spec in plan_specs} & {
        spec.name for spec in execution_specs
    }
    plan_shared = [spec for spec in plan_specs if spec.name in shared_names]
    execution_shared = [spec for spec in execution_specs if spec.name in shared_names]

    assert plan_shared == execution_shared
    assert plan_specs == plan_shared
    assert execution_specs[: len(execution_shared)] == execution_shared
    assert {"remote.connections.list", "remote.list_dir", "remote.read_file"} <= {
        spec.name for spec in plan_shared
    }


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


def test_subagent_execution_explicit_allowlist_matches_callable_surface() -> None:
    exposure = ToolsetExposure(build_default_tool_registry())
    kwargs = {
        "policy": {"name": "execution", "allowed_tools": ["runs.submit"]},
        "role": "subagent",
    }

    assert exposure.exposed_names(**kwargs) == {"runs.submit"}
    assert exposure.callable_names(**kwargs) == {"runs.submit"}


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
