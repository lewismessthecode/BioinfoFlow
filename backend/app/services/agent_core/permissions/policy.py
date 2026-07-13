from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.services.agent_core.permissions.risk import RiskAssessment, RiskLevel


Decision = Literal["allow", "ask", "deny"]
PermissionMode = Literal["ask_each_action", "guarded_auto", "bypass"]
AutomationMode = Literal["advise_only", "assisted", "autonomous"]


@dataclass(frozen=True)
class PermissionDecision:
    decision: Decision
    reasons: list[str]
    risk_level: RiskLevel

    def as_dict(self) -> dict:
        return {
            "decision": self.decision,
            "reasons": self.reasons,
            "risk_level": self.risk_level,
        }


class PermissionPolicy:
    def decide(
        self,
        *,
        risk: RiskAssessment,
        permission_mode: PermissionMode,
        automation_mode: AutomationMode,
    ) -> PermissionDecision:
        if risk.level == "critical" or getattr(risk, "hard_blocked", False):
            return PermissionDecision(
                decision="deny",
                reasons=[*risk.reasons, "hard-blocked actions cannot be approved"],
                risk_level=risk.level,
            )

        if automation_mode == "advise_only" and risk.level != "read":
            return PermissionDecision(
                decision="deny",
                reasons=["advise_only mode blocks side effects"],
                risk_level=risk.level,
            )

        if risk.requires_explicit_approval:
            return PermissionDecision(
                decision="ask",
                reasons=[*risk.reasons, "risk assessment requires explicit approval"],
                risk_level=risk.level,
            )

        if permission_mode == "ask_each_action" and risk.level != "read":
            return PermissionDecision(
                decision="ask",
                reasons=["ask_each_action requires approval for side effects"],
                risk_level=risk.level,
            )

        if permission_mode == "bypass":
            return PermissionDecision(
                decision="allow",
                reasons=["bypass mode allows non-critical actions"],
                risk_level=risk.level,
            )

        if risk.level in {"read", "act_low"}:
            return PermissionDecision(
                decision="allow",
                reasons=["guarded_auto allows read and low-risk actions"],
                risk_level=risk.level,
            )

        return PermissionDecision(
            decision="ask",
            reasons=["guarded_auto requires approval for elevated risk"],
            risk_level=risk.level,
        )
