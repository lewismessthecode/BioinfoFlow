from __future__ import annotations

from typing import Any

from app.services.agent_core.tools.specs import AgentToolContext, AgentToolSpec
from app.utils.exceptions import BadRequestError


class TodoWriteTool:
    """Maintain a visible task checklist for multi-step work.

    Mirrors Claude Code's TodoWrite: each call *replaces* the entire list, so
    the model re-sends the full set with updated statuses. Exactly one task
    should be ``in_progress`` at a time. The result is rendered as a
    ``todo_list`` artifact (the right-panel "进度 / Progress" checklist); the
    latest call wins.
    """

    spec = AgentToolSpec(
        name="todo_write",
        description=(
            "Create and update a visible task checklist for multi-step work. "
            "Replaces the whole list each call. Keep exactly one task "
            "in_progress; mark tasks completed as you finish them."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "todos": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "content": {"type": "string", "minLength": 1},
                            "status": {
                                "type": "string",
                                "enum": ["pending", "in_progress", "completed"],
                            },
                            "activeForm": {"type": "string"},
                        },
                        "required": ["content", "status"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["todos"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {"todos": {"type": "array"}},
            "required": ["todos"],
        },
        risk_level="act_low",
        audit="Update the agent task checklist.",
        artifact_policy={"type": "todo_list"},
    )

    async def run(self, input: dict[str, Any], context: AgentToolContext) -> dict[str, Any]:
        del context
        todos = input.get("todos")
        if not isinstance(todos, list):
            raise BadRequestError("todos must be a list")
        in_progress = [todo for todo in todos if isinstance(todo, dict) and todo.get("status") == "in_progress"]
        if len(in_progress) > 1:
            raise BadRequestError("at most one task may be in_progress")
        return {"todos": todos}
