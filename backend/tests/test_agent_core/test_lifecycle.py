from contextlib import asynccontextmanager

import pytest

from app.services.agent_core.core.lifecycle import TurnLifecycle
from app.services.agent_core.ownership import TurnOwnershipLostError


class _FakeOwnership:
    def __init__(self):
        self.entered = False
        self.exited = False

    @asynccontextmanager
    async def maintain(self):
        self.entered = True
        try:
            yield self
        finally:
            self.exited = True


@pytest.mark.asyncio
async def test_lifecycle_executes_inside_one_ownership_context():
    ownership = _FakeOwnership()
    lifecycle = TurnLifecycle(
        read_after_ownership_loss=lambda turn_id: _value(f"lost:{turn_id}"),
        terminalize_unexpected_failure=lambda **kwargs: _value(
            f"failed:{kwargs['turn_id']}"
        ),
    )

    result = await lifecycle.execute(
        turn_id="turn-1",
        ownership=ownership,
        operation=lambda: _value("completed"),
    )

    assert result == "completed"
    assert ownership.entered is True
    assert ownership.exited is True


@pytest.mark.asyncio
async def test_lifecycle_projects_ownership_loss_without_terminalizing():
    ownership = _FakeOwnership()
    lifecycle = TurnLifecycle(
        read_after_ownership_loss=lambda turn_id: _value(f"lost:{turn_id}"),
        terminalize_unexpected_failure=lambda **kwargs: _value(
            f"failed:{kwargs['turn_id']}"
        ),
    )

    result = await lifecycle.execute(
        turn_id="turn-2",
        ownership=ownership,
        operation=_raise_ownership_loss,
    )

    assert result == "lost:turn-2"


@pytest.mark.asyncio
async def test_lifecycle_routes_unexpected_failure_to_terminalizer():
    ownership = _FakeOwnership()
    lifecycle = TurnLifecycle(
        read_after_ownership_loss=lambda turn_id: _value(f"lost:{turn_id}"),
        terminalize_unexpected_failure=lambda **kwargs: _value(
            f"failed:{kwargs['turn_id']}:{type(kwargs['exc']).__name__}"
        ),
    )

    result = await lifecycle.execute(
        turn_id="turn-3",
        ownership=ownership,
        operation=_raise_unexpected,
    )

    assert result == "failed:turn-3:RuntimeError"


async def _value(value):
    return value


async def _raise_ownership_loss():
    raise TurnOwnershipLostError("replaced")


async def _raise_unexpected():
    raise RuntimeError("unexpected")
