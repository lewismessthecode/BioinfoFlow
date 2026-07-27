from app.services.agent_core.tools import build_default_tool_registry
from app.services.agent_core.tools.toolsets import (
    EXECUTION_TOOLSET_POLICY,
    ToolsetExposure,
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


def test_default_and_plan_use_explicit_small_core_surfaces() -> None:
    exposure = ToolsetExposure(build_default_tool_registry())

    assert exposure.exposed_names(policy={"name": "default"}) == {
        "ask_user",
        "projects.list",
        "runs.inspect",
        "skills.load",
        "web.search",
        "workflows.inspect",
    }
    assert exposure.exposed_names(policy={"name": "plan"}) == {
        "ask_user",
        "exit_plan_mode",
        "projects.list",
        "runs.inspect",
        "skills.load",
        "todo_write",
        "web.search",
        "workflows.inspect",
    }


def test_execution_uses_only_unnamespaced_general_purpose_tools() -> None:
    registry = build_default_tool_registry()
    exposed = ToolsetExposure(registry).exposed_names(policy={"name": "execution"})

    assert exposed == {
        "ask_user",
        "bash",
        "edit",
        "projects.list",
        "runs.inspect",
        "skills.load",
        "task",
        "todo_write",
        "web.search",
        "workflows.inspect",
        "write",
    }
    assert {"write", "edit"} <= registry.names()
    assert {"files.write", "files.edit"}.isdisjoint(registry.names())


def test_registry_resolves_historical_file_action_names_without_exposing_them() -> None:
    registry = build_default_tool_registry()

    assert registry.get("files.write") is registry.get("write")
    assert registry.get("files.edit") is registry.get("edit")
    assert {"files.write", "files.edit"}.isdisjoint(registry.names())
    assert {"files.write", "files.edit"}.isdisjoint(
        spec.name for spec in registry.list_specs()
    )


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
    retired = {
        "attachments.read",
        "attachments.search",
        "files.apply_patch",
        "files.read",
        "glob",
        "grep",
        "images.build",
        "images.delete",
        "images.get",
        "images.list",
        "images.pull",
        "web.fetch",
    }
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


def test_plan_capabilities_never_disclose_mutating_or_remote_execution_tools() -> None:
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
        "remote.exec",
    }.isdisjoint(exposed)


def test_attachment_tools_remain_registered_but_are_never_model_visible() -> None:
    registry = build_default_tool_registry()
    search = registry.get("attachments.search").spec
    read = registry.get("attachments.read").spec

    assert search.risk_level == "read"
    assert read.risk_level == "read"
    assert search.parallel_safe is True
    assert read.parallel_safe is True
    exposed = ToolsetExposure(registry).exposed_names(
        policy={"name": "execution"},
        execution_target={"type": "remote_ssh", "connection_id": "conn-1"},
    )
    assert {"attachments.search", "attachments.read"}.isdisjoint(exposed)
