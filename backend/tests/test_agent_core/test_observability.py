from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.agent_core import ledger as ledger_module
from app.services.agent_core.ledger import AgentEventLedger
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


@pytest.mark.asyncio
async def test_event_ledger_logs_appended_events_at_debug_not_info(monkeypatch):
    debug_calls: list[tuple[str, dict]] = []
    info_calls: list[tuple[str, dict]] = []

    class FakeSessionRepository:
        async def lock_for_update(self, session_id: str):
            assert session_id == "session-1"
            return object()

    class FakeLogger:
        def debug(self, event_name: str, **fields):
            debug_calls.append((event_name, fields))

        def info(self, event_name: str, **fields):
            info_calls.append((event_name, fields))

    class FakeRepo:
        session = SimpleNamespace(rollback=lambda: None)

        async def next_seq(self, session_id: str) -> int:
            assert session_id == "session-1"
            return 11730

        async def create(self, **fields):
            return SimpleNamespace(**fields)

    monkeypatch.setattr(ledger_module, "logger", FakeLogger())
    ledger = AgentEventLedger.__new__(AgentEventLedger)
    ledger.event_repo = FakeRepo()
    ledger.session_repo = FakeSessionRepository()

    event = await ledger.append(
        session_id="session-1",
        turn_id="turn-1",
        type="assistant.tool_call.delta",
        payload={"status": "building", "arguments_delta": "x" * 500},
    )

    assert event.seq == 11730
    assert info_calls == []
    assert debug_calls == [
        (
            "agent_core.event.appended",
            {
                "session_id": "session-1",
                "turn_id": "turn-1",
                "seq": 11730,
                "event_type": "assistant.tool_call.delta",
                "status": "building",
            },
        ),
    ]
