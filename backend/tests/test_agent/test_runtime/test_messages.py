"""Tests for runtime/messages.py — plain dict message helpers (OpenAI format)."""

from __future__ import annotations

from app.services.agent.runtime.messages import (
    estimate_tokens,
    extract_text,
    extract_tool_calls,
    make_tool_results,
    make_user_message,
)


class TestMakeUserMessage:
    def test_basic(self):
        msg = make_user_message("hello")
        assert msg == {"role": "user", "content": "hello"}

    def test_empty(self):
        msg = make_user_message("")
        assert msg["role"] == "user"
        assert msg["content"] == ""


class TestMakeToolResults:
    def test_single_result(self):
        calls = [{"id": "call_1", "name": "scan_dir", "input": {}}]
        results = ['{"files": []}']
        msgs = make_tool_results(calls, results)
        assert isinstance(msgs, list)
        assert len(msgs) == 1
        msg = msgs[0]
        assert msg["role"] == "tool"
        assert msg["tool_call_id"] == "call_1"
        assert msg["content"] == '{"files": []}'

    def test_multiple_results(self):
        calls = [
            {"id": "call_1", "name": "a", "input": {}},
            {"id": "call_2", "name": "b", "input": {}},
        ]
        results = ["r1", "r2"]
        msgs = make_tool_results(calls, results)
        assert len(msgs) == 2
        assert msgs[0]["tool_call_id"] == "call_1"
        assert msgs[0]["content"] == "r1"
        assert msgs[1]["tool_call_id"] == "call_2"
        assert msgs[1]["content"] == "r2"


class TestExtractToolCalls:
    def test_no_tool_calls(self):
        msg = {"role": "assistant", "content": "just text"}
        assert extract_tool_calls(msg) == []

    def test_with_tool_calls(self):
        msg = {
            "role": "assistant",
            "content": "thinking...",
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "scan_dir",
                        "arguments": '{"path": "/tmp"}',
                    },
                }
            ],
        }
        calls = extract_tool_calls(msg)
        assert len(calls) == 1
        assert calls[0]["id"] == "call_1"
        assert calls[0]["name"] == "scan_dir"
        assert calls[0]["input"] == {"path": "/tmp"}

    def test_missing_tool_calls_key(self):
        msg = {"role": "assistant", "content": "done"}
        assert extract_tool_calls(msg) == []


class TestExtractText:
    def test_string_content(self):
        msg = {"role": "assistant", "content": "hello"}
        assert extract_text(msg) == "hello"

    def test_none_content(self):
        msg = {"role": "assistant", "content": None}
        assert extract_text(msg) == ""

    def test_missing_content(self):
        msg = {"role": "assistant"}
        assert extract_text(msg) == ""


class TestEstimateTokens:
    def test_basic(self):
        messages = [{"role": "user", "content": "a" * 400}]
        tokens = estimate_tokens(messages)
        # ~400 chars content + JSON overhead => ~100+ tokens
        assert tokens > 100

    def test_empty(self):
        assert estimate_tokens([]) < 10
