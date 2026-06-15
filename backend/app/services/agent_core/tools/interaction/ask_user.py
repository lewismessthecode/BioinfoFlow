from __future__ import annotations

from typing import Any

from app.services.agent_core.tools.specs import AgentToolContext, AgentToolSpec


class AskUserTool:
    """Ask the user a structured clarifying question and pause for the answer.

    This is an interaction tool: it never executes anything. Setting
    ``interaction="user_input"`` makes the executor pause the turn for the user
    regardless of permission_mode (even ``bypass``). On resume the user's reply
    is threaded back into the tool input under ``_user_answer`` and echoed as the
    tool result, so the model continues with the choice in context.

    Use it only to clarify genuinely ambiguous requirements or to choose between
    materially different approaches — never for trivially-defaultable choices.
    """

    spec = AgentToolSpec(
        name="ask_user",
        description=(
            "Ask the user a structured multiple-choice question to clarify "
            "ambiguous requirements or choose between approaches. Pauses for the "
            "user's answer. Do not use for trivially-defaultable choices."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "questions": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 4,
                    "items": {
                        "type": "object",
                        "properties": {
                            "question": {"type": "string", "minLength": 1},
                            "header": {"type": "string", "minLength": 1, "maxLength": 12},
                            "multiSelect": {"type": "boolean"},
                            "options": {
                                "type": "array",
                                "minItems": 2,
                                "maxItems": 4,
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "label": {"type": "string", "minLength": 1},
                                        "description": {"type": "string"},
                                    },
                                    "required": ["label", "description"],
                                    "additionalProperties": False,
                                },
                            },
                        },
                        "required": ["question", "header", "options"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["questions"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {"answers": {"type": "object"}},
            "required": ["answers"],
        },
        risk_level="read",
        audit="Ask the user a structured clarifying question.",
        interaction="user_input",
    )

    async def run(self, input: dict[str, Any], context: AgentToolContext) -> dict[str, Any]:
        del context
        answer = input.get("_user_answer")
        return {"answers": answer if isinstance(answer, dict) else {}}
