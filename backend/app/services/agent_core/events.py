from __future__ import annotations


class AgentEventType:
    TURN_CREATED = "turn.created"
    TURN_STARTED = "turn.started"
    TURN_COMPLETED = "turn.completed"
    TURN_FAILED = "turn.failed"
    TURN_CANCELLED = "turn.cancelled"
    TURN_INTERRUPTED = "turn.interrupted"
    ASSISTANT_TEXT_DELTA = "assistant.text.delta"
    ASSISTANT_TEXT_COMPLETED = "assistant.text.completed"
    ASSISTANT_THINKING_DELTA = "assistant.thinking.delta"
    ASSISTANT_THINKING_COMPLETED = "assistant.thinking.completed"
    ASSISTANT_THINKING_SUMMARY = "assistant.thinking.summary"
    ASSISTANT_TOOL_CALL_STARTED = "assistant.tool_call.started"
    ASSISTANT_TOOL_CALL_DELTA = "assistant.tool_call.delta"
    ASSISTANT_TOOL_CALL_COMPLETED = "assistant.tool_call.completed"
    MODEL_SELECTED = "model.selected"
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


__all__ = ["AgentEventType"]
