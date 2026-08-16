from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

import pytest

from app.services.agent_harness.contracts import AssistantDeltaEvent, SessionSnapshot
from app.services.agent_harness.events import AgentEventHub


def _snapshot() -> SessionSnapshot:
    now = datetime(2026, 8, 15, tzinfo=timezone.utc)
    return SessionSnapshot(
        session={
            "id": UUID("10000000-0000-0000-0000-000000000001"),
            "user_id": "user-1",
            "workspace_id": UUID("30000000-0000-0000-0000-000000000001"),
            "model": {
                "provider": "openai",
                "model": "gpt-5.6",
                "display_name": "GPT-5.6",
                "supports_vision": True,
                "supports_reasoning": True,
                "supports_tools": True,
            },
            "permission_mode": "ask_dangerous",
            "workspace_access": "read_write",
            "status": "active",
            "created_at": now,
            "updated_at": now,
        },
        runs=[],
        entries=[],
        active_run=None,
    )


@pytest.mark.asyncio
async def test_event_hub_close_ends_existing_stream_and_allows_new_lifecycle() -> None:
    hub = AgentEventHub()

    async def first_snapshot():
        return _snapshot()

    first = hub.stream("session-1", first_snapshot)
    assert (await anext(first)).type == "snapshot"

    await hub.close()
    with pytest.raises(StopAsyncIteration):
        await anext(first)

    second = hub.stream("session-1", first_snapshot)
    assert (await anext(second)).type == "snapshot"
    await second.aclose()


@pytest.mark.asyncio
async def test_event_hub_close_session_ends_only_deleted_session_streams() -> None:
    hub = AgentEventHub()

    async def snapshot():
        return _snapshot()

    deleted = hub.stream("deleted-session", snapshot)
    retained = hub.stream("retained-session", snapshot)
    assert (await anext(deleted)).type == "snapshot"
    assert (await anext(retained)).type == "snapshot"

    await hub.close_session("deleted-session")

    with pytest.raises(StopAsyncIteration):
        await anext(deleted)
    event = AssistantDeltaEvent(
        run_id=UUID("00000000-0000-0000-0000-000000000001"),
        draft_id="draft-1",
        part_id="draft-1:text",
        part_type="text",
        delta="still live",
        start_offset=0,
        end_offset=10,
    )
    await hub.publish("retained-session", event)
    assert await anext(retained) == event
    await retained.aclose()


@pytest.mark.asyncio
async def test_event_stream_detects_session_deleted_by_another_worker() -> None:
    hub = AgentEventHub(liveness_interval_seconds=0.01)
    deleted = False
    snapshot_calls = 0

    async def snapshot():
        nonlocal snapshot_calls
        snapshot_calls += 1
        return _snapshot()

    async def exists():
        return not deleted

    events = hub.stream("session-1", snapshot, exists)
    assert (await anext(events)).type == "snapshot"
    deleted = True

    with pytest.raises(StopAsyncIteration):
        await anext(events)
    assert snapshot_calls == 1


@pytest.mark.asyncio
async def test_slow_event_subscriber_is_dropped_without_blocking_fast_subscribers() -> (
    None
):
    hub = AgentEventHub()

    async def snapshot():
        return _snapshot()

    slow = hub.stream("session-1", snapshot)
    fast = hub.stream("session-1", snapshot)
    assert (await anext(slow)).type == "snapshot"
    assert (await anext(fast)).type == "snapshot"

    for index in range(257):
        event = AssistantDeltaEvent(
            run_id=UUID("00000000-0000-0000-0000-000000000001"),
            draft_id="draft-1",
            part_id="draft-1:text",
            part_type="text",
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
        draft_id="draft-1",
        part_id="draft-1:text",
        part_type="text",
        delta="final",
        start_offset=257,
        end_offset=262,
    )
    await hub.publish("session-1", final)
    assert await anext(fast) == final
    await fast.aclose()
    assert hub._subscribers == {}
