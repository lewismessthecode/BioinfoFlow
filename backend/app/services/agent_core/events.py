from __future__ import annotations

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


__all__ = ["AgentEventType", "compact_transcript_events"]
