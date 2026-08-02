"""Capability decisions shared by model exposure and tool execution.

This module deliberately consumes a fresh PermissionContext snapshot rather
than resolving session state itself. The resolver owns current environment
facts; this module owns the policy that turns those facts into capability
decisions.
"""

from __future__ import annotations

from typing import Any

from app.services.agent_core.permissions.command_risk import CommandRiskAssessment
from app.services.agent_core.permissions.risk import RiskAssessment
from app.services.agent_core.tools.registry import AgentToolRegistry
from app.services.agent_core.tools.specs import AgentToolSpec
from app.services.agent_core.tools.toolsets import (
    ToolExposureDecision,
    ToolsetExposure,
)


class CapabilityPolicy:
    """Coordinate tool exposure and concrete Plan-mode capability checks."""

    def __init__(self, registry: AgentToolRegistry):
        self.exposure = ToolsetExposure(registry)

    def exposed_specs(self, **kwargs: Any) -> list[AgentToolSpec]:
        return self.exposure.exposed_specs(**kwargs)

    def exposed_names(self, **kwargs: Any) -> set[str]:
        return self.exposure.exposed_names(**kwargs)

    def callable_names(self, **kwargs: Any) -> set[str]:
        return self.exposure.callable_names(**kwargs)

    def decide(self, **kwargs: Any) -> ToolExposureDecision:
        return self.exposure.decide(**kwargs)

    @staticmethod
    def plan_command_allowed(
        *,
        tool_name: str,
        toolset_policy: dict[str, Any],
        risk: RiskAssessment,
    ) -> bool:
        """Apply the Plan ceiling after concrete command risk is known."""
        if str(toolset_policy.get("name") or "default") != "plan":
            return True
        if tool_name not in {"bash", "remote.exec"}:
            return True
        return (
            isinstance(risk, CommandRiskAssessment)
            and risk.level in {"read", "act_low"}
            and bool(risk.effects)
            and set(risk.effects) == {"read"}
            and not risk.hard_blocked
            and not risk.requires_explicit_approval
        )


__all__ = ["CapabilityPolicy"]
