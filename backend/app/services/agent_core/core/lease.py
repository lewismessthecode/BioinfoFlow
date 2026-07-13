from __future__ import annotations

import asyncio


LEASE_LOSS_CANCELLATION = "agent_turn_lease_lost"


def is_lease_loss_cancellation(exc: asyncio.CancelledError) -> bool:
    return bool(exc.args and exc.args[0] == LEASE_LOSS_CANCELLATION)


__all__ = ["LEASE_LOSS_CANCELLATION", "is_lease_loss_cancellation"]
