from app.services.agent_core.tools import build_default_tool_registry
from app.services.agent_core.tools.toolsets import ToolsetExposure


def test_default_and_plan_use_explicit_small_core_surfaces() -> None:
    exposure = ToolsetExposure(build_default_tool_registry())

    assert exposure.exposed_names(policy={"name": "default"}) == {
        "ask_user",
        "attachments.read",
        "attachments.search",
        "files.read",
        "glob",
        "grep",
        "projects.list",
        "runs.inspect",
        "skills.load",
        "web.fetch",
        "web.search",
        "workflows.inspect",
    }
    assert exposure.exposed_names(policy={"name": "plan"}) == {
        "ask_user",
        "attachments.read",
        "attachments.search",
        "exit_plan_mode",
        "files.read",
        "glob",
        "grep",
        "projects.list",
        "runs.inspect",
        "skills.load",
        "todo_write",
        "web.fetch",
        "web.search",
        "workflows.inspect",
    }


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
    assert exposure.exposed_names(
        policy={"name": "default", "allowed_tools": ["projects.list"]},
        role="worker",
        execution_target=target,
    ) == set()


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


def test_attachment_tools_are_read_only_parallel_safe_and_remote_compatible() -> None:
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
    assert {"attachments.search", "attachments.read"} <= exposed
