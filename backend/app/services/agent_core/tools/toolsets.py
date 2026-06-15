from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from app.services.agent_core.tools.registry import AgentToolRegistry
from app.services.agent_core.tools.specs import AgentToolSpec


# The read-only fallback policy, used when a caller passes no policy at all.
DEFAULT_TOOLSET_POLICY = {"name": "default"}
# The capable, approval-gated policy new sessions start with: every registered
# tool is exposed, and the permission policy gates each side-effecting action.
EXECUTION_TOOLSET_POLICY = {"name": "execution"}


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
    ) -> list[AgentToolSpec]:
        names = self.exposed_names(policy=policy, role=role)
        return [self.registry.get(name).spec for name in sorted(names)]

    def exposed_names(self, *, policy: dict | None, role: str = "orchestrator") -> set[str]:
        policy = policy or DEFAULT_TOOLSET_POLICY
        policy_name = str(policy.get("name") or "default")
        specs = self.registry.list_specs()
        if role == "worker":
            names = {
                spec.name
                for spec in specs
                if spec.risk_level == "read" and not spec.write_scope
            }
        elif policy_name == "execution":
            names = {spec.name for spec in specs}
        elif policy_name == "bio":
            names = {
                spec.name
                for spec in specs
                if spec.name.startswith(("bio.", "runs.", "workflows.", "images.", "projects."))
                and spec.risk_level == "read"
            }
        else:
            names = {
                spec.name
                for spec in specs
                if spec.risk_level == "read" and not spec.write_scope
            }
        allowed_tools = policy.get("allowed_tools")
        if isinstance(allowed_tools, list) and allowed_tools:
            names &= {str(name) for name in allowed_tools}
        return names

    def decide(
        self,
        *,
        tool_name: str,
        policy: dict | None,
        role: str = "orchestrator",
    ) -> ToolExposureDecision:
        names = self.exposed_names(policy=policy, role=role)
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
