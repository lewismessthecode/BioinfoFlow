"""Tests for runtime/loop.py — core agent loop with streaming."""

from __future__ import annotations

from typing import Any, AsyncIterator

import pytest

from app.services.agent.runtime.llm_client import LLMResponse
from app.services.agent.runtime.loop import agent_loop
from app.services.agent.runtime.session_state import SessionState
from app.services.agent.runtime.dispatch import ToolEntry
from app.services.agent.runtime.stream_events import (
    AgentDone,
    StreamEvent,
    TextDelta,
    ThinkingDelta,
    ToolCallsAccumulated,
)


def _make_session_state() -> SessionState:
    return SessionState(project_id="test", conversation_id="conv-1")


class _MockLLM:
    """Configurable mock LLM for loop tests.

    Accepts LLMResponse objects (new OpenAI format) and yields them
    as streaming events via create_stream().
    """

    def __init__(self, responses: list[LLMResponse]):
        self._responses = list(responses)
        self._call_count = 0

    async def create(self, **kwargs: Any) -> LLMResponse:
        idx = min(self._call_count, len(self._responses) - 1)
        self._call_count += 1
        return self._responses[idx]

    async def create_stream(self, **kwargs: Any) -> AsyncIterator[StreamEvent]:
        idx = min(self._call_count, len(self._responses) - 1)
        self._call_count += 1
        resp = self._responses[idx]

        # Yield thinking if present
        if resp.thinking:
            yield ThinkingDelta(text=resp.thinking)

        # Yield text if present
        if resp.content:
            yield TextDelta(text=resp.content)

        # Yield tool calls as a single accumulated event
        if resp.tool_calls:
            yield ToolCallsAccumulated(tool_calls=resp.tool_calls)

        yield AgentDone(usage=resp.usage)


def _text_response(text: str) -> LLMResponse:
    return LLMResponse(content=text, stop_reason="end_turn")


def _tool_response(
    tool_name: str, tool_id: str = "tc_1", tool_input: dict | None = None
) -> LLMResponse:
    return LLMResponse(
        content="",
        tool_calls=[{
            "id": tool_id,
            "name": tool_name,
            "input": tool_input or {},
        }],
        stop_reason="tool_use",
    )


def _simple_dispatch_map() -> dict[str, ToolEntry]:
    """Dispatch map with a single mock tool."""

    async def mock_handler(**kwargs: Any) -> str:
        return '{"result": "ok"}'

    return {
        "mock_tool": ToolEntry(
            handler=mock_handler,
            schema={
                "type": "function",
                "function": {
                    "name": "mock_tool",
                    "description": "A mock tool",
                    "parameters": {},
                },
            },
            risk_level="read",
        ),
    }


@pytest.mark.asyncio
async def test_loop_exits_on_end_turn():
    """Loop should exit when LLM returns end_turn stop reason."""
    events: list[dict] = []

    async def on_event(event: dict) -> None:
        events.append(event)

    llm = _MockLLM([_text_response("Done!")])

    await agent_loop(
        user_message="hello",
        session_state=_make_session_state(),
        dispatch_map={},
        llm=llm,
        system_prompt="test",
        on_event=on_event,
        is_cancelled=lambda: False,
        max_rounds=10,
    )

    event_types = [e["type"] for e in events]
    assert "text_delta" in event_types or "text" in event_types
    # Check the final text event or text_delta contains our text
    text_events = [e for e in events if e["type"] in ("text", "text_delta")]
    all_text = "".join(e["content"] for e in text_events)
    assert "Done!" in all_text


@pytest.mark.asyncio
async def test_loop_dispatches_tools():
    """Loop should call tools and continue looping on tool_use."""
    events: list[dict] = []

    async def on_event(event: dict) -> None:
        events.append(event)

    llm = _MockLLM(
        [
            _tool_response("mock_tool"),
            _text_response("Finished after tool call."),
        ]
    )

    await agent_loop(
        user_message="use the tool",
        session_state=_make_session_state(),
        dispatch_map=_simple_dispatch_map(),
        llm=llm,
        system_prompt="test",
        on_event=on_event,
        is_cancelled=lambda: False,
        max_rounds=10,
    )

    event_types = [e["type"] for e in events]
    assert "tool_call_start" in event_types
    assert "tool_call_end" in event_types
    assert "text" in event_types or "text_delta" in event_types


