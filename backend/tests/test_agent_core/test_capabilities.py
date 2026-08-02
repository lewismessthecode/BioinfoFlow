from app.services.agent_core.permissions.capabilities import CapabilityPolicy
from app.services.agent_core.permissions.command_risk import CommandRiskAssessment
from app.services.agent_core.tools import build_default_tool_registry


def test_capability_policy_preserves_plan_exposure_and_callable_surface() -> None:
    policy = CapabilityPolicy(build_default_tool_registry())
    kwargs = {
        "policy": {"name": "plan"},
        "execution_scope": {
            "mode": "manual",
            "selected_targets": [{"type": "local"}],
        },
    }

    assert policy.exposed_names(**kwargs) == policy.callable_names(**kwargs)


def test_capability_policy_applies_plan_command_ceiling() -> None:
    read_risk = CommandRiskAssessment(level="read", effects=["read"])
    write_risk = CommandRiskAssessment(level="act_low", effects=["write"])

    assert CapabilityPolicy.plan_command_allowed(
        tool_name="bash",
        toolset_policy={"name": "plan"},
        risk=read_risk,
    )
    assert not CapabilityPolicy.plan_command_allowed(
        tool_name="bash",
        toolset_policy={"name": "plan"},
        risk=write_risk,
    )
    assert CapabilityPolicy.plan_command_allowed(
        tool_name="bash",
        toolset_policy={"name": "execution"},
        risk=write_risk,
    )
