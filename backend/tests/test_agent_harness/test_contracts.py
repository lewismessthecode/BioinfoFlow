from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

import pytest
from pydantic import TypeAdapter, ValidationError

from app.services.agent_harness.contracts import (
    AgentCommand,
    AgentEvent,
    MessageEntry,
    OpenSessionRequest,
    SessionSnapshot,
)


SESSION_ID = UUID("10000000-0000-0000-0000-000000000001")
RUN_ID = UUID("20000000-0000-0000-0000-000000000001")
WORKSPACE_ID = UUID("30000000-0000-0000-0000-000000000001")


def test_public_contract_parses_all_five_commands() -> None:
    adapter = TypeAdapter(AgentCommand)

    commands = [
        {"type": "prompt", "command_id": "p1", "text": "start", "attachment_ids": []},
        {"type": "steer", "command_id": "s1", "text": "use csv"},
        {
            "type": "follow_up",
            "command_id": "f1",
            "text": "summarize",
            "attachment_ids": [],
        },
        {
            "type": "respond",
            "command_id": "r1",
            "interaction_id": "question-1",
            "response": {"choice": "continue"},
        },
        {"type": "cancel", "command_id": "c1", "reason": "user stopped"},
    ]

    assert [adapter.validate_python(command).type for command in commands] == [
        "prompt",
        "steer",
        "follow_up",
        "respond",
        "cancel",
    ]


def test_public_contract_rejects_unknown_commands_and_unknown_fields() -> None:
    adapter = TypeAdapter(AgentCommand)

    with pytest.raises(ValidationError):
        adapter.validate_python({"type": "resume", "command_id": "x1"})
    with pytest.raises(ValidationError):
        OpenSessionRequest(
            user_id="user-1",
            workspace_id=WORKSPACE_ID,
            prompt_snapshot={},
            engine="pi",  # type: ignore[call-arg]
        )


def test_snapshot_contains_renderable_history_without_checkpoint() -> None:
    created_at = datetime(2026, 8, 13, tzinfo=timezone.utc)
    entry = MessageEntry(
        id=UUID("40000000-0000-0000-0000-000000000001"),
        session_id=SESSION_ID,
        run_id=RUN_ID,
        sequence=1,
        schema_version=1,
        created_at=created_at,
        payload={"role": "user", "content": [{"type": "text", "text": "hello"}]},
    )
    snapshot = SessionSnapshot(
        session={
            "id": SESSION_ID,
            "user_id": "user-1",
            "workspace_id": WORKSPACE_ID,
            "project_id": None,
            "title": None,
            "permission_mode": "ask_dangerous",
            "status": "active",
            "created_at": created_at,
            "updated_at": created_at,
        },
        current_run=None,
        entries=[entry],
        revision=1,
    )

    dumped = snapshot.model_dump(mode="json")
    assert dumped["entries"][0]["type"] == "message"
    assert dumped["assistant_draft"] is None
    assert dumped["tool_progress"] == []
    assert dumped["pending_interaction"] is None
    assert "checkpoint" not in str(dumped)


def test_public_event_union_covers_the_six_product_events() -> None:
    adapter = TypeAdapter(AgentEvent)
    payloads = [
        {"type": "snapshot", "snapshot": None},
        {
            "type": "run.updated",
            "run_id": RUN_ID,
            "status": "running",
            "phase": "model",
        },
        {
            "type": "assistant.delta",
            "run_id": RUN_ID,
            "delta": "hello",
            "start_offset": 0,
            "end_offset": 5,
        },
        {
            "type": "tool.updated",
            "run_id": RUN_ID,
            "call_id": "call-1",
            "status": "running",
        },
        {
            "type": "interaction.requested",
            "run_id": RUN_ID,
            "interaction_id": "question-1",
            "request": {"question": "continue?"},
        },
        {"type": "entry.committed", "entry": None},
    ]

    assert [adapter.validate_python(payload).type for payload in payloads] == [
        "snapshot",
        "run.updated",
        "assistant.delta",
        "tool.updated",
        "interaction.requested",
        "entry.committed",
    ]
