from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from app.services.agent_core.execution_target import (
    execution_scope_allows_local,
    execution_scope_allows_remote,
    execution_scope_mode,
    is_remote_ssh_execution_target,
)
from app.services.agent_core.tools.registry import AgentToolRegistry
from app.services.agent_core.tools.specs import AgentToolSpec
from app.services.model_runtime.contracts import ToolDefinition


# The small read-only fallback policy, used when a caller passes no policy at all.
DEFAULT_TOOLSET_POLICY = {"name": "default"}
# The capable, approval-gated policy new sessions start with. Registration and
# exposure are deliberately separate: product and compatibility tools remain
# registered but are disclosed only by capability, target, or explicit allowlist.
EXECUTION_TOOLSET_POLICY = {"name": "execution"}
# Read-only planning policy: core inspection plus planning helpers. Writes and
# shell are hidden until exit_plan_mode flips the session to execution.
PLAN_TOOLSET_POLICY = {"name": "plan"}

_CORE_READ_TOOLS = frozenset(
    {
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
)
_DEFAULT_TOOLS = _CORE_READ_TOOLS | {"ask_user"}
_PLAN_TOOLS = _DEFAULT_TOOLS | {"exit_plan_mode", "todo_write"}
_EXECUTION_TOOLS = _CORE_READ_TOOLS | {
    "ask_user",
    "bash",
    "files.apply_patch",
    "task",
    "todo_write",
}

_BIOINFO_READ_TOOLS = frozenset(
    {
        "images.get",
        "images.list",
        "projects.get",
        "projects.list",
        "projects.workflows.list",
        "runs.list",
        "scheduler.resources",
        "scheduler.status",
        "workflows.list",
    }
)
_BIOINFO_MANAGE_TOOLS = frozenset(
    {
        "images.build",
        "images.delete",
        "images.pull",
        "projects.create",
        "projects.delete",
        "projects.update",
        "projects.workflows.bind",
        "projects.workflows.pin",
        "projects.workflows.unbind",
        "runs.cancel",
        "runs.cleanup",
        "runs.delete",
        "runs.resume",
        "runs.retry",
        "runs.submit",
        "workflows.create",
        "workflows.delete",
        "workflows.update",
    }
)
_REMOTE_READ_TOOLS = frozenset(
    {"remote.connections.list", "remote.list_dir", "remote.read_file"}
)
_REMOTE_EXECUTION_TOOLS = _REMOTE_READ_TOOLS | {"remote.exec"}
TOOL_CAPABILITY_BUNDLES: dict[str, frozenset[str]] = {
    "bioinfo.read": _BIOINFO_READ_TOOLS,
    "bioinfo.manage": _BIOINFO_MANAGE_TOOLS,
    "remote": _REMOTE_EXECUTION_TOOLS,
}
_REMOTE_SSH_TARGET_NEUTRAL_TOOLS = frozenset(
    {
        "ask_user",
        "exit_plan_mode",
        "memory.list",
        "plugins.list",
        "todo_write",
    }
)
_REMOTE_SSH_TARGET_PREFIXES = ("attachments.", "remote.", "skills.", "web.")
_MODEL_HIDDEN_TOOLS = frozenset(
    {
        "files.edit",
        "files.write",
        "memory.list",
        "memory.propose",
        "plugins.list",
        "runs.audit",
        "runs.dag",
        "runs.get",
        "runs.logs",
        "runs.outputs",
        "skills.list",
        "subagent.analyze",
        "workflows.dag",
        "workflows.form_spec",
        "workflows.get",
        "workflows.source",
    }
)
_BUILTIN_TOOL_NAMES = frozenset(
    _DEFAULT_TOOLS
    | _PLAN_TOOLS
    | _EXECUTION_TOOLS
    | _BIOINFO_READ_TOOLS
    | _BIOINFO_MANAGE_TOOLS
    | _REMOTE_EXECUTION_TOOLS
    | _MODEL_HIDDEN_TOOLS
)


@dataclass(frozen=True)
class ToolExposureDecision:
    allowed: bool
    reasons: list[str]
    policy: dict


class ToolsetExposure:
    def __init__(self, registry: AgentToolRegistry):
        self.registry = registry

    def exposed_specs(
        self,
        *,
        policy: dict | None,
        role: str = "orchestrator",
        execution_target: dict | str | None = None,
        execution_scope: dict | str | None = None,
    ) -> list[AgentToolSpec]:
        names = self.exposed_names(
            policy=policy,
            role=role,
            execution_target=execution_target,
            execution_scope=execution_scope,
        )
        return [self.registry.get(name).spec for name in sorted(names)]

    def exposed_names(
        self,
        *,
        policy: dict | None,
        role: str = "orchestrator",
        execution_target: dict | str | None = None,
        execution_scope: dict | str | None = None,
    ) -> set[str]:
        policy = policy or DEFAULT_TOOLSET_POLICY
        policy_name = str(policy.get("name") or "default")
        specs = self.registry.list_specs()
        registered = {spec.name for spec in specs}
        extension_tools = registered - _BUILTIN_TOOL_NAMES
        read_only = {
            spec.name
            for spec in specs
            if spec.risk_level == "read" and not spec.write_scope
        }
        allowed_tools = policy.get("allowed_tools")
        explicit_allowed = (
            {str(name) for name in allowed_tools}
            if isinstance(allowed_tools, list) and allowed_tools
            else None
        )
        if role == "worker":
            # A worker subagent runs without a user watching, so interaction
            # tools (ask_user / exit_plan_mode) that would pause for input are
            # excluded — they could only deadlock the child run.
            names = set(explicit_allowed or (_CORE_READ_TOOLS | extension_tools))
            names &= {
                spec.name for spec in specs if spec.name in read_only and not spec.interaction
            }
        elif policy_name == "execution":
            names = set(_EXECUTION_TOOLS | extension_tools)
        elif policy_name == "plan":
            names = set(_PLAN_TOOLS)
        elif policy_name == "bio":
            names = set(_CORE_READ_TOOLS | _BIOINFO_READ_TOOLS)
        else:
            names = set(_DEFAULT_TOOLS)

        if role != "worker":
            capabilities = policy.get("capabilities")
            if isinstance(capabilities, list):
                for capability in capabilities:
                    capability_tools = TOOL_CAPABILITY_BUNDLES.get(
                        str(capability), ()
                    )
                    names.update(
                        capability_tools
                        if policy_name == "execution"
                        else set(capability_tools) & read_only
                    )
            if explicit_allowed is not None:
                names = set(explicit_allowed)

        remote_target = is_remote_ssh_execution_target(execution_target)
        remote_selected = remote_target or (
            execution_scope_mode(execution_scope) == "manual"
            and execution_scope_allows_remote(execution_scope)
        )
        if remote_selected and explicit_allowed is None:
            names.update(
                _REMOTE_READ_TOOLS
                if role == "worker" or policy_name != "execution"
                else _REMOTE_EXECUTION_TOOLS
            )

        names &= registered
        names -= _MODEL_HIDDEN_TOOLS
        scope_allows_remote = execution_scope_allows_remote(execution_scope)
        remote_only_scope = (
            execution_scope is not None
            and scope_allows_remote
            and not execution_scope_allows_local(execution_scope)
        )
        if is_remote_ssh_execution_target(execution_target) or remote_only_scope:
            names &= {
                spec.name for spec in specs if _is_remote_ssh_compatible_tool(spec)
            }
        elif execution_scope is not None and not scope_allows_remote:
            names = {name for name in names if not name.startswith("remote.")}
        elif execution_target is not None and not scope_allows_remote:
            names = {name for name in names if not name.startswith("remote.")}
        return names

    def decide(
        self,
        *,
        tool_name: str,
        policy: dict | None,
        role: str = "orchestrator",
        execution_target: dict | str | None = None,
        execution_scope: dict | str | None = None,
        model_visible: bool = True,
    ) -> ToolExposureDecision:
        names = (
            self.exposed_names(
                policy=policy,
                role=role,
                execution_target=execution_target,
                execution_scope=execution_scope,
            )
            if model_visible
            else self.callable_names(
                policy=policy,
                role=role,
                execution_target=execution_target,
                execution_scope=execution_scope,
            )
        )
        if tool_name in names:
            return ToolExposureDecision(
                allowed=True,
                reasons=[
                    "tool is exposed by session toolset"
                    if model_visible
                    else "tool is callable by session toolset"
                ],
                policy=policy or DEFAULT_TOOLSET_POLICY,
            )
        return ToolExposureDecision(
            allowed=False,
            reasons=["tool is registered but not exposed for this session"],
            policy=policy or DEFAULT_TOOLSET_POLICY,
        )

    def callable_names(
        self,
        *,
        policy: dict | None,
        role: str = "orchestrator",
        execution_target: dict | str | None = None,
        execution_scope: dict | str | None = None,
    ) -> set[str]:
        """Return host-callable tools without widening model-visible schemas."""
        policy = policy or DEFAULT_TOOLSET_POLICY
        policy_name = str(policy.get("name") or "default")
        specs = self.registry.list_specs()
        read_only = {
            spec.name
            for spec in specs
            if spec.risk_level == "read" and not spec.write_scope
        }
        if role == "worker":
            names = {
                spec.name
                for spec in specs
                if spec.name in read_only and not spec.interaction
            }
        elif policy_name == "execution":
            names = {spec.name for spec in specs}
        elif policy_name == "plan":
            names = set(read_only) | {"ask_user", "exit_plan_mode", "todo_write"}
        elif policy_name == "bio":
            names = set(_CORE_READ_TOOLS | _BIOINFO_READ_TOOLS)
        else:
            names = set(read_only)

        names -= _MODEL_HIDDEN_TOOLS
        allowed_tools = policy.get("allowed_tools")
        if isinstance(allowed_tools, list) and allowed_tools:
            names &= {str(name) for name in allowed_tools}
        scope_allows_remote = execution_scope_allows_remote(execution_scope)
        remote_only_scope = (
            execution_scope is not None
            and scope_allows_remote
            and not execution_scope_allows_local(execution_scope)
        )
        if is_remote_ssh_execution_target(execution_target) or remote_only_scope:
            names &= {
                spec.name for spec in specs if _is_remote_ssh_compatible_tool(spec)
            }
        elif execution_scope is not None and not scope_allows_remote:
            names = {name for name in names if not name.startswith("remote.")}
        elif execution_target is not None and not scope_allows_remote:
            names = {name for name in names if not name.startswith("remote.")}
        return names


def _is_remote_ssh_compatible_tool(spec: AgentToolSpec) -> bool:
    if spec.name in _REMOTE_SSH_TARGET_NEUTRAL_TOOLS:
        return True
    return spec.name.startswith(_REMOTE_SSH_TARGET_PREFIXES)


def provider_tool_specs(specs: Iterable[AgentToolSpec]) -> list[dict]:
    tools: list[dict] = []
    for spec in specs:
        tools.append(
            {
                "type": "function",
                "function": {
                    "name": encode_provider_tool_name(spec.name),
                    "description": spec.description,
                    "parameters": spec.input_schema,
                },
            }
        )
    return tools


def model_tool_definitions(
    specs: Iterable[AgentToolSpec],
) -> tuple[ToolDefinition, ...]:
    return tuple(
        ToolDefinition(
            name=encode_provider_tool_name(spec.name),
            description=spec.description,
            parameters=spec.input_schema,
        )
        for spec in specs
    )


def encode_provider_tool_name(name: str) -> str:
    return name.replace(".", "__")


def decode_provider_tool_name(name: str) -> str:
    return name.replace("__", ".")
