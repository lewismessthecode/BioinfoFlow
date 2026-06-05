from __future__ import annotations

from app.services.agent_core.permissions.policy import PermissionPolicy
from app.services.agent_core.permissions.risk import RiskAssessment


def test_guarded_auto_allows_low_risk_actions() -> None:
    decision = PermissionPolicy().decide(
        risk=RiskAssessment(level="act_low", reasons=["declared"]),
        permission_mode="guarded_auto",
        automation_mode="assisted",
    )

    assert decision.decision == "allow"


def test_guarded_auto_asks_for_high_risk_actions() -> None:
    decision = PermissionPolicy().decide(
        risk=RiskAssessment(level="act_high", reasons=["declared"]),
        permission_mode="guarded_auto",
        automation_mode="assisted",
    )

    assert decision.decision == "ask"


def test_advise_only_denies_side_effects() -> None:
    decision = PermissionPolicy().decide(
        risk=RiskAssessment(level="act_low", reasons=["declared"]),
        permission_mode="bypass",
        automation_mode="advise_only",
    )

    assert decision.decision == "deny"


def test_critical_actions_are_hard_blocked_even_in_bypass() -> None:
    decision = PermissionPolicy().decide(
        risk=RiskAssessment(level="critical", reasons=["declared"]),
        permission_mode="bypass",
        automation_mode="autonomous",
    )

    assert decision.decision == "deny"
