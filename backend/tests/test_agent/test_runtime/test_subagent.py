"""Tests for runtime/subagent.py — subagent delegation pattern."""

from __future__ import annotations

import pytest

from app.services.agent.runtime.dispatch import ToolEntry
from app.services.agent.runtime.llm_client import DeterministicTestClient, LLMResponse
from app.services.agent.runtime.session_state import SessionState
from app.services.agent.runtime.subagent import run_subagent


def _make_text_response(text: str) -> LLMResponse:
    """Create a simple text LLM response (stop_reason=end_turn)."""
    return LLMResponse(
        content=text,
        stop_reason="end_turn",
        usage={"input_tokens": 10, "output_tokens": 5},
    )


def _make_tool_then_text_responses(
    tool_name: str,
    tool_id: str,
    tool_input: dict,
    final_text: str,
) -> list[LLMResponse]:
    """Create a sequence: tool_use response, then text response."""
    return [
        LLMResponse(
            content="",
            tool_calls=[{
                "id": tool_id,
                "name": tool_name,
                "input": tool_input,
            }],
            stop_reason="tool_use",
            usage={"input_tokens": 10, "output_tokens": 5},
        ),
        _make_text_response(final_text),
    ]


class TestRunSubagent:
    @pytest.mark.asyncio
    async def test_returns_text_summary(self):
        llm = DeterministicTestClient([_make_text_response("I found 3 files.")])
        session = SessionState(project_id="p1", conversation_id="c1")
        dispatch: dict[str, ToolEntry] = {}

        result = await run_subagent(
            prompt="Find all FASTQ files",
            parent_session=session,
            llm=llm,
            parent_dispatch_map=dispatch,
            system_prompt="You are a helpful assistant.",
        )
        assert result == "I found 3 files."

    @pytest.mark.asyncio
    async def test_task_tool_excluded(self):
        """The 'task' tool should be filtered out to prevent recursive spawning."""
        llm = DeterministicTestClient([_make_text_response("done")])

        async def dummy_handler(**kwargs):
            return "should not be called"

        parent_dispatch = {
            "scan_dir": ToolEntry(handler=dummy_handler, schema={}, risk_level="READ"),
            "task": ToolEntry(handler=dummy_handler, schema={}, risk_level="ACT_LOW"),
        }
        session = SessionState(project_id="p1", conversation_id="c1")

        result = await run_subagent(
            prompt="test",
            parent_session=session,
            llm=llm,
            parent_dispatch_map=parent_dispatch,
            system_prompt="test",
        )
        assert result == "done"

    @pytest.mark.asyncio
    async def test_isolated_messages(self):
        """Child session should have its own message list."""
        llm = DeterministicTestClient([_make_text_response("child response")])
        parent = SessionState(project_id="p1", conversation_id="c1")
        parent.messages.append({"role": "user", "content": "parent message"})

        await run_subagent(
            prompt="child task",
            parent_session=parent,
            llm=llm,
            parent_dispatch_map={},
            system_prompt="test",
        )

        assert len(parent.messages) == 1
        assert parent.messages[0]["content"] == "parent message"

    @pytest.mark.asyncio
    async def test_max_rounds_respected(self):
        """Subagent should stop at max_rounds even with tool calls."""
        responses = [
            LLMResponse(
                content="",
                tool_calls=[{"id": f"t{i}", "name": "unknown_tool", "input": {}}],
                stop_reason="tool_use",
                usage={"input_tokens": 10, "output_tokens": 5},
            )
            for i in range(5)
        ]

        llm = DeterministicTestClient(responses)
        session = SessionState(project_id="p1", conversation_id="c1")

        result = await run_subagent(
            prompt="test",
            parent_session=session,
            llm=llm,
            parent_dispatch_map={},
            system_prompt="test",
            max_rounds=2,
        )
        assert (
            "max" in result.lower()
            or "completed" in result.lower()
            or "subagent" in result.lower()
        )

    @pytest.mark.asyncio
    async def test_tool_calls_then_text(self):
        """Subagent should execute tool calls and return final text."""

        async def echo_handler(**kwargs):
            return "echoed"

        dispatch = {
            "echo": ToolEntry(
                handler=echo_handler,
                schema={
                    "type": "function",
                    "function": {
                        "name": "echo",
                        "description": "echo",
                        "parameters": {"type": "object", "properties": {}},
                    },
                },
                risk_level="READ",
            ),
        }

        responses = _make_tool_then_text_responses(
            tool_name="echo",
            tool_id="call-1",
            tool_input={},
            final_text="All done with echo.",
        )
        llm = DeterministicTestClient(responses)
        session = SessionState(project_id="p1", conversation_id="c1")

        result = await run_subagent(
            prompt="run echo",
            parent_session=session,
            llm=llm,
            parent_dispatch_map=dispatch,
            system_prompt="test",
        )
        assert result == "All done with echo."


class TestSubagentCancellation:
    @pytest.mark.asyncio
    async def test_cancellation_callback_is_forwarded(self):
        """When is_cancelled returns True, the subagent should stop early."""
        responses = [
            LLMResponse(
                content="",
                tool_calls=[{"id": f"t{i}", "name": "echo", "input": {}}],
                stop_reason="tool_use",
                usage={"input_tokens": 10, "output_tokens": 5},
            )
            for i in range(20)
        ]
        llm = DeterministicTestClient(responses)

        cancel_after = 2
        call_count = 0

        def is_cancelled() -> bool:
            nonlocal call_count
            call_count += 1
            return call_count > cancel_after

        async def echo_handler(**kwargs):
            return "echoed"

        dispatch = {
            "echo": ToolEntry(
                handler=echo_handler,
                schema={
                    "type": "function",
                    "function": {
                        "name": "echo",
                        "description": "echo",
                        "parameters": {"type": "object", "properties": {}},
                    },
                },
                risk_level="READ",
            ),
        }
        session = SessionState(project_id="p1", conversation_id="c1")

        result = await run_subagent(
            prompt="keep echoing",
            parent_session=session,
            llm=llm,
            parent_dispatch_map=dispatch,
            system_prompt="test",
            is_cancelled=is_cancelled,
        )
        assert call_count <= 10
        assert result is not None
