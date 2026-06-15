from __future__ import annotations

from typing import Any

from app.services.agent_core.tools.specs import AgentToolContext, AgentToolSpec


class ExitPlanModeTool:
    """Present a plan and ask the user to approve switching from plan to act.

    This is an interaction tool (``interaction="plan_approval"``): it pauses the
    turn for the user. When the user approves, the service flips the session's
    toolset from the read-only ``plan`` policy to ``execution`` before resuming,
    so the agent gains write/exec/platform-mutation tools on the next round.
    Only call this once you have a concrete plan and are ready to implement it.
    """

    spec = AgentToolSpec(
        name="exit_plan_mode",
        description=(
            "Present your implementation plan and ask the user to approve moving "
            "from read-only planning into acting. Call this only when you have a "
            "concrete plan and are ready to make changes."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "plan": {"type": "string", "minLength": 1},
            },
            "required": ["plan"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {"approved": {"type": "boolean"}},
            "required": ["approved"],
        },
        risk_level="read",
        audit="Request approval to exit plan mode and begin acting.",
        interaction="plan_approval",
    )

    async def run(self, input: dict[str, Any], context: AgentToolContext) -> dict[str, Any]:
        del input, context
        # Reaching run() means the user approved; the toolset flip happened in
        # the decision handler before resume.
        return {"approved": True}
