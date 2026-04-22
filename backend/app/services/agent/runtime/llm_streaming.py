"""Stream chunk processing for LLM responses.

Extracted from llm_client.py to keep each module under 400 lines.
Handles accumulating tool call deltas and converting streamed chunks
into StreamEvent objects.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any, AsyncIterator

from app.services.agent.runtime.llm_providers import (
    LLMProviderAttempt,
    _LLM_REQUEST_TIMEOUT,
    is_retryable_llm_exception,
)
from app.services.agent.runtime.stream_events import (
    AgentDone,
    AgentError,
    StreamEvent,
    TextDelta,
    ThinkingDelta,
    ToolCallsAccumulated,
)
from app.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class StreamFallbackSignal:
    """Internal signal indicating the caller should try the next provider.

    Never yielded to external consumers -- only used between
    ``process_stream_response`` and ``LLMClient.create_stream``.
    """

    error: str


# Events yielded by process_stream_response include the normal StreamEvent
# types plus the internal StreamFallbackSignal.
StreamOrFallback = StreamEvent | StreamFallbackSignal


def accumulate_tool_calls(
    tool_call_chunks: dict[int, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Convert accumulated tool call chunks into structured tool calls."""
    result = []
    for _idx in sorted(tool_call_chunks.keys()):
        entry = tool_call_chunks[_idx]
        try:
            args = json.loads(entry["arguments"]) if entry["arguments"] else {}
        except json.JSONDecodeError:
            args = {}
        result.append({
            "id": entry["id"],
            "name": entry["name"],
            "input": args,
        })
    return result


async def process_stream_response(
    response: Any,
    attempt: LLMProviderAttempt,
) -> AsyncIterator[StreamOrFallback]:
    """Process a streaming LLM response, yielding StreamEvent objects.

    May yield ``StreamFallbackSignal`` to indicate the caller should
    try the next provider attempt instead of forwarding the error.
    """
    tool_call_chunks: dict[int, dict[str, Any]] = {}
    last_chunk: Any = None
    yielded_content = False

    try:
        async with asyncio.timeout(_LLM_REQUEST_TIMEOUT):
            async for chunk in response:
                last_chunk = chunk
                delta = chunk.choices[0].delta if chunk.choices else None
                if not delta:
                    continue

                reasoning = getattr(delta, "reasoning_content", None)
                if reasoning:
                    yielded_content = True
                    yield ThinkingDelta(text=reasoning)

                if delta.content:
                    yielded_content = True
                    yield TextDelta(text=delta.content)

                if delta.tool_calls:
                    yielded_content = True
                    for tc_delta in delta.tool_calls:
                        idx = tc_delta.index
                        if idx not in tool_call_chunks:
                            tool_call_chunks[idx] = {
                                "id": tc_delta.id or "",
                                "name": "",
                                "arguments": "",
                            }
                        entry = tool_call_chunks[idx]
                        if tc_delta.id:
                            entry["id"] = tc_delta.id
                        if tc_delta.function:
                            if tc_delta.function.name:
                                entry["name"] = tc_delta.function.name
                            if tc_delta.function.arguments:
                                entry["arguments"] += tc_delta.function.arguments

        if tool_call_chunks:
            yield ToolCallsAccumulated(
                tool_calls=accumulate_tool_calls(tool_call_chunks)
            )

        usage: dict[str, int] = {}
        if last_chunk is not None and hasattr(last_chunk, "usage") and last_chunk.usage:
            usage = {
                "input_tokens": getattr(last_chunk.usage, "prompt_tokens", 0) or 0,
                "output_tokens": getattr(last_chunk.usage, "completion_tokens", 0) or 0,
            }

        yield AgentDone(usage=usage)

    except TimeoutError:
        if not yielded_content:
            yield StreamFallbackSignal(
                error=f"{attempt.provider}/{attempt.model} stream timed out after {_LLM_REQUEST_TIMEOUT}s"
            )
        else:
            yield AgentError(
                message=f"{attempt.provider}/{attempt.model} stream timed out after {_LLM_REQUEST_TIMEOUT}s"
            )

    except Exception as exc:
        logger.exception("llm.stream_error", error=str(exc))
        if not yielded_content and is_retryable_llm_exception(exc):
            yield StreamFallbackSignal(error=str(exc))
        else:
            yield AgentError(message=str(exc))
