from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import patch

import pytest

from app.services.agent_harness.contracts import (
    InputTextPart,
    MessageCommand,
    OpenSessionRequest,
    RespondCommand,
)
from app.services.agent_harness.harness import AgentHarness
from app.services.agent_harness.loop import HARNESS_VERSION
from app.services.agent_harness.recovery import create_checkpoint
from app.services.agent_harness.workspace_runtime import (
    LocalWorkspaceBackend,
    WorkspaceRuntime,
)
from app.services.model_runtime.contracts import (
    CompletionMetadata,
    ModelEvent,
    TextDelta,
    ToolCallDelta,
)


def _model_snapshot(name: str) -> dict:
    return {
        "target": {
            "endpoint_id": f"endpoint-{name}",
            "provider_kind": "openai",
            "model_name": name,
            "target_revision": f"revision-{name}",
        },
        "capabilities": {
            "supports_vision": True,
            "supports_reasoning": True,
            "supports_tools": True,
        },
    }


class _ScriptedModel:
    def __init__(self, *responses: tuple[ModelEvent, ...]) -> None:
        self.responses = list(responses)

    async def invoke(self, _invocation) -> AsyncIterator[ModelEvent]:
        for event in self.responses.pop(0):
            yield event


def _workspace(root: Path, session) -> WorkspaceRuntime:
    return WorkspaceRuntime(
        LocalWorkspaceBackend(
            working_directory=root,
            read_roots=(root,),
            write_roots=(root,),
            sandbox_runner=None,
        ),
        permission_mode=session.permission_mode,
        workspace_access=session.workspace_access,
    )


@pytest.mark.asyncio
async def test_active_run_keeps_its_turn_config_when_thread_settings_change(
    async_client,
) -> None:
    from app.repositories.agent_harness_repo import AgentHarnessRepository
    import app.database as app_database

    initial_model = _model_snapshot("gpt-initial")
    next_model = _model_snapshot("gpt-next")
    with patch(
        "app.api.v1.agent.resolve_model_snapshot",
        side_effect=[initial_model, next_model],
    ):
        created = await async_client.post(
            "/api/v1/agent/sessions",
            json={"permission_mode": "ask_dangerous"},
        )
        session_id = created.json()["data"]["session"]["id"]

        async with app_database.async_session_maker() as db:
            repository = AgentHarnessRepository(db)
            run = await repository.create_run(session_id)
            run_id = str(run.id)

        updated = await async_client.patch(
            f"/api/v1/agent/sessions/{session_id}",
            json={
                "provider": "openai",
                "model": "gpt-next",
                "permission_mode": "full_access",
            },
        )

    assert updated.status_code == 200
    session = updated.json()["data"]["session"]
    assert session["model"]["model"] == "gpt-next"
    assert session["permission_mode"] == "full_access"

    async with app_database.async_session_maker() as db:
        persisted = await AgentHarnessRepository(db).get_run(run_id)

    assert persisted is not None
    assert persisted.turn_execution_config == {
        "settings_revision": 1,
        "model": initial_model,
        "permission_mode": "ask_dangerous",
        "workspace_access": "read_write",
        "environment_scope": {
            "mode": "auto",
            "environment_ids": ["local"],
        },
        "environment_targets": {},
    }


