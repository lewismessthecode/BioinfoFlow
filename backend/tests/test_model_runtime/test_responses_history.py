from __future__ import annotations

from app.services.model_runtime.codecs.responses import ResponsesCodec
from app.services.model_runtime.contracts import (
    ModelInvocation,
    ModelTarget,
    TextPart,
)


def test_completed_turn_assistant_text_uses_easy_input_message_shape() -> None:
    invocation = ModelInvocation(
        target=ModelTarget(
            endpoint_id="endpoint-responses",
            provider_kind="openai",
            model_name="gpt-test",
            routed_model_name="openai/gpt-test",
            wire_protocol="responses",
        ),
        instructions="Continue the conversation.",
        input_items=(
            TextPart(text="First question."),
            TextPart(text="First answer.", phase="final_answer"),
            TextPart(text="Follow-up question."),
        ),
        tools=(),
        stream=False,
        max_output_tokens=128,
    )

    request = ResponsesCodec().encode_request(invocation)

    assert request["input"] == [
        {
            "role": "user",
            "content": [{"type": "input_text", "text": "First question."}],
        },
        {
            "role": "assistant",
            "content": "First answer.",
            "phase": "final_answer",
        },
        {
            "role": "user",
            "content": [
                {"type": "input_text", "text": "Follow-up question."}
            ],
        },
    ]
