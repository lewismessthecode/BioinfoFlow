from __future__ import annotations

from uuid import UUID

import pytest

from app.services.agent_harness.contracts import AssistantDeltaEvent
from app.services.agent_harness.events import AgentEventHub


@pytest.mark.asyncio
async def test_event_hub_close_ends_existing_stream_and_allows_new_lifecycle() -> None:
    hub = AgentEventHub()

    async def first_snapshot():
        return None

    first = hub.stream("session-1", first_snapshot)
    assert (await anext(first)).type == "snapshot"

    await hub.close()
    with pytest.raises(StopAsyncIteration):
        await anext(first)

    second = hub.stream("session-1", first_snapshot)
    assert (await anext(second)).type == "snapshot"
    await second.aclose()


@pytest.mark.asyncio
async def test_slow_event_subscriber_is_dropped_without_blocking_fast_subscribers() -> (
    None
):
    hub = AgentEventHub()

    async def snapshot():
        return None

    slow = hub.stream("session-1", snapshot)
    fast = hub.stream("session-1", snapshot)
    assert (await anext(slow)).type == "snapshot"
    assert (await anext(fast)).type == "snapshot"

    for index in range(257):
        event = AssistantDeltaEvent(
            run_id=UUID("00000000-0000-0000-0000-000000000001"),
            delta=str(index),
            start_offset=index,
            end_offset=index + 1,
        )
        await hub.publish("session-1", event)
        received = await anext(fast)
        assert received == event

    with pytest.raises(StopAsyncIteration):
        await anext(slow)

    final = AssistantDeltaEvent(
        run_id=UUID("00000000-0000-0000-0000-000000000001"),
        delta="final",
        start_offset=257,
        end_offset=262,
    )
    await hub.publish("session-1", final)
    assert await anext(fast) == final
    await fast.aclose()
    assert hub._subscribers == {}
