from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_harness import AgentHarnessSession
from app.repositories.agent_harness_repo import AgentHarnessRepository
from app.services.agent_harness.contracts import OpenSessionRequest
from app.services.agent_harness.snapshot import AgentHarnessSnapshotService
from tests.test_agent_harness.run_test_helpers import create_agent_run


def _request() -> OpenSessionRequest:
    return OpenSessionRequest(
        user_id="user-1",
        workspace_id=UUID("30000000-0000-0000-0000-000000000001"),
        prompt_snapshot={"system": "stable"},
    )


@pytest.mark.asyncio
async def test_snapshot_service_preserves_the_public_snapshot_json_contract() -> None:
    timestamp = datetime(2026, 9, 3, 12, 0, tzinfo=timezone.utc)
    session = AgentHarnessSession(
        id="10000000-0000-0000-0000-000000000001",
        user_id="user-1",
        workspace_id="30000000-0000-0000-0000-000000000001",
        project_id=None,
        title="Golden conversation",
        model_snapshot=None,
        permission_mode="ask_dangerous",
        workspace_access="read_write",
        settings_revision=1,
        environment_scope={"mode": "auto"},
        prompt_snapshot={"system": "stable"},
        history_revision=0,
        command_queue=[],
        command_ids=[],
        status="active",
        created_at=timestamp,
        updated_at=timestamp,
    )

    class StaticReader:
        async def get_session(self, _session_id: str) -> AgentHarnessSession:
            return session

        async def list_runs(self, _session_id: str) -> list:
            return []

        async def list_entries(self, _session_id: str) -> list:
            return []

    snapshot = await AgentHarnessSnapshotService(StaticReader()).build(
        str(session.id)
    )

    assert snapshot.model_dump(mode="json") == {
        "presentation_protocol": "bioinfoflow.agent.presentation",
        "presentation_schema_version": 1,
        "session": {
            "id": "10000000-0000-0000-0000-000000000001",
            "user_id": "user-1",
            "workspace_id": "30000000-0000-0000-0000-000000000001",
            "project_id": None,
            "title": "Golden conversation",
            "model": {
                "provider": "unknown",
                "model": "unknown",
                "display_name": "unknown",
                "supports_vision": False,
                "supports_reasoning": False,
                "supports_tools": False,
            },
            "permission_mode": "ask_dangerous",
            "workspace_access": "read_write",
            "settings_revision": 1,
            "environment_scope": {"mode": "auto", "environment_ids": None},
            "status": "active",
            "created_at": "2026-09-03T12:00:00Z",
            "updated_at": "2026-09-03T12:00:00Z",
        },
        "runs": [],
        "entries": [],
        "active_run": None,
    }


@pytest.mark.asyncio
async def test_snapshot_service_projects_repository_state_to_public_contract(
    harness_db: AsyncSession,
) -> None:
    repository = AgentHarnessRepository(harness_db)
    session = await repository.open_session(_request())
    run = await create_agent_run(repository, str(session.id))
    await repository.append_entry(
        str(session.id),
        run_id=str(run.id),
        entry_type="message",
        payload={
            "role": "user",
            "parts": [{"id": "part-1", "type": "text", "text": "hello"}],
        },
    )

    snapshot = await AgentHarnessSnapshotService(repository).build(str(session.id))

    assert snapshot.presentation_protocol == "bioinfoflow.agent.presentation"
    assert snapshot.session.id == session.id
    assert [entry.type for entry in snapshot.entries] == ["message"]
    assert snapshot.runs[0].id == run.id
    assert snapshot.active_run is not None
    assert snapshot.active_run.run.id == run.id

