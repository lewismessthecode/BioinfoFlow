from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.repositories.agent_harness_repo import AgentHarnessRepository
from app.services.agent_harness.snapshot import AgentHarnessSnapshotService


@pytest.mark.asyncio
async def test_repository_snapshot_delegates_to_application_service(
    harness_db,
) -> None:
    repository = AgentHarnessRepository(harness_db)
    expected = object()

    with patch.object(
        AgentHarnessSnapshotService,
        "build",
        new_callable=AsyncMock,
        return_value=expected,
    ) as build:
        actual = await repository.snapshot("session-id")

    assert actual is expected
    build.assert_awaited_once_with("session-id")
