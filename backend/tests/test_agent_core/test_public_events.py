from __future__ import annotations

from uuid import uuid4

import pytest

from app.services.agent_core.events import (
    AgentEventType,
    PublicAgentEventType,
    project_public_event,
)


PUBLIC_EVENT_TYPES = {
    value
    for name, value in vars(PublicAgentEventType).items()
    if name.isupper() and isinstance(value, str)
}


@pytest.mark.parametrize(
    ("durable_type", "public_type", "discriminators"),
    [
        (AgentEventType.TURN_CREATED, "turn.lifecycle", {"status": "created"}),
        (AgentEventType.TURN_STARTED, "turn.lifecycle", {"status": "started"}),
        (AgentEventType.TURN_COMPLETED, "turn.lifecycle", {"status": "completed"}),
        (AgentEventType.TURN_FAILED, "turn.lifecycle", {"status": "failed"}),
        (AgentEventType.TURN_CANCELLED, "turn.lifecycle", {"status": "cancelled"}),
        (
            AgentEventType.TURN_INTERRUPTED,
            "turn.lifecycle",
            {"status": "interrupted"},
        ),
        (
            AgentEventType.TURN_NO_PROGRESS,
            "turn.lifecycle",
            {"status": "no_progress"},
        ),
        (
            AgentEventType.TURN_RECOVERY_ENQUEUED,
            "turn.lifecycle",
            {"status": "recovery_enqueued"},
        ),
        (
            AgentEventType.TURN_RECOVERY_FAILED,
            "turn.lifecycle",
            {"status": "recovery_failed"},
        ),
        (
            AgentEventType.TURN_STEER_RECEIVED,
            "turn.steering",
            {"status": "received"},
        ),
        (
            AgentEventType.TURN_STEER_DELIVERED,
            "turn.steering",
            {"status": "delivered"},
        ),
        (
            AgentEventType.TURN_STEER_CANCELLED,
            "turn.steering",
            {"status": "cancelled"},
        ),
        (AgentEventType.MODEL_SELECTED, "model.lifecycle", {"status": "selected"}),
        (AgentEventType.MODEL_RETRYING, "model.lifecycle", {"status": "retrying"}),
        (AgentEventType.MODEL_FALLBACK, "model.lifecycle", {"status": "fallback"}),
        (AgentEventType.MODEL_WARNING, "model.lifecycle", {"status": "warning"}),
        (
            AgentEventType.ASSISTANT_TEXT_DELTA,
            "assistant.content",
            {"kind": "text", "phase": "delta"},
        ),
        (
            AgentEventType.ASSISTANT_TEXT_COMPLETED,
            "assistant.content",
            {"kind": "text", "phase": "completed"},
        ),
        (
            AgentEventType.ASSISTANT_THINKING_DELTA,
            "assistant.content",
            {"kind": "thinking", "phase": "delta"},
        ),
        (
            AgentEventType.ASSISTANT_THINKING_COMPLETED,
            "assistant.content",
            {"kind": "thinking", "phase": "completed"},
        ),
        (
            AgentEventType.ASSISTANT_THINKING_SUMMARY,
            "assistant.content",
            {"kind": "thinking", "phase": "summary"},
        ),
        (
            AgentEventType.ASSISTANT_TOOL_CALL_STARTED,
            "assistant.tool_call",
            {"phase": "started"},
        ),
        (
            AgentEventType.ASSISTANT_TOOL_CALL_DELTA,
            "assistant.tool_call",
            {"phase": "delta"},
        ),
        (
            AgentEventType.ASSISTANT_TOOL_CALL_COMPLETED,
            "assistant.tool_call",
            {"phase": "completed"},
        ),
        (
            AgentEventType.ACTION_REQUESTED,
            "action.lifecycle",
            {"status": "requested"},
        ),
        (
            AgentEventType.ACTION_RISK_ASSESSED,
            "action.lifecycle",
            {"status": "risk_assessed"},
        ),
        (
            AgentEventType.ACTION_WAITING_DECISION,
            "action.lifecycle",
            {"status": "waiting_decision"},
        ),
        (
            AgentEventType.ACTION_DECISION_RECORDED,
            "action.lifecycle",
            {"status": "decision_recorded"},
        ),
        (AgentEventType.ACTION_STARTED, "action.lifecycle", {"status": "started"}),
        (
            AgentEventType.ACTION_COMPLETED,
            "action.lifecycle",
            {"status": "completed"},
        ),
        (AgentEventType.ACTION_FAILED, "action.lifecycle", {"status": "failed"}),
        (
            AgentEventType.ACTION_CANCELLED,
            "action.lifecycle",
            {"status": "cancelled"},
        ),
        (AgentEventType.ARTIFACT_CREATED, "artifact.created", {}),
        (AgentEventType.MEMORY_READ, "memory.lifecycle", {"status": "read"}),
        (
            AgentEventType.MEMORY_PROPOSED,
            "memory.lifecycle",
            {"status": "proposed"},
        ),
        (
            AgentEventType.MEMORY_WRITTEN,
            "memory.lifecycle",
            {"status": "written"},
        ),
        (
            AgentEventType.MEMORY_REJECTED,
            "memory.lifecycle",
            {"status": "rejected"},
        ),
    ],
)
def test_projects_user_events_into_eight_public_categories(
    durable_type: str,
    public_type: str,
    discriminators: dict[str, str],
) -> None:
    event = _event(durable_type, payload={"domain_value": 7})

    projected = project_public_event(event)

    assert projected is not None
    assert projected["type"] == public_type
    assert projected["payload"]["domain_value"] == 7
    assert {key: projected["payload"][key] for key in discriminators} == discriminators
    assert projected["visibility"] == "user"
    assert projected["schema_version"] == 1
    assert len(PUBLIC_EVENT_TYPES) == 8


@pytest.mark.parametrize(
    "durable_type",
    [
        AgentEventType.TRANSCRIPT_TOOL_GROUP_REPAIRED,
        AgentEventType.PERMISSION_POLICY_UPDATED,
        AgentEventType.PERMISSION_PENDING_RECONCILED,
    ],
)
def test_does_not_project_internal_protocol_events(durable_type: str) -> None:
    assert project_public_event(_event(durable_type)) is None


@pytest.mark.parametrize("visibility", ["internal", "audit"])
def test_does_not_project_non_user_visibility(visibility: str) -> None:
    assert project_public_event(_event(AgentEventType.TURN_STARTED, visibility)) is None


def _event(
    event_type: str,
    visibility: str = "user",
    *,
    payload: dict | None = None,
) -> dict:
    return {
        "id": str(uuid4()),
        "session_id": str(uuid4()),
        "turn_id": str(uuid4()),
        "seq": 1,
        "type": event_type,
        "payload": payload or {},
        "visibility": visibility,
        "schema_version": 7,
        "created_at": "2026-07-24T00:00:00Z",
        "updated_at": "2026-07-24T00:00:00Z",
    }
