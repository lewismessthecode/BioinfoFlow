from __future__ import annotations

from app.services.agent_core.observability import agent_event_log_fields


def test_agent_event_log_fields_keeps_diagnostics_without_payload_contents():
    fields = agent_event_log_fields(
        session_id="session-1",
        turn_id="turn-1",
        seq=12,
        event_type="turn.failed",
        payload={
            "error_code": "model_request_failed",
            "error_message": "x" * 500,
            "final_text": "model output should not be logged",
            "input_text": "user prompt should not be logged",
        },
    )

    assert fields == {
        "session_id": "session-1",
        "turn_id": "turn-1",
        "seq": 12,
        "event_type": "turn.failed",
        "error_code": "model_request_failed",
        "error_message": f"{'x' * 197}...",
    }