@pytest.mark.asyncio
async def test_queued_message_uses_latest_thread_settings_when_its_run_starts(
    harness_db,
) -> None:
    from app.repositories.agent_harness_repo import AgentHarnessRepository
    from app.services.agent_harness.contracts import MessageCommand, OpenSessionRequest

    repository = AgentHarnessRepository(harness_db)
    initial_model = _model_snapshot("gpt-initial")
    next_model = _model_snapshot("gpt-next")
    session = await repository.open_session(
        OpenSessionRequest(
            user_id="user-1",
            workspace_id="30000000-0000-0000-0000-000000000001",
            project_id=None,
            title=None,
            model=initial_model,
            workspace={"runtime": "local", "root": "/tmp/workspace"},
            permission_mode="ask_dangerous",
            workspace_access="read_write",
            prompt_snapshot={"content": "stable"},
        )
    )
    session_id = str(session.id)
    active = await repository.create_run(session_id)

    queued = MessageCommand(
        command_id="queued-message",
        parts=[{"type": "text", "text": "run later"}],
    )
    run, entry, inserted = await repository.submit_user_command(session_id, queued)
    assert (run, entry, inserted) == (None, None, True)

    await repository.update_session_settings(
        session_id,
        model_snapshot=next_model,
        permission_mode="full_access",
    )
    await repository.update_run(str(active.id), status="completed")

    started = await repository.create_run_from_next_session_command(
        session_id,
        kind="message",
    )

    assert started is not None
    next_run, _ = started
    assert next_run.turn_execution_config == {
        "settings_revision": 2,
        "model": next_model,
        "permission_mode": "full_access",
        "workspace_access": "read_write",
        "environment_scope": {
            "mode": "auto",
            "environment_ids": ["local"],
        },
        "environment_targets": {},
    }


@pytest.mark.asyncio
async def test_waiting_run_resume_keeps_workspace_settings_from_run_snapshot(
    harness_db,
    tmp_path,
) -> None:
    observed_settings: list[tuple[str, str, int]] = []

    def workspace_factory(session) -> WorkspaceRuntime:
        observed_settings.append(
            (
                session.permission_mode,
                session.workspace_access,
                session.settings_revision,
            )
        )
        return _workspace(tmp_path, session)

    model = _ScriptedModel(
        (
            ToolCallDelta(
                index=0,
                call_id="ask-1",
                name="ask_user",
                arguments_delta=(
                    '{"questions":[{"question":"Continue?","header":"Continue",'
                    '"options":[{"label":"Yes","description":"Continue"},'
                    '{"label":"No","description":"Stop"}]}]}'
                ),
            ),
            CompletionMetadata(response_id="response-1", finish_reason="tool_calls"),
        ),
        (
            TextDelta(text="Done."),
            CompletionMetadata(response_id="response-2", finish_reason="stop"),
        ),
    )
    harness = AgentHarness.for_database(
        harness_db,
        model_gateway=model,
        workspace_factory=workspace_factory,
    )
    opened = await harness.open_session(
        OpenSessionRequest(
            user_id="user-1",
            workspace_id="30000000-0000-0000-0000-000000000001",
            model=_model_snapshot("gpt-initial"),
            workspace={"runtime": "local", "root": str(tmp_path)},
            permission_mode="ask_dangerous",
            workspace_access="read_only",
            prompt_snapshot={"content": "stable"},
        )
    )
    session_id = str(opened.session.id)

    await harness.dispatch(
        session_id,
        MessageCommand(
            command_id="start",
            parts=[InputTextPart(text="Ask before continuing.")],
        ),
    )
    waiting = await harness.snapshot(session_id)
    assert waiting.active_run is not None
    run_id = str(waiting.active_run.run.id)

    await harness.repository.update_session_settings(
        session_id,
        permission_mode="full_access",
        workspace_access="read_write",
    )
    await harness.dispatch(
        session_id,
        RespondCommand(
            command_id="answer",
            interaction_id="tool:ask-1",
            response={"type": "ask_user", "answers": {"Continue?": "Yes"}},
        ),
    )

    completed = await harness.repository.get_run(run_id)
    assert completed is not None
    assert completed.status == "completed"
    assert observed_settings
    assert set(observed_settings) == {("ask_dangerous", "read_only", 1)}


