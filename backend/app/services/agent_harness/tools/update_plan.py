from __future__ import annotations

from typing import Any

from app.services.agent_harness.tools.specs import ToolExecutionContext, ToolSpec


class UpdatePlanTool:
    spec = ToolSpec(
        name="update_plan",
        description=(
            "Create or replace the visible execution plan. Keep exactly one item "
            "in progress until the work is complete."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "explanation": {"type": "string"},
                "plan": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 50,
                    "items": {
                        "type": "object",
                        "properties": {
                            "step": {"type": "string", "minLength": 1},
                            "status": {
                                "type": "string",
                                "enum": ["pending", "in_progress", "completed"],
                            },
                        },
                        "required": ["step", "status"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["plan"],
            "additionalProperties": False,
        },
        replay_policy="safe",
        serial=True,
    )

    async def run(
        self, arguments: dict[str, Any], context: ToolExecutionContext
    ) -> dict[str, Any]:
        del context
        raw_plan = arguments.get("plan")
        if not isinstance(raw_plan, list) or not raw_plan:
            raise ValueError("plan must contain at least one item")
        in_progress = sum(
            1
            for item in raw_plan
            if isinstance(item, dict) and item.get("status") == "in_progress"
        )
        if in_progress > 1:
            raise ValueError("plan must not contain more than one in_progress item")
        return {
            "title": str(arguments.get("explanation") or "").strip() or None,
            "items": [
                {
                    "id": f"step-{index}",
                    "text": str(item["step"]).strip(),
                    "status": item["status"],
                }
                for index, item in enumerate(raw_plan, start=1)
            ],
        }
