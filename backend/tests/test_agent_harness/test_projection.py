from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from app.models.agent_harness import AgentHarnessEntry, AgentHarnessRun
from app.services.agent_harness.projection import (
    entry_contract,
    pending_interaction_entry_view,
    public_interaction_request,
    public_interaction_response,
    public_model_summary,
    public_run_error,
    run_view,
)


SESSION_ID = UUID("10000000-0000-0000-0000-000000000001")
RUN_ID = UUID("20000000-0000-0000-0000-000000000001")
NOW = datetime(2026, 8, 15, tzinfo=timezone.utc)


def _run(**changes: object) -> AgentHarnessRun:
    values = {
        "id": RUN_ID,
        "session_id": SESSION_ID,
        "status": "failed",
        "phase": None,
        "revision": 3,
        "started_at": NOW,
        "completed_at": NOW,
        "termination_reason": "runtime_failed",
        "error": {
            "code": "provider_specific_failure",
            "message": "credential sk-private-value was rejected",
        },
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(changes)
    return AgentHarnessRun(**values)


def test_run_projection_exposes_only_stable_public_error() -> None:
    run = _run()

    assert public_run_error(run) == {
        "code": "runtime_failed",
        "message": "The Agent runtime stopped unexpectedly.",
    }
    assert run_view(run).model_dump(mode="json")["error"] == {
        "code": "runtime_failed",
        "message": "The Agent runtime stopped unexpectedly.",
    }


def test_entry_projection_returns_typed_public_history() -> None:
    entry = AgentHarnessEntry(
        id=UUID("30000000-0000-0000-0000-000000000001"),
        session_id=SESSION_ID,
        run_id=RUN_ID,
        sequence=4,
        type="message",
        schema_version=2,
        payload={
            "role": "assistant",
            "parts": [{"id": "text-1", "type": "text", "text": "Finished"}],
        },
        created_at=NOW,
        updated_at=NOW,
    )

    projected = entry_contract(entry)

    assert projected.type == "message"
    assert projected.payload.parts[0].type == "text"
    assert projected.payload.parts[0].text == "Finished"


def test_pending_interaction_projection_uses_entry_revision() -> None:
    entry = AgentHarnessEntry(
        id=UUID("30000000-0000-0000-0000-000000000002"),
        session_id=SESSION_ID,
        run_id=RUN_ID,
        sequence=5,
        type="interaction_request",
        schema_version=2,
        payload={
            "interaction_id": "approval-1",
            "request": {
                "type": "approval",
                "call_id": "bash-1",
                "tool_name": "bash",
                "summary": "Run command",
                "allowed_responses": ["reject"],
                "risk": {
                    "level": "high",
                    "effects": ["write"],
                    "reasons": ["changes files"],
                    "affected_resources": ["results.txt"],
                },
            },
        },
        created_at=NOW,
        updated_at=NOW,
    )

    projected = pending_interaction_entry_view(entry)

    assert projected.interaction_id == "approval-1"
    assert projected.run_id == RUN_ID
    assert projected.revision == 5
    assert projected.request.type == "approval"
    assert projected.request.allowed_responses == ["reject"]


def test_model_projection_exposes_only_rendering_capabilities() -> None:
    projected = public_model_summary(
        {
            "display_name": "GPT-5.6",
            "target": {
                "provider_kind": "openai",
                "model_name": "gpt-5.6",
                "api_key": "sk-private-value",
            },
            "capabilities": {
                "supports_vision": True,
                "supports_reasoning": True,
                "supports_tools": True,
                "private_transport": "responses",
            },
        }
    )

    assert projected == {
        "provider": "openai",
        "model": "gpt-5.6",
        "display_name": "GPT-5.6",
        "supports_vision": True,
        "supports_reasoning": True,
        "supports_tools": True,
    }
    assert "sk-private-value" not in str(projected)


def test_interaction_request_projection_normalizes_approval_risk() -> None:
    projected = public_interaction_request(
        {
            "kind": "confirmation",
            "call_id": "bash-1",
            "tool_name": "bash",
            "summary": "Run command",
            "input_preview": "rm output.txt",
            "allowed_responses": ["reject"],
            "risk": {
                "level": "high",
                "effects": ["delete"],
                "reasons": ["removes output"],
                "affected_resources": [{"id": "output.txt", "private": True}],
            },
            "private_policy": {"rule": "secret"},
        }
    )

    assert projected == {
        "type": "approval",
        "call_id": "bash-1",
        "tool_name": "bash",
        "summary": "Run command",
        "input_preview": "rm output.txt",
        "allowed_responses": ["reject"],
        "risk": {
            "level": "high",
            "effects": ["delete"],
            "reasons": ["removes output"],
            "affected_resources": ["output.txt"],
        },
    }


def test_interaction_response_projection_drops_private_fields() -> None:
    projected = public_interaction_response(
        {
            "type": "approval",
            "approved": True,
            "actor": "private-user-id",
            "policy_revision": 42,
        }
    )

    assert projected == {"type": "approval", "approved": True}
