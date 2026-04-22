"""Three-layer context compaction (s03 pattern).

Layer 1 (micro): Replace old tool result content with short placeholders.
Layer 2 (auto):  At token threshold, save transcript and LLM-summarize.
Layer 3 (manual): ``compact`` tool triggers the same auto-compact logic.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.services.agent.runtime.messages import estimate_tokens
from app.utils.logging import get_logger

if TYPE_CHECKING:
    from app.services.agent.runtime.llm_client import LLMClient

logger = get_logger(__name__)

# Rounds after which tool result content is replaced with a placeholder.
MICRO_COMPACT_HORIZON = 3


def micro_compact(messages: list[dict[str, Any]], current_round: int) -> None:
    """Layer 1: In-place replacement of stale tool result messages.

    Tool results (role: "tool") older than ``MICRO_COMPACT_HORIZON`` rounds
    are replaced with a short ``[Previous: used {tool_name}]`` placeholder.

    The ``_round`` key is stamped on tool messages by the main loop.
    """
    cutoff = current_round - MICRO_COMPACT_HORIZON
    for msg in messages:
        if msg.get("role") != "tool":
            continue
        msg_round = msg.get("_round")
        if msg_round is None or msg_round >= cutoff:
            continue
        content = msg.get("content", "")
        if isinstance(content, str) and content.startswith("[Previous:"):
            continue  # Already compacted
        tool_call_id = msg.get("tool_call_id", "")
        tool_name = _lookup_tool_name(messages, tool_call_id)
        msg["content"] = f"[Previous: used {tool_name}]"


def _lookup_tool_name(messages: list[dict[str, Any]], tool_call_id: str) -> str:
    """Find the tool name for a given tool_call_id by scanning assistant messages."""
    for msg in messages:
        if msg.get("role") != "assistant":
            continue
        for tc in msg.get("tool_calls", []):
            tc_id = tc.get("id", "")
            if tc_id == tool_call_id:
                func = tc.get("function", {})
                return func.get("name", "tool")
    return "tool"


async def auto_compact(
    messages: list[dict[str, Any]],
    *,
    llm: "LLMClient",
    system_prompt: str,
    transcript_dir: Path | None = None,
) -> list[dict[str, Any]]:
    """Layer 2: Save transcript to disk, then LLM-summarize to ~2000 tokens.

    Returns a new messages list containing only the summary as a single
    user message.
    """
    if transcript_dir:
        _save_transcript(messages, transcript_dir)

    summary = await _summarize_messages(messages, llm=llm, system_prompt=system_prompt)

    return [
        {
            "role": "user",
            "content": (
                "<context-summary>\n"
                "The conversation was compacted to save context. "
                "Here is a summary of what happened so far:\n\n"
                f"{summary}\n"
                "</context-summary>\n\n"
                "Please continue from where we left off."
            ),
        }
    ]


async def _summarize_messages(
    messages: list[dict[str, Any]],
    *,
    llm: "LLMClient",
    system_prompt: str,
) -> str:
    """Ask the LLM to summarize the conversation so far."""
    condensed_parts: list[str] = []
    for msg in messages:
        role = msg.get("role", "?")
        content = msg.get("content", "") or ""

        if role == "assistant":
            parts = [content] if content else []
            for tc in msg.get("tool_calls", []):
                func = tc.get("function", {})
                parts.append(f"[Called tool: {func.get('name', '?')}]")
            content = " ".join(parts)
        elif role == "tool":
            tool_call_id = msg.get("tool_call_id", "?")
            if len(content) > 200:
                content = content[:200] + "..."
            content = f"[Tool result ({tool_call_id}): {content}]"

        if len(content) > 500:
            content = content[:500] + "..."
        condensed_parts.append(f"{role}: {content}")

    condensed = "\n".join(condensed_parts)

    summary_prompt = (
        "Summarize this conversation in ~500 words. Focus on:\n"
        "1. What the user asked for\n"
        "2. What tools were used and key results\n"
        "3. Current state and any pending tasks\n"
        "4. Important file paths, IDs, or values discovered\n\n"
        f"Conversation:\n{condensed}"
    )

    response = await llm.create(
        system="You are a helpful assistant that summarizes conversations concisely.",
        messages=[{"role": "user", "content": summary_prompt}],
        max_tokens=2000,
    )

    return response.content


def _save_transcript(messages: list[dict[str, Any]], transcript_dir: Path) -> Path:
    """Save the full message history as a JSONL file."""
    transcript_dir.mkdir(parents=True, exist_ok=True)
    ts = f"{time.time():.6f}_{os.getpid()}"
    path = transcript_dir / f"transcript_{ts}.jsonl"
    with open(path, "w") as f:
        for msg in messages:
            clean = {k: v for k, v in msg.items() if not k.startswith("_")}
            f.write(json.dumps(clean, ensure_ascii=False, default=str) + "\n")
    logger.info("compact.transcript_saved", path=str(path), messages=len(messages))
    return path


def should_auto_compact(messages: list[dict[str, Any]], threshold: int) -> bool:
    """Check if the message history has exceeded the token threshold."""
    return estimate_tokens(messages) > threshold
