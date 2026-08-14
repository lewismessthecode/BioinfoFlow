from __future__ import annotations

from typing import Any

from app.services.agent_harness.tools.specs import ToolExecutionContext, ToolSpec


class AskUserTool:
    spec = ToolSpec(
        name="ask_user",
        description=(
            "Pause and ask the user one to three short questions when their input "
            "is required to continue."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "questions": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 3,
                    "items": {
                        "type": "object",
                        "properties": {
                            "question": {"type": "string", "minLength": 1},
                            "header": {
                                "type": "string",
                                "minLength": 1,
                                "maxLength": 12,
                            },
                            "multiSelect": {"type": "boolean"},
                            "options": {
                                "type": "array",
                                "minItems": 2,
                                "maxItems": 3,
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "label": {"type": "string", "minLength": 1},
                                        "description": {"type": "string"},
                                        "recommended": {"type": "boolean"},
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
        replay_policy="safe",
        serial=True,
    )

    async def run(
        self, arguments: dict[str, Any], context: ToolExecutionContext
    ) -> dict[str, Any]:
        del arguments, context
        raise RuntimeError("ask_user is handled as a harness interaction")
