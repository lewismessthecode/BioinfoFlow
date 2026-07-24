from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class AgentEventType:
    TURN_CREATED = "turn.created"
    TURN_STARTED = "turn.started"
    TURN_COMPLETED = "turn.completed"
    TURN_FAILED = "turn.failed"
    TURN_CANCELLED = "turn.cancelled"
    TURN_INTERRUPTED = "turn.interrupted"
    TURN_STEER_RECEIVED = "turn.steer.received"
    TURN_STEER_DELIVERED = "turn.steer.delivered"
    TURN_STEER_CANCELLED = "turn.steer.cancelled"
    TURN_NO_PROGRESS = "turn.no_progress"
    TURN_RECOVERY_ENQUEUED = "turn.recovery.enqueued"
    TURN_RECOVERY_FAILED = "turn.recovery.failed"
    TRANSCRIPT_TOOL_GROUP_REPAIRED = "transcript.tool_group_repaired"
    MODEL_SELECTED = "model.selected"
    MODEL_RETRYING = "model.retrying"
    MODEL_FALLBACK = "model.fallback"
    MODEL_WARNING = "model.warning"
    PERMISSION_POLICY_UPDATED = "permission.policy_updated"
    PERMISSION_PENDING_RECONCILED = "permission.pending_reconciled"
    ASSISTANT_TEXT_DELTA = "assistant.text.delta"
    ASSISTANT_TEXT_COMPLETED = "assistant.text.completed"
    ASSISTANT_THINKING_DELTA = "assistant.thinking.delta"
    ASSISTANT_THINKING_COMPLETED = "assistant.thinking.completed"
    ASSISTANT_THINKING_SUMMARY = "assistant.thinking.summary"
    ASSISTANT_TOOL_CALL_STARTED = "assistant.tool_call.started"
    ASSISTANT_TOOL_CALL_DELTA = "assistant.tool_call.delta"
    ASSISTANT_TOOL_CALL_COMPLETED = "assistant.tool_call.completed"
    ACTION_REQUESTED = "action.requested"
    ACTION_RISK_ASSESSED = "action.risk_assessed"
    ACTION_WAITING_DECISION = "action.waiting_decision"
    ACTION_DECISION_RECORDED = "action.decision_recorded"
    ACTION_STARTED = "action.started"
    ACTION_COMPLETED = "action.completed"
    ACTION_FAILED = "action.failed"
    ACTION_CANCELLED = "action.cancelled"
    ARTIFACT_CREATED = "artifact.created"
    MEMORY_READ = "memory.read"
    MEMORY_PROPOSED = "memory.proposed"
    MEMORY_WRITTEN = "memory.written"
    MEMORY_REJECTED = "memory.rejected"


class PublicAgentEventType:
    TURN_LIFECYCLE = "turn.lifecycle"
    TURN_STEERING = "turn.steering"
    MODEL_LIFECYCLE = "model.lifecycle"
    ASSISTANT_CONTENT = "assistant.content"
    ASSISTANT_TOOL_CALL = "assistant.tool_call"
    ACTION_LIFECYCLE = "action.lifecycle"
    ARTIFACT_CREATED = "artifact.created"
    MEMORY_LIFECYCLE = "memory.lifecycle"


