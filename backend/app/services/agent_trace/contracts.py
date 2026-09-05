from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue


AGENT_TRACE_PROTOCOL = "bioinfoflow.agent.trace"
AGENT_TRACE_PROTOCOL_VERSION = 1

TraceCategory = Literal["system", "user", "context", "assistant", "tool"]


class _StrictContract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TraceModelSummary(_StrictContract):
    provider: str
    model: str
    display_name: str


class TraceSessionSummary(_StrictContract):
    id: str
    title: str | None = None
    status: str
    model: TraceModelSummary
    created_at: datetime
    updated_at: datetime


class TraceTurn(_StrictContract):
    id: str
    run_id: str
    index: int = Field(ge=1)
    status: str
    model: TraceModelSummary | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


class ContextCompositionItem(_StrictContract):
    category: TraceCategory
    characters: int = Field(ge=0)
    tokens: int | None = Field(default=None, ge=0)


class ContextFlowSnapshot(_StrictContract):
    id: str
    turn_id: str
    model_trace_id: str
    sequence: int = Field(ge=1)
    through_sequence: int = Field(ge=0)
    compacted: bool = False
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    cached_input_tokens: int | None = Field(default=None, ge=0)
    reasoning_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    max_context_tokens: int | None = Field(default=None, ge=1)
    composition: list[ContextCompositionItem] = Field(default_factory=list)
    created_at: datetime


class TraceEvent(_StrictContract):
    id: str
    turn_id: str | None = None
    category: TraceCategory
    title: str
    # ``title`` remains for clients that predate the localized title contract.
    title_code: str | None = None
    title_params: dict[str, JsonValue] = Field(default_factory=dict)
    summary: str
    status: str | None = None
    sequence: int = Field(ge=1)
    has_detail: bool = False
    created_at: datetime


class AgentTraceTimeline(_StrictContract):
    protocol: Literal["bioinfoflow.agent.trace"] = AGENT_TRACE_PROTOCOL
    protocol_version: Literal[1] = AGENT_TRACE_PROTOCOL_VERSION
    session: TraceSessionSummary
    turns: list[TraceTurn] = Field(default_factory=list)
    context_flow: list[ContextFlowSnapshot] = Field(default_factory=list)
    events: list[TraceEvent] = Field(default_factory=list)


class TraceTiming(_StrictContract):
    started_at: datetime | None = None
    request_prepared_at: datetime | None = None
    first_byte_at: datetime | None = None
    completed_at: datetime | None = None
    duration_ms: int | None = Field(default=None, ge=0)


class AgentTraceEventDetail(_StrictContract):
    protocol: Literal["bioinfoflow.agent.trace"] = AGENT_TRACE_PROTOCOL
    protocol_version: Literal[1] = AGENT_TRACE_PROTOCOL_VERSION
    event_id: str
    summary: dict[str, JsonValue] = Field(default_factory=dict)
    payload: JsonValue | None = None
    result: JsonValue | None = None
    schema_: JsonValue | None = Field(default=None, alias="schema")
    timing: TraceTiming | None = None


__all__ = [
    "AGENT_TRACE_PROTOCOL",
    "AGENT_TRACE_PROTOCOL_VERSION",
    "AgentTraceEventDetail",
    "AgentTraceTimeline",
    "ContextCompositionItem",
    "ContextFlowSnapshot",
    "TraceCategory",
    "TraceEvent",
    "TraceModelSummary",
    "TraceSessionSummary",
    "TraceTiming",
    "TraceTurn",
]