@pytest.mark.asyncio
async def test_loop_max_rounds():
    """Loop should exit after max_rounds with a warning message."""
    events: list[dict] = []

    async def on_event(event: dict) -> None:
        events.append(event)

    llm = _MockLLM([_tool_response("mock_tool")] * 10)

    await agent_loop(
        user_message="keep going",
        session_state=_make_session_state(),
        dispatch_map=_simple_dispatch_map(),
        llm=llm,
        system_prompt="test",
        on_event=on_event,
        is_cancelled=lambda: False,
        max_rounds=3,
    )

    text_events = [e for e in events if e["type"] == "text"]
    assert len(text_events) == 1
    assert "maximum" in text_events[0]["content"].lower()


@pytest.mark.asyncio
async def test_loop_cancellation():
    """Loop should exit immediately when is_cancelled returns True."""
    events: list[dict] = []

    async def on_event(event: dict) -> None:
        events.append(event)

    cancel_after = 0

    def is_cancelled() -> bool:
        return cancel_after > 0 and len(events) >= cancel_after

    cancel_after = 1
    llm = _MockLLM([_text_response("should not reach")])

    await agent_loop(
        user_message="hello",
        session_state=_make_session_state(),
        dispatch_map={},
        llm=llm,
        system_prompt="test",
        on_event=on_event,
        is_cancelled=is_cancelled,
        max_rounds=10,
    )

    # Should have stopped early
    assert len(events) <= 2


@pytest.mark.asyncio
async def test_loop_handles_sync_callable_returning_awaitable():
    """Regression: a sync callable that returns an awaitable (e.g. a lambda
    wrapping an async method call without `await`) must not silently cancel
    every turn. Previously the wrapper returned a bare coroutine object, and
    `if <coroutine>:` is always truthy, so the loop exited immediately before
    calling the LLM — producing the "frontend hangs forever, no reply" bug.
    """
    events: list[dict] = []

    async def on_event(event: dict) -> None:
        events.append(event)

    async def _async_is_cancelled_inner() -> bool:
        return False

    # The footgun shape: sync lambda that forgets to await the async callable.
    is_cancelled = lambda: _async_is_cancelled_inner()  # noqa: E731

    llm = _MockLLM([_text_response("hello from model")])

    await agent_loop(
        user_message="hi",
        session_state=_make_session_state(),
        dispatch_map={},
        llm=llm,
        system_prompt="test",
        on_event=on_event,
        is_cancelled=is_cancelled,
        max_rounds=2,
    )

    # The LLM must have been reached and produced a text event.
    text_events = [e for e in events if e.get("type") == "text"]
    assert text_events, f"expected LLM text event, got: {events}"
    assert "hello from model" in text_events[0]["content"]


@pytest.mark.asyncio
async def test_loop_unknown_tool_returns_error():
    """Loop should handle unknown tools gracefully."""
    events: list[dict] = []

    async def on_event(event: dict) -> None:
        events.append(event)

    llm = _MockLLM(
        [
            _tool_response("nonexistent_tool"),
            _text_response("Handled the error."),
        ]
    )

    await agent_loop(
        user_message="call unknown",
        session_state=_make_session_state(),
        dispatch_map=_simple_dispatch_map(),
        llm=llm,
        system_prompt="test",
        on_event=on_event,
        is_cancelled=lambda: False,
        max_rounds=10,
    )

    tool_end_events = [e for e in events if e["type"] == "tool_call_end"]
    assert len(tool_end_events) >= 1
    assert tool_end_events[0]["metadata"]["is_error"] is True


