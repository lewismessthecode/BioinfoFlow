"""Tests for runtime/compact.py — 3-layer context compaction."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.services.agent.runtime.compact import (
    auto_compact,
    micro_compact,
    should_auto_compact,
)
from app.services.agent.runtime.messages import estimate_tokens


class TestMicroCompact:
    def test_preserves_recent_messages(self):
        messages = [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "tc_1", "type": "function", "function": {"name": "scan_dir", "arguments": "{}"}}
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "tc_1",
                "content": "lots of data here",
                "_round": 8,
            },
        ]
        # Current round 9 → round 8 is within horizon (3), should NOT be compacted
        micro_compact(messages, current_round=9)
        assert messages[1]["content"] == "lots of data here"

    def test_compacts_old_messages(self):
        messages = [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"id": "tc_1", "type": "function", "function": {"name": "scan_dir", "arguments": "{}"}}
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "tc_1",
                "content": "lots of data here",
                "_round": 1,
            },
        ]
        # Current round 10 → round 1 is well past horizon, should be compacted
        micro_compact(messages, current_round=10)
        assert messages[1]["content"].startswith("[Previous:")
        assert "scan_dir" in messages[1]["content"]

    def test_skips_already_compacted(self):
        messages = [
            {
                "role": "tool",
                "tool_call_id": "tc_1",
                "content": "[Previous: used scan_dir]",
                "_round": 1,
            },
        ]
        micro_compact(messages, current_round=10)
        assert messages[0]["content"] == "[Previous: used scan_dir]"

    def test_ignores_non_tool_messages(self):
        messages = [
            {"role": "assistant", "content": "response text", "_round": 1},
        ]
        micro_compact(messages, current_round=10)
        assert messages[0]["content"] == "response text"

    def test_ignores_plain_text_user_messages(self):
        messages = [
            {"role": "user", "content": "hello", "_round": 1},
        ]
        micro_compact(messages, current_round=10)
        assert messages[0]["content"] == "hello"


class TestShouldAutoCompact:
    def test_under_threshold(self):
        messages = [{"role": "user", "content": "short"}]
        assert not should_auto_compact(messages, threshold=50_000)

    def test_over_threshold(self):
        messages = [{"role": "user", "content": "x" * 200_001}]
        assert should_auto_compact(messages, threshold=50_000)


class TestEstimateTokens:
    def test_scales_with_content(self):
        small = estimate_tokens([{"role": "user", "content": "hi"}])
        large = estimate_tokens([{"role": "user", "content": "a" * 10000}])
        assert large > small * 5


class TestAutoCompact:
    @pytest.mark.asyncio
    async def test_returns_summary_message(self):
        """auto_compact should call LLM to summarize, return a single summary message."""
        from app.services.agent.runtime.llm_client import LLMResponse

        mock_llm = AsyncMock()
        mock_llm.create.return_value = LLMResponse(
            content="Summary of conversation so far.",
            stop_reason="end_turn",
            usage={"input_tokens": 100, "output_tokens": 50},
        )

        messages = [
            {"role": "user", "content": "Analyze my FASTQ files"},
            {"role": "assistant", "content": "I'll scan the directory."},
            {"role": "user", "content": "Great, please proceed."},
        ]

        result = await auto_compact(
            messages, llm=mock_llm, system_prompt="You are Bioinfoflow."
        )

        assert len(result) == 1
        assert result[0]["role"] == "user"
        assert "<context-summary>" in result[0]["content"]
        assert "Summary of conversation so far." in result[0]["content"]
        mock_llm.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_saves_transcript_to_disk(self, tmp_path):
        """auto_compact should save full transcript before summarizing."""
        from app.services.agent.runtime.llm_client import LLMResponse

        mock_llm = AsyncMock()
        mock_llm.create.return_value = LLMResponse(
            content="Summary.",
            stop_reason="end_turn",
        )

        messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ]

        transcript_dir = tmp_path / "transcripts"
        await auto_compact(
            messages,
            llm=mock_llm,
            system_prompt="test",
            transcript_dir=transcript_dir,
        )

        transcripts = list(transcript_dir.glob("transcript_*.jsonl"))
        assert len(transcripts) == 1
        lines = transcripts[0].read_text().strip().split("\n")
        assert len(lines) == 2