_PUBLIC_EVENT_PROJECTIONS: dict[str, tuple[str, dict[str, str]]] = {
    AgentEventType.TURN_CREATED: (
        PublicAgentEventType.TURN_LIFECYCLE,
        {"status": "created"},
    ),
    AgentEventType.TURN_STARTED: (
        PublicAgentEventType.TURN_LIFECYCLE,
        {"status": "started"},
    ),
    AgentEventType.TURN_COMPLETED: (
        PublicAgentEventType.TURN_LIFECYCLE,
        {"status": "completed"},
    ),
    AgentEventType.TURN_FAILED: (
        PublicAgentEventType.TURN_LIFECYCLE,
        {"status": "failed"},
    ),
    AgentEventType.TURN_CANCELLED: (
        PublicAgentEventType.TURN_LIFECYCLE,
        {"status": "cancelled"},
    ),
    AgentEventType.TURN_INTERRUPTED: (
        PublicAgentEventType.TURN_LIFECYCLE,
        {"status": "interrupted"},
    ),
    AgentEventType.TURN_NO_PROGRESS: (
        PublicAgentEventType.TURN_LIFECYCLE,
        {"status": "no_progress"},
    ),
    AgentEventType.TURN_RECOVERY_ENQUEUED: (
        PublicAgentEventType.TURN_LIFECYCLE,
        {"status": "recovery_enqueued"},
    ),
    AgentEventType.TURN_RECOVERY_FAILED: (
        PublicAgentEventType.TURN_LIFECYCLE,
        {"status": "recovery_failed"},
    ),
    AgentEventType.TURN_STEER_RECEIVED: (
        PublicAgentEventType.TURN_STEERING,
        {"status": "received"},
    ),
    AgentEventType.TURN_STEER_DELIVERED: (
        PublicAgentEventType.TURN_STEERING,
        {"status": "delivered"},
    ),
    AgentEventType.TURN_STEER_CANCELLED: (
        PublicAgentEventType.TURN_STEERING,
        {"status": "cancelled"},
    ),
    AgentEventType.MODEL_SELECTED: (
        PublicAgentEventType.MODEL_LIFECYCLE,
        {"status": "selected"},
    ),
    AgentEventType.MODEL_RETRYING: (
        PublicAgentEventType.MODEL_LIFECYCLE,
        {"status": "retrying"},
    ),
    AgentEventType.MODEL_FALLBACK: (
        PublicAgentEventType.MODEL_LIFECYCLE,
        {"status": "fallback"},
    ),
    AgentEventType.MODEL_WARNING: (
        PublicAgentEventType.MODEL_LIFECYCLE,
        {"status": "warning"},
    ),
    AgentEventType.ASSISTANT_TEXT_DELTA: (
        PublicAgentEventType.ASSISTANT_CONTENT,
        {"kind": "text", "phase": "delta"},
    ),
    AgentEventType.ASSISTANT_TEXT_COMPLETED: (
        PublicAgentEventType.ASSISTANT_CONTENT,
        {"kind": "text", "phase": "completed"},
    ),
    AgentEventType.ASSISTANT_THINKING_DELTA: (
        PublicAgentEventType.ASSISTANT_CONTENT,
        {"kind": "thinking", "phase": "delta"},
    ),
    AgentEventType.ASSISTANT_THINKING_COMPLETED: (
        PublicAgentEventType.ASSISTANT_CONTENT,
        {"kind": "thinking", "phase": "completed"},
    ),
    AgentEventType.ASSISTANT_THINKING_SUMMARY: (
        PublicAgentEventType.ASSISTANT_CONTENT,
        {"kind": "thinking", "phase": "summary"},
    ),
    AgentEventType.ASSISTANT_TOOL_CALL_STARTED: (
        PublicAgentEventType.ASSISTANT_TOOL_CALL,
        {"phase": "started"},
    ),
    AgentEventType.ASSISTANT_TOOL_CALL_DELTA: (
        PublicAgentEventType.ASSISTANT_TOOL_CALL,
        {"phase": "delta"},
    ),
    AgentEventType.ASSISTANT_TOOL_CALL_COMPLETED: (
        PublicAgentEventType.ASSISTANT_TOOL_CALL,
        {"phase": "completed"},
    ),
    AgentEventType.ACTION_REQUESTED: (
        PublicAgentEventType.ACTION_LIFECYCLE,
        {"status": "requested"},
    ),
    AgentEventType.ACTION_RISK_ASSESSED: (
        PublicAgentEventType.ACTION_LIFECYCLE,
        {"status": "risk_assessed"},
    ),
    AgentEventType.ACTION_WAITING_DECISION: (
        PublicAgentEventType.ACTION_LIFECYCLE,
        {"status": "waiting_decision"},
    ),
    AgentEventType.ACTION_DECISION_RECORDED: (
        PublicAgentEventType.ACTION_LIFECYCLE,
        {"status": "decision_recorded"},
    ),
    AgentEventType.ACTION_STARTED: (
        PublicAgentEventType.ACTION_LIFECYCLE,
        {"status": "started"},
    ),
    AgentEventType.ACTION_COMPLETED: (
        PublicAgentEventType.ACTION_LIFECYCLE,
        {"status": "completed"},
    ),
    AgentEventType.ACTION_FAILED: (
        PublicAgentEventType.ACTION_LIFECYCLE,
        {"status": "failed"},
    ),
    AgentEventType.ACTION_CANCELLED: (
        PublicAgentEventType.ACTION_LIFECYCLE,
        {"status": "cancelled"},
    ),
    AgentEventType.ARTIFACT_CREATED: (PublicAgentEventType.ARTIFACT_CREATED, {}),
    AgentEventType.MEMORY_READ: (
        PublicAgentEventType.MEMORY_LIFECYCLE,
        {"status": "read"},
    ),
    AgentEventType.MEMORY_PROPOSED: (
        PublicAgentEventType.MEMORY_LIFECYCLE,
        {"status": "proposed"},
    ),
    AgentEventType.MEMORY_WRITTEN: (
        PublicAgentEventType.MEMORY_LIFECYCLE,
        {"status": "written"},
    ),
    AgentEventType.MEMORY_REJECTED: (
        PublicAgentEventType.MEMORY_LIFECYCLE,
        {"status": "rejected"},
    ),
}
PUBLIC_DURABLE_EVENT_TYPES = frozenset(_PUBLIC_EVENT_PROJECTIONS)


