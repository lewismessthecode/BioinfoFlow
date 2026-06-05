from __future__ import annotations


class AgentEventType:
    TURN_CREATED = "turn.created"
    TURN_STARTED = "turn.started"
    TURN_COMPLETED = "turn.completed"
    TURN_FAILED = "turn.failed"
    TURN_CANCELLED = "turn.cancelled"
    ASSISTANT_TEXT_COMPLETED = "assistant.text.completed"
    ASSISTANT_THINKING_SUMMARY = "assistant.thinking.summary"
    MODEL_SELECTED = "model.selected"
    ACTION_REQUESTED = "action.requested"
    ACTION_RISK_ASSESSED = "action.risk_assessed"
    ACTION_WAITING_DECISION = "action.waiting_decision"
    ACTION_DECISION_RECORDED = "action.decision_recorded"
    ACTION_STARTED = "action.started"
    ACTION_COMPLETED = "action.completed"
    ACTION_FAILED = "action.failed"
    ARTIFACT_CREATED = "artifact.created"
    MEMORY_READ = "memory.read"
    MEMORY_PROPOSED = "memory.proposed"
    MEMORY_WRITTEN = "memory.written"
    MEMORY_REJECTED = "memory.rejected"


__all__ = ["AgentEventType"]