@pytest.mark.asyncio
async def test_recovery_workspace_uses_run_snapshot_after_thread_settings_change(
    harness_db,
    tmp_path,
) -> None:
    observed_settings: list[tuple[str, str, int]] = []

    def workspace_factory(session) -> WorkspaceRuntime:
        observed_settings.append(
            (
                session.permission_mode,
                session.workspace_access,
                session.settings_revision,
            )
        )
        return _workspace(tmp_path, session)

    harness = AgentHarness.for_database(
        harness_db,
        model_gateway=_ScriptedModel(
            (
                TextDelta(text="Recovered."),
                CompletionMetadata(
                    response_id="response-recovered", finish_reason="stop"
                ),
            )
        ),
        workspace_factory=workspace_factory,
    )
    opened = await harness.open_session(
        OpenSessionRequest(
            user_id="user-1",
            workspace_id="30000000-0000-0000-0000-000000000001",
            model=_model_snapshot("gpt-initial"),
            workspace={"runtime": "local", "root": str(tmp_path)},
            permission_mode="ask_dangerous",
            workspace_access="read_only",
            prompt_snapshot={"content": "stable"},
        )
    )
    session_id = str(opened.session.id)
    run = await harness.repository.create_run(session_id)
    assistant = await harness.repository.append_entry(
        session_id,
        run_id=str(run.id),
        entry_type="message",
        payload={
            "role": "assistant",
            "parts": [
                {
                    "id": "tool-call:bash-1",
                    "type": "tool_call",
                    "call_id": "bash-1",
                    "group_id": "assistant-1",
                    "execution_mode": "serial",
                    "name": "bash",
                    "display_name": "bash",
                    "category": "command",
                    "summary": "bash",
                    "arguments": {"command": "touch marker.txt"},
                }
            ],
        },
    )
    await harness.repository.update_run(
        str(run.id),
        status="running",
        phase="tools",
        checkpoint=create_checkpoint(
            harness_version=HARNESS_VERSION,
            phase="tools",
            history_revision=assistant.sequence,
            in_flight_tools=(
                {
                    "call_id": "bash-1",
                    "group_id": "assistant-1",
                    "execution_mode": "serial",
                    "name": "bash",
                    "arguments": {"command": "touch marker.txt"},
                    "replay_policy": "never",
                },
            ),
        ),
    )
    await harness.repository.update_session_settings(
        session_id,
        permission_mode="full_access",
        workspace_access="read_write",
    )

    assert await harness.recover() == 1

    recovered = await harness.repository.get_run(str(run.id))
    assert recovered is not None
    assert recovered.status == "waiting_user"
    assert observed_settings
    assert set(observed_settings) == {("ask_dangerous", "read_only", 1)}


@pytest.mark.asyncio
async def test_started_run_model_resolution_uses_its_snapshot_not_latest_thread_model(
    harness_db,
    tmp_path,
) -> None:
    initial_model = _model_snapshot("gpt-initial")
    next_model = _model_snapshot("gpt-next")
    resolved_models: list[dict | None] = []

    async def resolve_runtime(session) -> dict:
        resolved_models.append(session.model_snapshot)
        snapshot = session.model_snapshot or {}
        target = snapshot["target"]
        return {
            "endpoint_id": target["endpoint_id"],
            "provider": target["provider_kind"],
            "model": target["model_name"],
            "target_revision": target["target_revision"],
            "capabilities": snapshot["capabilities"],
        }

    harness = AgentHarness.for_database(
        harness_db,
        model_gateway=_ScriptedModel(
            (
                TextDelta(text="Done."),
                CompletionMetadata(response_id="response-1", finish_reason="stop"),
            )
        ),
        workspace_factory=lambda session: _workspace(tmp_path, session),
        model_runtime_resolver=resolve_runtime,
    )
    opened = await harness.open_session(
        OpenSessionRequest(
            user_id="user-1",
            workspace_id="30000000-0000-0000-0000-000000000001",
            model=initial_model,
            workspace={"runtime": "local", "root": str(tmp_path)},
            permission_mode="ask_dangerous",
            workspace_access="read_only",
            prompt_snapshot={"content": "stable"},
        )
    )
    session_id = str(opened.session.id)
    run = await harness.repository.create_run(session_id)
    await harness.repository.update_session_settings(
        session_id,
        model_snapshot=next_model,
        permission_mode="full_access",
        workspace_access="read_write",
    )

    await harness.drive_run(session_id, str(run.id))

    completed = await harness.repository.get_run(str(run.id))
    assert completed is not None
    assert completed.status == "completed"
    assert resolved_models == [initial_model]
