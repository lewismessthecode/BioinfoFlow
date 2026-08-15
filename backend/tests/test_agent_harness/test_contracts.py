from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

import pytest
from pydantic import TypeAdapter, ValidationError

from app.services.agent_harness.contracts import (
    AgentCommand,
    AgentEvent,
    HistoryEntry,
    MessageEntry,
    OpenSessionRequest,
    PlanEntry,
    SessionSnapshot,
    ToolResultPart,
    UnknownPart,
)


SESSION_ID = UUID("10000000-0000-0000-0000-000000000001")
RUN_ID = UUID("20000000-0000-0000-0000-000000000001")
WORKSPACE_ID = UUID("30000000-0000-0000-0000-000000000001")


def test_public_contract_parses_all_four_commands() -> None:
    adapter = TypeAdapter(AgentCommand)

    commands = [
        {
            "type": "message",
            "command_id": "m1",
            "parts": [{"type": "text", "text": "start"}],
        },
        {
            "type": "steer",
            "command_id": "s1",
            "parts": [{"type": "text", "text": "use csv"}],
        },
        {
            "type": "respond",
            "command_id": "r1",
            "interaction_id": "question-1",
            "response": {
                "type": "ask_user",
                "answers": {"format": "continue"},
            },
        },
        {"type": "cancel", "command_id": "c1", "reason": "user stopped"},
    ]

    assert [adapter.validate_python(command).type for command in commands] == [
        "message",
        "steer",
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
        schema_version=2,
        created_at=created_at,
        payload={
            "role": "user",
            "parts": [{"id": "part-1", "type": "text", "text": "hello"}],
        },
    )
    snapshot = SessionSnapshot(
        session={
            "id": SESSION_ID,
            "user_id": "user-1",
            "workspace_id": WORKSPACE_ID,
            "project_id": None,
            "title": None,
            "model": {
                "provider": "openai",
                "model": "gpt-5.6",
                "display_name": "GPT-5.6",
                "supports_vision": True,
                "supports_reasoning": True,
                "supports_tools": True,
            },
            "permission_mode": "ask_dangerous",
            "workspace_access": "read_write",
            "status": "active",
            "created_at": created_at,
            "updated_at": created_at,
        },
        runs=[],
        entries=[entry],
        active_run=None,
    )

    dumped = snapshot.model_dump(mode="json")
    assert dumped["entries"][0]["type"] == "message"
    assert dumped["runs"] == []
    assert dumped["active_run"] is None
    assert "history_revision" not in dumped
    assert "checkpoint" not in str(dumped)


def test_public_history_rejects_harness_private_compaction_entries() -> None:
    created_at = datetime(2026, 8, 13, tzinfo=timezone.utc)

    with pytest.raises(ValidationError):
        TypeAdapter(HistoryEntry).validate_python(
            {
                "id": UUID("40000000-0000-0000-0000-000000000003"),
                "session_id": SESSION_ID,
                "run_id": RUN_ID,
                "sequence": 2,
                "schema_version": 2,
                "created_at": created_at,
                "type": "compaction",
                "payload": {
                    "summary": "Private continuity summary",
                    "through_sequence": 1,
                },
            }
        )


def test_public_message_parts_are_typed_and_unknown_parts_are_safe() -> None:
    unknown = UnknownPart(
        id="unknown-1",
        original_type="future_part",
        display_text="Unsupported content",
    )
    result = ToolResultPart(
        id="result-1",
        call_id="call-1",
        status="completed",
        output={
            "type": "json",
            "value": {"stdout": "ok", "exit_code": 0},
        },
    )

    assert unknown.model_dump(mode="json") == {
        "id": "unknown-1",
        "type": "unknown",
        "original_type": "future_part",
        "display_text": "Unsupported content",
    }
    assert result.output.type == "json"
    assert result.output.value == {"stdout": "ok", "exit_code": 0}
    with pytest.raises(ValidationError):
        UnknownPart.model_validate(
            {
                "id": "unknown-2",
                "type": "unknown",
                "original_type": "private_provider_part",
                "display_text": "Unsupported content",
                "raw": {"secret": True},
            }
        )
    with pytest.raises(ValidationError):
        ToolResultPart(
            id="result-2",
            call_id="call-2",
            status="completed",
            output={"type": "json", "value": object()},
        )


