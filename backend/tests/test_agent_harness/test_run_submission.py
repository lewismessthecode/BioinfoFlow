from __future__ import annotations

from uuid import UUID

import pytest

from app.repositories.agent_harness_repo import AgentHarnessRepository
from app.services.agent_harness.contracts import (
    InputTextPart,
    MessageCommand,
    OpenSessionRequest,
)
from app.services.agent_harness.run_submission import AgentRunSubmissionService
from app.services.agent_harness.snapshot import AgentHarnessSnapshotService
@pytest.mark.asyncio
async def test_run_submission_prepares_title_and_effective_turn_config(
    harness_db,
) -> None:
    repository = AgentHarnessRepository(harness_db)
    session = await repository.open_session(
        OpenSessionRequest(
            user_id="user-1",
            workspace_id=UUID("30000000-0000-0000-0000-000000000001"),
            permission_mode="ask_dangerous",
            prompt_snapshot={"system": "stable"},
        )
    )
    prompt = "Summarize this very long workflow request with many details"

    run, entry, inserted = await AgentRunSubmissionService(
        repository
    ).submit_user_command(
        str(session.id),
        MessageCommand(
            command_id="message-title",
            parts=[InputTextPart(text=prompt)],
        ),
    )

    assert inserted is True
    assert run is not None
    assert entry is not None
    assert run.turn_execution_config == {
        "settings_revision": 1,
        "model": None,
        "permission_mode": "ask_dangerous",
        "workspace_access": "read_write",
        "environment_scope": {
            "mode": "auto",
            "environment_ids": ["local"],
        },
        "environment_targets": {},
    }
    snapshot = await AgentHarnessSnapshotService(repository).build(str(session.id))
    assert snapshot.session.title == "Summarize this very long"
    assert snapshot.entries[0].payload.parts[0].text == prompt
    persisted = await repository.get_session(str(session.id))
    assert persisted is not None
    assert persisted.prompt_snapshot == {"system": "stable"}
