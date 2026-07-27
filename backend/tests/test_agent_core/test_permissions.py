from __future__ import annotations

import pytest

from app.services.agent_core.permissions.command_risk import CommandRiskAssessment
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


def test_bypass_allows_risk_that_normally_requires_explicit_approval() -> None:
    decision = PermissionPolicy().decide(
        risk=RiskAssessment(
            level="act_high",
            reasons=["indirect shell execution"],
            requires_explicit_approval=True,
        ),
        permission_mode="bypass",
        automation_mode="autonomous",
    )

    assert decision.decision == "allow"


def test_critical_actions_require_approval_even_in_bypass() -> None:
    decision = PermissionPolicy().decide(
        risk=RiskAssessment(level="critical", reasons=["declared"]),
        permission_mode="bypass",
        automation_mode="autonomous",
    )

    assert decision.decision == "ask"


@pytest.mark.parametrize(
    "permission_mode", ["ask_each_action", "guarded_auto", "bypass"]
)
def test_hard_blocked_actions_are_denied_in_every_permission_mode(
    permission_mode,
) -> None:
    decision = PermissionPolicy().decide(
        risk=CommandRiskAssessment(
            level="act_low",
            reasons=["authorization boundary mismatch"],
            hard_blocked=True,
        ),
        permission_mode=permission_mode,
        automation_mode="autonomous",
    )

    assert decision.decision == "deny"
