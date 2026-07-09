from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from app.services.agent_core.execution_target import is_remote_ssh_execution_target
from app.services.agent_core.tools.registry import AgentToolRegistry
from app.services.agent_core.tools.specs import AgentToolSpec


# The read-only fallback policy, used when a caller passes no policy at all.
DEFAULT_TOOLSET_POLICY = {"name": "default"}
# The capable, approval-gated policy new sessions start with: every registered
# tool is exposed, and the permission policy gates each side-effecting action.
EXECUTION_TOOLSET_POLICY = {"name": "execution"}
# Read-only planning policy: read/search tools plus the planning helpers
# (todo_write, ask_user, exit_plan_mode). Writes, shell, and platform mutations
# are hidden until the user approves exit_plan_mode, which flips the session to
# the execution policy.
PLAN_TOOLSET_POLICY = {"name": "plan"}

# Planning helpers exposed on top of the read-only set in plan mode.
_PLAN_EXTRA_TOOLS = frozenset({"todo_write", "ask_user", "exit_plan_mode"})
_REMOTE_SSH_TARGET_NEUTRAL_TOOLS = frozenset(
    {
        "ask_user",
        "exit_plan_mode",
        "memory.list",
        "plugins.list",
        "todo_write",
    }
)
_REMOTE_SSH_TARGET_PREFIXES = ("remote.", "skills.", "web.")


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
    ) -> list[AgentToolSpec]:
        names = self.exposed_names(
            policy=policy,
            role=role,
            execution_target=execution_target,
        )
        return [self.registry.get(name).spec for name in sorted(names)]

    def exposed_names(
        self,
        *,
        policy: dict | None,
        role: str = "orchestrator",
        execution_target: dict | str | None = None,
    ) -> set[str]:
        policy = policy or DEFAULT_TOOLSET_POLICY
        policy_name = str(policy.get("name") or "default")
        specs = self.registry.list_specs()
        read_only = {
            spec.name
            for spec in specs
            if spec.risk_level == "read" and not spec.write_scope
        }
        if role == "worker":
            # A worker subagent runs without a user watching, so interaction
            # tools (ask_user / exit_plan_mode) that would pause for input are
            # excluded — they could only deadlock the child run.
            names = {
                spec.name
                for spec in specs
                if spec.name in read_only and not spec.interaction
            }
        elif policy_name == "execution":
            names = {spec.name for spec in specs}
        elif policy_name == "plan":
            names = set(read_only) | {
                spec.name for spec in specs if spec.name in _PLAN_EXTRA_TOOLS
            }
        elif policy_name == "bio":
            names = {
                spec.name
                for spec in specs
                if spec.name.startswith(("bio.", "runs.", "workflows.", "images.", "projects."))
                and spec.risk_level == "read"
            }
        else:
            names = set(read_only)
        allowed_tools = policy.get("allowed_tools")
        if isinstance(allowed_tools, list) and allowed_tools:
            names &= {str(name) for name in allowed_tools}
        if is_remote_ssh_execution_target(execution_target):
            names &= {
                spec.name
                for spec in specs
                if _is_remote_ssh_compatible_tool(spec)
            }
        return names

    def decide(
        self,
        *,
        tool_name: str,
        policy: dict | None,
        role: str = "orchestrator",
        execution_target: dict | str | None = None,
    ) -> ToolExposureDecision:
        names = self.exposed_names(
            policy=policy,
            role=role,
            execution_target=execution_target,
        )
        if tool_name in names:
            return ToolExposureDecision(
                allowed=True,
                reasons=["tool is exposed by session toolset"],
                policy=policy or DEFAULT_TOOLSET_POLICY,
            )
        return ToolExposureDecision(
            allowed=False,
            reasons=["tool is registered but not exposed for this session"],
            policy=policy or DEFAULT_TOOLSET_POLICY,
        )


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


def encode_provider_tool_name(name: str) -> str:
    return name.replace(".", "__")


def decode_provider_tool_name(name: str) -> str:
    return name.replace("__", ".")
