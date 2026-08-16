from __future__ import annotations

from typing import Any

from app.repositories.agent_harness_repo import AgentHarnessRepository
from app.services.agent_harness.turn_execution_config import (
    resolve_turn_execution_config,
)


async def create_agent_run(
    repository: AgentHarnessRepository,
    session_id: str,
    *,
    model_snapshot: dict[str, Any] | None = None,
):
    turn_execution_config = await agent_turn_execution_config(
        repository,
        session_id,
        model_snapshot=model_snapshot,
    )
    return await repository.create_run(
        session_id,
        model_snapshot=model_snapshot,
        turn_execution_config=turn_execution_config,
    )


async def agent_turn_execution_config(
    repository: AgentHarnessRepository,
    session_id: str,
    *,
    model_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    session = await repository.get_session(session_id)
    if session is None:
        raise LookupError(f"agent session not found: {session_id}")
    return await resolve_turn_execution_config(
        repository.db,
        session,
        model_snapshot=model_snapshot,
    )


__all__ = ["agent_turn_execution_config", "create_agent_run"]