def project_public_event(event: Mapping[str, Any]) -> dict[str, Any] | None:
    """Project a durable user event onto the stable public transport protocol."""
    if event.get("visibility") != "user":
        return None
    projection = _PUBLIC_EVENT_PROJECTIONS.get(str(event.get("type") or ""))
    if projection is None:
        return None
    public_type, discriminators = projection
    payload = event.get("payload")
    public_payload = dict(payload) if isinstance(payload, dict) else {}
    public_payload.update(discriminators)
    return {
        **event,
        "type": public_type,
        "payload": public_payload,
        "visibility": "user",
        "schema_version": 1,
    }


_DELTA_COMPLETION_TYPES = {
    AgentEventType.ASSISTANT_TEXT_DELTA: AgentEventType.ASSISTANT_TEXT_COMPLETED,
    AgentEventType.ASSISTANT_THINKING_DELTA: AgentEventType.ASSISTANT_THINKING_COMPLETED,
    AgentEventType.ASSISTANT_TOOL_CALL_DELTA: AgentEventType.ASSISTANT_TOOL_CALL_COMPLETED,
}


def compact_transcript_events(events: list[Any]) -> list[Any]:
    """Drop stream deltas superseded by cumulative completion events."""
    completion_keys = {
        key
        for event in events
        if event.type in _DELTA_COMPLETION_TYPES.values()
        if (key := _stream_event_key(event)) is not None
    }
    return [
        event
        for event in events
        if event.type not in _DELTA_COMPLETION_TYPES
        or _stream_event_key(event) not in completion_keys
    ]


def _stream_event_key(event: Any) -> tuple[str, str, str] | None:
    payload = event.payload if isinstance(event.payload, dict) else {}
    if event.type in {
        AgentEventType.ASSISTANT_TEXT_DELTA,
        AgentEventType.ASSISTANT_TEXT_COMPLETED,
    }:
        family = "text"
        identifier = payload.get("message_id")
    elif event.type in {
        AgentEventType.ASSISTANT_THINKING_DELTA,
        AgentEventType.ASSISTANT_THINKING_COMPLETED,
    }:
        family = "thinking"
        identifier = payload.get("message_id")
    elif event.type in {
        AgentEventType.ASSISTANT_TOOL_CALL_DELTA,
        AgentEventType.ASSISTANT_TOOL_CALL_COMPLETED,
    }:
        family = "tool_call"
        identifier = payload.get("call_id")
    else:
        return None
    if not isinstance(identifier, str) or not identifier:
        return None
    return str(event.turn_id or ""), family, identifier


__all__ = [
    "AgentEventType",
    "PublicAgentEventType",
    "PUBLIC_DURABLE_EVENT_TYPES",
    "compact_transcript_events",
    "project_public_event",
]