@pytest.mark.asyncio
async def test_loop_appends_messages():
    """Loop should build up the message history correctly."""
    state = _make_session_state()

    llm = _MockLLM([_text_response("Response")])

    async def noop_event(event: dict) -> None:
        pass

    await agent_loop(
        user_message="hello",
        session_state=state,
        dispatch_map={},
        llm=llm,
        system_prompt="test",
        on_event=noop_event,
        is_cancelled=lambda: False,
        max_rounds=10,
    )

    assert len(state.messages) >= 2
    assert state.messages[0]["role"] == "user"
    assert state.messages[0]["content"] == "hello"
    assert state.messages[1]["role"] == "assistant"


def _thinking_text_response(text: str, thinking: str) -> LLMResponse:
    """LLMResponse with both text and thinking content."""
    return LLMResponse(
        content=text,
        stop_reason="end_turn",
        thinking=thinking,
    )


@pytest.mark.asyncio
async def test_loop_emits_thinking_content_event():
    """Loop should emit thinking_delta events when LLM returns thinking text."""
    events: list[dict] = []

    async def on_event(event: dict) -> None:
        events.append(event)

    llm = _MockLLM(
        [_thinking_text_response("Final answer.", "Let me reason about this...")]
    )

    await agent_loop(
        user_message="hello",
        session_state=_make_session_state(),
        dispatch_map={},
        llm=llm,
        system_prompt="test",
        on_event=on_event,
        is_cancelled=lambda: False,
        max_rounds=10,
    )

    thinking_events = [e for e in events if e["type"] == "thinking_delta"]
    assert len(thinking_events) == 1
    assert thinking_events[0]["content"] == "Let me reason about this..."


@pytest.mark.asyncio
async def test_loop_no_thinking_content_when_empty():
    """Loop should NOT emit thinking_delta events when thinking is empty."""
    events: list[dict] = []

    async def on_event(event: dict) -> None:
        events.append(event)

    llm = _MockLLM([_text_response("Done!")])

    await agent_loop(
        user_message="hello",
        session_state=_make_session_state(),
        dispatch_map={},
        llm=llm,
        system_prompt="test",
        on_event=on_event,
        is_cancelled=lambda: False,
        max_rounds=10,
    )

    thinking_events = [e for e in events if e["type"] == "thinking_delta"]
    assert len(thinking_events) == 0


# ---------------------------------------------------------------------------
# Execution-policy unit tests — bypass is the key UX lever, make sure the
# happy path + every existing mode still compute the right approval decision.
# ---------------------------------------------------------------------------


class TestRequiresApprovalByPolicy:
    """Direct unit tests on ``_requires_approval_by_policy`` — cheap,
    exhaustive coverage of the policy matrix so UX regressions surface here
    instead of in an end-to-end chat session.
    """

    def test_read_always_auto_allowed(self):
        from app.services.agent.runtime.loop import _requires_approval_by_policy

        for mode in ("auto", "approve_all", "approve_python", "bypass", None):
            assert not _requires_approval_by_policy("any_tool", "read", policy=mode), mode

    def test_bypass_allows_act_high(self):
        from app.services.agent.runtime.loop import _requires_approval_by_policy

        assert not _requires_approval_by_policy(
            "platform_run_submit", "act_high", policy="bypass"
        )
        assert not _requires_approval_by_policy(
            "shell", "act_high", policy="bypass"
        )

    def test_auto_prompts_on_act_high_except_execute_code(self):
        from app.services.agent.runtime.loop import _requires_approval_by_policy

        assert _requires_approval_by_policy(
            "platform_run_submit", "act_high", policy="auto"
        )
        assert not _requires_approval_by_policy(
            "execute_code", "act_high", policy="auto"
        )

    def test_approve_all_prompts_on_act_low_too(self):
        from app.services.agent.runtime.loop import _requires_approval_by_policy

        assert _requires_approval_by_policy("file_edit", "act_low", policy="approve_all")
        assert _requires_approval_by_policy("shell", "act_high", policy="approve_all")

    def test_none_policy_falls_back_to_settings_default(self):
        from app.services.agent.runtime.loop import _requires_approval_by_policy

        # With the default settings policy ("auto") a fresh ACT_HIGH should prompt.
        assert _requires_approval_by_policy(
            "platform_run_submit", "act_high", policy=None
        )