def test_plan_is_a_first_class_history_entry() -> None:
    created_at = datetime(2026, 8, 13, tzinfo=timezone.utc)

    entry = PlanEntry(
        id=UUID("40000000-0000-0000-0000-000000000002"),
        session_id=SESSION_ID,
        run_id=RUN_ID,
        sequence=2,
        created_at=created_at,
        payload={
            "plan_id": "plan-1",
            "revision": 2,
            "title": "Refactor agent UI",
            "items": [
                {"id": "item-1", "text": "Define protocol", "status": "completed"},
                {"id": "item-2", "text": "Build UI", "status": "in_progress"},
            ],
            "updated_at": created_at,
        },
    )

    assert entry.type == "plan"
    assert entry.schema_version == 2
    assert entry.payload.revision == 2
    assert entry.payload.items[1].status == "in_progress"


def test_public_event_union_covers_the_six_product_events() -> None:
    created_at = datetime(2026, 8, 13, tzinfo=timezone.utc)
    run = {
        "id": RUN_ID,
        "session_id": SESSION_ID,
        "status": "running",
        "phase": "model",
        "revision": 3,
        "created_at": created_at,
        "updated_at": created_at,
    }
    entry = {
        "id": UUID("40000000-0000-0000-0000-000000000001"),
        "session_id": SESSION_ID,
        "run_id": RUN_ID,
        "sequence": 1,
        "schema_version": 2,
        "created_at": created_at,
        "type": "message",
        "payload": {
            "role": "user",
            "parts": [{"id": "part-1", "type": "text", "text": "hello"}],
        },
    }
    snapshot = {
        "session": {
            "id": SESSION_ID,
            "user_id": "user-1",
            "workspace_id": WORKSPACE_ID,
            "project_id": None,
            "title": None,
            "model": {
                "provider": "openai",
                "model": "gpt-5.6",
                "display_name": "GPT-5.6",
                "supports_vision": True,
                "supports_reasoning": True,
                "supports_tools": True,
            },
            "permission_mode": "ask_dangerous",
            "workspace_access": "read_write",
            "status": "active",
            "created_at": created_at,
            "updated_at": created_at,
        },
        "runs": [run],
        "entries": [entry],
        "active_run": {
            "run": run,
            "assistant_draft": None,
            "tool_progress": [],
            "pending_interaction": None,
        },
    }
    adapter = TypeAdapter(AgentEvent)
    payloads = [
        {"type": "snapshot", "snapshot": snapshot},
        {"type": "run.updated", "run": run},
        {
            "type": "assistant.delta",
            "run_id": RUN_ID,
            "draft_id": "draft-1",
            "part_id": "draft-1:text",
            "part_type": "text",
            "delta": "hello",
            "start_offset": 0,
            "end_offset": 5,
        },
        {
            "type": "tool.updated",
            "run_id": RUN_ID,
            "tool": {
                "call_id": "call-1",
                    "group_id": "group-1",
                    "name": "read",
                    "display_name": "read",
                "category": "read",
                "summary": "Read README.md",
                "arguments": {"path": "README.md"},
                "execution_mode": "parallel",
                "status": "running",
                "revision": 2,
            },
        },
        {
            "type": "interaction.requested",
            "run_id": RUN_ID,
            "interaction": {
                "interaction_id": "question-1",
                "run_id": RUN_ID,
                "revision": 4,
                "request": {
                    "type": "ask_user",
                    "call_id": "ask-1",
                    "questions": [
                        {
                            "id": "format",
                            "header": "Format",
                            "question": "Continue?",
                            "options": [
                                {
                                    "id": "continue",
                                    "label": "Continue",
                                    "description": "Keep working",
                                },
                                {
                                    "id": "stop",
                                    "label": "Stop",
                                    "description": "Stop now",
                                },
                            ],
                        }
                    ],
                },
            },
        },
        {"type": "entry.committed", "entry": entry},
    ]

    with pytest.raises(ValidationError):
        adapter.validate_python({"type": "snapshot", "snapshot": None})
    with pytest.raises(ValidationError):
        adapter.validate_python({"type": "entry.committed", "entry": None})

    assert [adapter.validate_python(payload).type for payload in payloads] == [
        "snapshot",
        "run.updated",
        "assistant.delta",
        "tool.updated",
        "interaction.requested",
        "entry.committed",
    ]
