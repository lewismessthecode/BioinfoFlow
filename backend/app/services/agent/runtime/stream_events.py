"""Stream event types for the agent loop → SSE pipeline.

Each event represents an atomic unit of information streamed from the
agent loop to the frontend via Server-Sent Events.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class TextDelta:
    """Incremental text content from the LLM."""

    text: str


@dataclass(frozen=True)
class ThinkingDelta:
    """Incremental reasoning/thinking content from the LLM."""

    text: str


@dataclass(frozen=True)
class ToolCallStart:
    """A tool call has begun execution."""

    id: str
    name: str
    args: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ToolCallEnd:
    """A tool call has completed."""

    id: str
    name: str
    result: str
    is_error: bool = False
    duration_ms: float = 0.0


@dataclass(frozen=True)
class ToolCallsAccumulated:
    """All tool call chunks have been assembled into complete calls."""

    tool_calls: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class AgentDone:
    """The agent has finished processing."""

    usage: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class AgentError:
    """An error occurred during agent processing."""

    message: str


# Union type for dispatching
StreamEvent = (
    TextDelta
    | ThinkingDelta
    | ToolCallStart
    | ToolCallEnd
    | ToolCallsAccumulated
    | AgentDone
    | AgentError
)
