from __future__ import annotations

from uuid import UUID

import pytest

from app.models.workspace import Workspace
from app.repositories.agent_harness_repo import AgentHarnessRepository
from app.repositories.agent_trace_repo import AgentModelTraceRepository
from app.services.agent_harness.contracts import OpenSessionRequest


WORKSPACE_ID = UUID("70000000-0000-0000-0000-000000000001")


@pytest.mark.asyncio
async def test_model_trace_repository_preserves_raw_exchange_without_credentials(
    db_session,
) -> None:
    db_session.add(
        Workspace(
            id=str(WORKSPACE_ID),
            name="Trace",
            slug="trace",
            is_default=False,
        )
    )
    await db_session.commit()
    harness = AgentHarnessRepository(db_session)
    session = await harness.open_session(
        OpenSessionRequest(
            user_id="user-1",
            workspace_id=WORKSPACE_ID,
            prompt_snapshot={"schema_version": 1, "content": "System prompt"},
            model={
                "target": {
                    "provider_kind": "openai",
                    "model_name": "gpt-5",
                }
            },
        )
    )
    run = await harness.create_run(
        str(session.id),
        turn_execution_config={
            "settings_revision": 1,
            "model": session.model_snapshot,
            "permission_mode": "ask_dangerous",
            "workspace_access": "read_write",
            "environment_scope": {"mode": "auto", "environment_ids": ["local"]},
        },
    )
    repository = AgentModelTraceRepository(db_session)

    trace = await repository.start(
        session_id=str(session.id),
        run_id=str(run.id),
        iteration=1,
        attempt=1,
        context_through_sequence=0,
        provider="openai",
        model="gpt-5",
        wire_protocol="responses",
        context_snapshot={
            "compacted": False,
            "max_context_tokens": 128000,
            "composition": [{"category": "system", "characters": 13, "tokens": None}],
        },
    )
    await repository.record_request(
        str(trace.id),
        {"model": "gpt-5", "input": [{"role": "user", "content": "hello"}]},
    )
    completed = await repository.complete(
        str(trace.id),
        response_payload={"stream": True, "chunks": [{"type": "response.done"}]},
        usage={
            "input_tokens": 12,
            "output_tokens": 4,
            "total_tokens": 16,
            "cached_input_tokens": None,
            "reasoning_tokens": 2,
        },
        provider_response_id="resp-1",
        finish_reason="completed",
    )

    stored = await repository.get(str(trace.id), session_id=str(session.id))

    assert stored is not None
    assert completed.status == "completed"
    assert stored.request_payload == {
        "model": "gpt-5",
        "input": [{"role": "user", "content": "hello"}],
    }
    assert stored.response_payload == {
        "stream": True,
        "chunks": [{"type": "response.done"}],
    }
    assert stored.usage["cached_input_tokens"] is None
    assert "api_key" not in str(stored.request_payload)
