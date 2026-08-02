"""Shared durable turn lifecycle execution rules.

The runtime owns turn-specific work. This module owns the invariant that every
owned execution path gets one lease heartbeat, one ownership-loss projection,
and one unexpected-failure terminalization path.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from app.services.agent_core.ownership import TurnOwnership, TurnOwnershipLostError


class TurnLifecycle:
    """Run one owned turn operation through the durable lifecycle seam."""

    def __init__(
        self,
        *,
        read_after_ownership_loss: Callable[[str], Awaitable[Any]],
        terminalize_unexpected_failure: Callable[..., Awaitable[Any]],
    ) -> None:
        self._read_after_ownership_loss = read_after_ownership_loss
        self._terminalize_unexpected_failure = terminalize_unexpected_failure

    async def execute(
        self,
        *,
        turn_id: str,
        ownership: TurnOwnership,
        operation: Callable[[], Awaitable[Any]],
    ) -> Any:
        async with ownership.maintain():
            try:
                return await operation()
            except TurnOwnershipLostError:
                return await self._read_after_ownership_loss(turn_id)
            except Exception as exc:  # noqa: BLE001 - lifecycle terminalizes failures
                return await self._terminalize_unexpected_failure(
                    turn_id=turn_id,
                    ownership=ownership,
                    exc=exc,
                )


__all__ = ["TurnLifecycle"]
