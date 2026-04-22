"""Subagent delegation pattern (s04).

Spawns a child agent loop with isolated message context that reuses
the parent's tools (minus recursive spawning) and returns a text summary.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Awaitable, Callable

from app.services.agent.runtime.session_state import SessionState
from app.utils.logging import get_logger

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.services.agent.runtime.dispatch import ToolEntry
    from app.services.agent.runtime.llm_client import LLMClient

logger = get_logger(__name__)

SUBAGENT_MAX_ROUNDS = 30
_EXCLUDED_TOOLS = {"task"}


async def run_subagent(
    *,
    prompt: str,
    parent_session: SessionState,
    llm: "LLMClient",
    parent_dispatch_map: dict[str, "ToolEntry"],
    system_prompt: str,
    max_rounds: int = SUBAGENT_MAX_ROUNDS,
    is_cancelled: Callable[[], bool | "Awaitable[bool]"] | None = None,
    db_session: "AsyncSession | None" = None,
    conversation_id: str | None = None,
) -> str:
    """Run a child agent loop and return its final text response.

    The child gets:
    - Fresh message history (context isolation)
    - Parent's tools minus ``task`` (no recursive spawning)
    - Same LLM client and system prompt
    - The parent's db_session + conversation_id so the risk/approval
      gate still fires for ACT_HIGH tool calls inside the subagent.
      Without threading these through, _check_risk inside loop.py
      early-returns and the child silently bypasses approval.
    """
    from app.services.agent.runtime.loop import agent_loop

    # Filter out tools that could cause recursion
    child_dispatch = {
        k: v for k, v in parent_dispatch_map.items() if k not in _EXCLUDED_TOOLS
    }

    # Create isolated child session
    child_session = SessionState(
        project_id=parent_session.project_id,
        conversation_id=parent_session.conversation_id,
        workspace_root=parent_session.workspace_root,
    )

    # Fall back to the parent's identifiers when explicit ones aren't
    # supplied (keeps legacy callers working while still enforcing the
    # approval gate whenever they're available).
    effective_conversation_id = conversation_id or parent_session.conversation_id

    # Collect events — we only need the final text
    collected_events: list[dict[str, Any]] = []

    async def collect_event(event: dict[str, Any]) -> None:
        collected_events.append(event)

    logger.info("subagent.start", prompt=prompt[:80])

    await agent_loop(
        user_message=prompt,
        session_state=child_session,
        dispatch_map=child_dispatch,
        llm=llm,
        system_prompt=system_prompt,
        on_event=collect_event,
        is_cancelled=is_cancelled or (lambda: False),
        max_rounds=max_rounds,
        db_session=db_session,
        conversation_id=effective_conversation_id,
    )

    # Extract the last text event as the summary
    for event in reversed(collected_events):
        if event.get("type") == "text":
            summary = event.get("content", "")
            logger.info("subagent.done", summary_len=len(summary))
            return summary

    logger.warning("subagent.no_text_event")
    return "Subagent completed without producing a text response."
