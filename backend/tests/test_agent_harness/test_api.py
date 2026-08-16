from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from uuid import uuid4

import pytest


@pytest.mark.asyncio
async def test_session_create_reports_a_stable_code_when_no_model_is_available(
    async_client,
) -> None:
    response = await async_client.post("/api/v1/agent/sessions", json={})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "AGENT_MODEL_REQUIRED"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {"unexpected": True},
        {"provider": "openai"},
        {"model": "gpt-5.6"},
        {"provider": "", "model": "gpt-5.6"},
        {"provider": "openai", "model": ""},
        {"provider": "   ", "model": "gpt-5.6"},
        {"provider": "openai", "model": "   "},
        {"model_id": str(uuid4()), "profile_id": str(uuid4())},
        {
            "model_id": str(uuid4()),
            "provider": "openai",
            "model": "gpt-5.6",
        },
        {
            "profile_id": str(uuid4()),
            "provider": "openai",
            "model": "gpt-5.6",
        },
    ],
)
async def test_session_create_rejects_invalid_model_selector_combinations(
    async_client,
    payload: dict,
) -> None:
    with patch(
        "app.api.v1.agent.resolve_model_snapshot",
        return_value={"target": {"model_name": "fake"}},
    ) as resolve:
        response = await async_client.post("/api/v1/agent/sessions", json=payload)

    assert response.status_code == 422
    resolve.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("payload", "expected_selection"),
    [
        ({}, None),
        (
            {"model_id": "00000000-0000-0000-0000-000000000001"},
            {"model_id": "00000000-0000-0000-0000-000000000001"},
        ),
        (
            {"profile_id": "00000000-0000-0000-0000-000000000002"},
            {"profile_id": "00000000-0000-0000-0000-000000000002"},
        ),
        (
            {"provider": "openai", "model": "gpt-5.6"},
            {"provider": "openai", "model": "gpt-5.6"},
        ),
    ],
)
async def test_session_create_passes_one_explicit_model_selection(
    async_client,
    payload: dict,
    expected_selection: dict | None,
) -> None:
    with patch(
        "app.api.v1.agent.resolve_model_snapshot",
        return_value={"target": {"model_name": "fake"}},
    ) as resolve:
        response = await async_client.post("/api/v1/agent/sessions", json=payload)

    assert response.status_code == 201
    assert resolve.await_args.kwargs["selection"] == expected_selection


@pytest.mark.asyncio
async def test_session_create_and_summary_expose_permission_and_workspace_access(
    async_client,
) -> None:
    with patch(
        "app.api.v1.agent.resolve_model_snapshot",
        return_value={"target": {"model_name": "fake"}},
    ):
        created = await async_client.post(
            "/api/v1/agent/sessions",
            json={
                "permission_mode": "ask_changes",
                "workspace_access": "read_only",
            },
        )

    assert created.status_code == 201
    snapshot = created.json()["data"]
    assert "history_revision" not in snapshot
    session = snapshot["session"]
    assert session["permission_mode"] == "ask_changes"
    assert session["workspace_access"] == "read_only"

    listed = await async_client.get("/api/v1/agent/sessions")

    assert listed.status_code == 200
    summary = next(item for item in listed.json()["data"] if item["id"] == session["id"])
    assert summary["permission_mode"] == "ask_changes"
    assert summary["workspace_access"] == "read_only"
    assert "history_revision" not in summary


@pytest.mark.asyncio
async def test_session_snapshot_exposes_only_safe_model_summary(async_client) -> None:
    private_snapshot = {
        "target": {
            "endpoint_id": "provider-record",
            "provider_kind": "openai",
            "model_name": "gpt-5.6",
            "base_url": "https://private.example/v1",
            "target_revision": "secret-revision",
        },
        "capabilities": {
            "supports_vision": True,
            "supports_reasoning": True,
            "supports_tools": True,
        },
    }
    with patch(
        "app.api.v1.agent.resolve_model_snapshot",
        return_value=private_snapshot,
    ):
        created = await async_client.post("/api/v1/agent/sessions", json={})

    assert created.status_code == 201
    session = created.json()["data"]["session"]
    assert session["model"] == {
        "catalog_model_id": None,
        "provider": "openai",
        "model": "gpt-5.6",
        "display_name": "gpt-5.6",
        "supports_vision": True,
        "supports_reasoning": True,
        "supports_tools": True,
    }
    assert "private.example" not in repr(session)
    assert "secret-revision" not in repr(session)


@pytest.mark.asyncio
async def test_session_patch_updates_settings_and_publishes_authoritative_snapshot(
    async_client,
) -> None:
    from app.services.agent_harness.runtime import agent_runtime

    with patch(
        "app.api.v1.agent.resolve_model_snapshot",
        return_value={"target": {"model_name": "fake"}},
    ):
        created = await async_client.post(
            "/api/v1/agent/sessions",
            json={"title": "Before"},
        )
    session_id = created.json()["data"]["session"]["id"]
    events = agent_runtime.events(session_id)
    initial = await anext(events)

    updated = await async_client.patch(
        f"/api/v1/agent/sessions/{session_id}",
        json={
            "title": "After",
            "permission_mode": "ask_changes",
            "workspace_access": "read_only",
        },
    )
    published = await asyncio.wait_for(anext(events), timeout=1)
    await events.aclose()

    assert initial.type == "snapshot"
    assert updated.status_code == 200
    snapshot = updated.json()["data"]
    assert snapshot["session"]["title"] == "After"
    assert snapshot["session"]["permission_mode"] == "ask_changes"
    assert snapshot["session"]["workspace_access"] == "read_only"
    assert published.type == "snapshot"
    assert published.snapshot.session.title == "After"
    assert published.snapshot.session.permission_mode == "ask_changes"
    assert published.snapshot.session.workspace_access == "read_only"


@pytest.mark.asyncio
async def test_session_snapshot_has_one_canonical_get_route(async_client) -> None:
    with patch(
        "app.api.v1.agent.resolve_model_snapshot",
        return_value={"target": {"model_name": "fake"}},
    ):
        created = await async_client.post("/api/v1/agent/sessions", json={})
    session_id = created.json()["data"]["session"]["id"]

    duplicate = await async_client.get(f"/api/v1/agent/sessions/{session_id}")
    snapshot = await async_client.get(
        f"/api/v1/agent/sessions/{session_id}/snapshot"
    )

    assert duplicate.status_code == 405
    assert snapshot.status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {"title": "After", "permission_mode": "full_access"},
        {"title": "After", "workspace_access": "read_only"},
    ],
)
async def test_session_patch_rejects_policy_changes_atomically_during_active_run(
    async_client,
    payload: dict,
) -> None:
    from app.repositories.agent_harness_repo import AgentHarnessRepository
    import app.database as app_database

    with patch(
        "app.api.v1.agent.resolve_model_snapshot",
        return_value={"target": {"model_name": "fake"}},
    ):
        created = await async_client.post(
            "/api/v1/agent/sessions",
            json={"title": "Before"},
        )
    session_id = created.json()["data"]["session"]["id"]
    async with app_database.async_session_maker() as db:
        await AgentHarnessRepository(db).create_run(session_id)

    response = await async_client.patch(
        f"/api/v1/agent/sessions/{session_id}",
        json=payload,
    )
    current = await async_client.get(
        f"/api/v1/agent/sessions/{session_id}/snapshot"
    )

    assert response.status_code == 409
    session = current.json()["data"]["session"]
    assert session["title"] == "Before"
    assert session["permission_mode"] == "ask_dangerous"
    assert session["workspace_access"] == "read_write"


@pytest.mark.asyncio
async def test_session_patch_allows_title_change_during_active_run(async_client) -> None:
    from app.repositories.agent_harness_repo import AgentHarnessRepository
    import app.database as app_database

    with patch(
        "app.api.v1.agent.resolve_model_snapshot",
        return_value={"target": {"model_name": "fake"}},
    ):
        created = await async_client.post(
            "/api/v1/agent/sessions",
            json={"title": "Before"},
        )
    session_id = created.json()["data"]["session"]["id"]
    async with app_database.async_session_maker() as db:
        await AgentHarnessRepository(db).create_run(session_id)

    response = await async_client.patch(
        f"/api/v1/agent/sessions/{session_id}",
        json={"title": None},
    )

    assert response.status_code == 200
    assert response.json()["data"]["session"]["title"] is None


@pytest.mark.asyncio
async def test_session_patch_allows_next_run_permission_when_active_run_is_frozen(
    async_client,
) -> None:
    from app.repositories.agent_harness_repo import AgentHarnessRepository
    import app.database as app_database

    with patch(
        "app.api.v1.agent.resolve_model_snapshot",
        return_value={"target": {"model_name": "fake"}},
    ):
        created = await async_client.post(
            "/api/v1/agent/sessions",
            json={"title": "Before"},
        )
    session_id = created.json()["data"]["session"]["id"]
    async with app_database.async_session_maker() as db:
        await AgentHarnessRepository(db).create_run(
            session_id,
            settings_snapshot={
                "model_snapshot": {"target": {"model_name": "fake"}},
                "permission_mode": "ask_dangerous",
                "execution_scope": {"mode": "auto", "target_ids": []},
                "allowed_targets": [],
            },
        )

    response = await async_client.patch(
        f"/api/v1/agent/sessions/{session_id}",
        json={"permission_mode": "full_access"},
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["session"]["permission_mode"] == "full_access"
    assert payload["active_run"]["run"]["settings"]["permission_mode"] == (
        "ask_dangerous"
    )


@pytest.mark.asyncio
async def test_session_patch_updates_next_run_model_without_rewriting_active_run(
    async_client,
) -> None:
    from app.repositories.agent_harness_repo import AgentHarnessRepository
    import app.database as app_database

    initial_snapshot = {
        "model_id": "00000000-0000-0000-0000-000000000001",
        "target": {"provider_kind": "openai", "model_name": "gpt-old"},
    }
    next_snapshot = {
        "model_id": "00000000-0000-0000-0000-000000000002",
        "target": {"provider_kind": "openai", "model_name": "gpt-new"},
    }
    with patch(
        "app.api.v1.agent.resolve_model_snapshot",
        return_value=initial_snapshot,
    ):
        created = await async_client.post("/api/v1/agent/sessions", json={})
    session_id = created.json()["data"]["session"]["id"]
    async with app_database.async_session_maker() as db:
        await AgentHarnessRepository(db).create_run(
            session_id,
            settings_snapshot={
                "model_snapshot": initial_snapshot,
                "permission_mode": "ask_dangerous",
                "execution_scope": {"mode": "auto", "target_ids": []},
                "allowed_targets": [],
            },
        )

    with patch(
        "app.api.v1.agent.resolve_model_snapshot",
        return_value=next_snapshot,
    ) as resolve:
        response = await async_client.patch(
            f"/api/v1/agent/sessions/{session_id}",
            json={"model_id": next_snapshot["model_id"]},
        )

    assert response.status_code == 200
    resolve.assert_awaited_once()
    assert resolve.await_args.kwargs["selection"] == {
        "model_id": next_snapshot["model_id"]
    }
    payload = response.json()["data"]
    assert payload["session"]["model"]["model"] == "gpt-new"
    assert payload["session"]["model"]["catalog_model_id"] == next_snapshot["model_id"]
    assert payload["active_run"]["run"]["settings"]["model"]["model"] == "gpt-old"


@pytest.mark.asyncio
async def test_session_patch_rejects_ambiguous_model_selector(async_client) -> None:
    with patch(
        "app.api.v1.agent.resolve_model_snapshot",
        return_value={"target": {"model_name": "fake"}},
    ):
        created = await async_client.post("/api/v1/agent/sessions", json={})
    session_id = created.json()["data"]["session"]["id"]

    response = await async_client.patch(
        f"/api/v1/agent/sessions/{session_id}",
        json={
            "model_id": "00000000-0000-0000-0000-000000000002",
            "provider": "openai",
            "model": "gpt-new",
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_session_patch_archives_and_unarchives_idle_session(async_client) -> None:
    with patch(
        "app.api.v1.agent.resolve_model_snapshot",
        return_value={"target": {"model_name": "fake"}},
    ):
        created = await async_client.post("/api/v1/agent/sessions", json={})
    session_id = created.json()["data"]["session"]["id"]

    archived = await async_client.patch(
        f"/api/v1/agent/sessions/{session_id}",
        json={"status": "archived"},
    )
    unarchived = await async_client.patch(
        f"/api/v1/agent/sessions/{session_id}",
        json={"status": "active"},
    )

    assert archived.status_code == 200
    assert archived.json()["data"]["session"]["status"] == "archived"
    assert unarchived.status_code == 200
    assert unarchived.json()["data"]["session"]["status"] == "active"


@pytest.mark.asyncio
async def test_session_patch_rejects_archive_atomically_during_active_run(
    async_client,
) -> None:
    from app.repositories.agent_harness_repo import AgentHarnessRepository
    import app.database as app_database

    with patch(
        "app.api.v1.agent.resolve_model_snapshot",
        return_value={"target": {"model_name": "fake"}},
    ):
        created = await async_client.post(
            "/api/v1/agent/sessions",
            json={"title": "Before"},
        )
    session_id = created.json()["data"]["session"]["id"]
    async with app_database.async_session_maker() as db:
        await AgentHarnessRepository(db).create_run(session_id)

    response = await async_client.patch(
        f"/api/v1/agent/sessions/{session_id}",
        json={"title": "After", "status": "archived"},
    )
    current = await async_client.get(
        f"/api/v1/agent/sessions/{session_id}/snapshot"
    )

    assert response.status_code == 409
    assert current.json()["data"]["session"]["status"] == "active"
    assert current.json()["data"]["session"]["title"] == "Before"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"permission_mode": None},
        {"workspace_access": None},
    ],
)
async def test_session_patch_requires_at_least_one_valid_setting(
    async_client,
    payload: dict,
) -> None:
    with patch(
        "app.api.v1.agent.resolve_model_snapshot",
        return_value={"target": {"model_name": "fake"}},
    ):
        created = await async_client.post("/api/v1/agent/sessions", json={})
    session_id = created.json()["data"]["session"]["id"]

    response = await async_client.patch(
        f"/api/v1/agent/sessions/{session_id}",
        json=payload,
    )

    assert response.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reference_type",
    ["attachment_ref", "file_ref", "directory_ref"],
)
async def test_message_command_rejects_attachment_from_another_session(
    async_client,
    reference_type: str,
) -> None:
    with patch(
        "app.api.v1.agent.resolve_model_snapshot",
        return_value={"target": {"model_name": "fake"}},
    ):
        source = await async_client.post("/api/v1/agent/sessions", json={})
        target = await async_client.post("/api/v1/agent/sessions", json={})
    source_id = source.json()["data"]["session"]["id"]
    target_id = target.json()["data"]["session"]["id"]
    uploaded = await async_client.post(
        f"/api/v1/agent/sessions/{source_id}/attachments",
        data={"kind": "file", "source": "upload"},
        files={"files": ("private.txt", b"private", "text/plain")},
    )
    attachment_id = uploaded.json()["data"][0]["id"]

    with patch("app.api.v1.agent.agent_runtime.dispatch", return_value=None) as dispatch:
        response = await async_client.post(
            f"/api/v1/agent/sessions/{target_id}/commands",
            json={
                "type": "message",
                "command_id": "message-with-foreign-attachment",
                "parts": [
                    {"type": "text", "text": "read this"},
                    {"type": reference_type, "attachment_id": attachment_id},
                ],
            },
        )

    assert response.status_code == 404
    dispatch.assert_not_awaited()


@pytest.mark.asyncio
async def test_message_command_rejects_project_path_traversal(
    async_client,
    db_session,
    tmp_path,
) -> None:
    from app.models.project import Project

    workspace = tmp_path / "project"
    workspace.mkdir()
    project = Project(
        name="agent-context-path-project",
        storage_mode="external",
        external_root_path=str(workspace),
        user_id="dev",
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)
    with patch(
        "app.api.v1.agent.resolve_model_snapshot",
        return_value={"target": {"model_name": "fake"}},
    ):
        created = await async_client.post("/api/v1/agent/sessions", json={})
    session_id = created.json()["data"]["session"]["id"]

    with patch("app.api.v1.agent.agent_runtime.dispatch", return_value=None) as dispatch:
        response = await async_client.post(
            f"/api/v1/agent/sessions/{session_id}/commands",
            json={
                "type": "message",
                "command_id": "path-traversal",
                "parts": [
                    {
                        "type": "file_ref",
                        "project_id": str(project.id),
                        "path": "../secret.txt",
                    }
                ],
            },
        )

    assert response.status_code == 404
    dispatch.assert_not_awaited()


@pytest.mark.asyncio
async def test_message_command_accepts_run_ref_only_from_the_session_project(
    async_client,
    db_session,
) -> None:
    from app.models.run import Run, RunStatus
    from tests.support.path_contract import bind_workflow, create_project, create_workflow

    current_project = await create_project(
        db_session,
        name="agent-current-project",
    )
    other_project = await create_project(
        db_session,
        name="agent-other-project",
    )
    workflow = await create_workflow(
        db_session,
        name="agent-run-reference-workflow",
        content="workflow { }\n",
    )
    current_run = Run(
        run_id="agent-current-project-run",
        project_id=str(current_project.id),
        workflow_id=str(workflow.id),
        status=RunStatus.COMPLETED.value,
        config={},
        samples_count=0,
        tasks_total=0,
        tasks_completed=0,
    )
    other_run = Run(
        run_id="agent-other-project-run",
        project_id=str(other_project.id),
        workflow_id=str(workflow.id),
        status=RunStatus.COMPLETED.value,
        config={},
        samples_count=0,
        tasks_total=0,
        tasks_completed=0,
    )
    db_session.add_all((current_run, other_run))
    await db_session.commit()
    await bind_workflow(
        db_session,
        project_id=str(other_project.id),
        workflow_id=str(workflow.id),
    )

    with patch(
        "app.api.v1.agent.resolve_model_snapshot",
        return_value={"target": {"model_name": "fake"}},
    ):
        created = await async_client.post(
            "/api/v1/agent/sessions",
            json={"project_id": str(current_project.id)},
        )
    session_id = created.json()["data"]["session"]["id"]

    with patch("app.api.v1.agent.agent_runtime.dispatch", return_value=None) as dispatch:
        rejected = await async_client.post(
            f"/api/v1/agent/sessions/{session_id}/commands",
            json={
                "type": "message",
                "command_id": "foreign-project-run",
                "parts": [
                    {"type": "run_ref", "run_id": other_run.run_id},
                ],
            },
        )
        rejected_after_foreign_workflow = await async_client.post(
            f"/api/v1/agent/sessions/{session_id}/commands",
            json={
                "type": "message",
                "command_id": "foreign-workflow-and-run",
                "parts": [
                    {
                        "type": "workflow_ref",
                        "scope": "project",
                        "project_id": str(other_project.id),
                        "workflow_id": str(workflow.id),
                    },
                    {"type": "run_ref", "run_id": other_run.run_id},
                ],
            },
        )
        accepted = await async_client.post(
            f"/api/v1/agent/sessions/{session_id}/commands",
            json={
                "type": "message",
                "command_id": "current-project-run",
                "parts": [
                    {"type": "run_ref", "run_id": current_run.run_id},
                ],
            },
        )

    assert rejected.status_code == 404
    assert rejected_after_foreign_workflow.status_code == 404
    assert accepted.status_code == 202
    dispatch.assert_awaited_once()
    assert dispatch.await_args.args[1].parts[0].run_id == current_run.run_id


@pytest.mark.asyncio
async def test_message_command_rejects_attachment_reference_kind_mismatch(
    async_client,
) -> None:
    with patch(
        "app.api.v1.agent.resolve_model_snapshot",
        return_value={"target": {"model_name": "fake"}},
    ):
        created = await async_client.post("/api/v1/agent/sessions", json={})
    session_id = created.json()["data"]["session"]["id"]
    uploaded = await async_client.post(
        f"/api/v1/agent/sessions/{session_id}/attachments",
        data={"kind": "file", "source": "upload"},
        files={"files": ("sample.txt", b"sample", "text/plain")},
    )
    attachment_id = uploaded.json()["data"][0]["id"]

    with patch("app.api.v1.agent.agent_runtime.dispatch", return_value=None) as dispatch:
        response = await async_client.post(
            f"/api/v1/agent/sessions/{session_id}/commands",
            json={
                "type": "message",
                "command_id": "wrong-reference-kind",
                "parts": [
                    {
                        "type": "directory_ref",
                        "attachment_id": attachment_id,
                    }
                ],
            },
        )

    assert response.status_code == 400
    dispatch.assert_not_awaited()


@pytest.mark.asyncio
async def test_session_mutation_locks_are_request_scoped(async_client) -> None:
    from app.api.v1 import agent as agent_api

    agent_api._session_mutation_locks.clear()
    missing = await async_client.post(
        "/api/v1/agent/sessions/00000000-0000-0000-0000-000000000001/commands",
        json={"type": "cancel", "command_id": "cancel-missing"},
    )

    assert missing.status_code == 404
    assert agent_api._session_mutation_locks == {}

    with patch(
        "app.api.v1.agent.resolve_model_snapshot",
        return_value={"target": {"model_name": "fake"}},
    ):
        created = await async_client.post("/api/v1/agent/sessions", json={})
    session_id = created.json()["data"]["session"]["id"]
    with patch("app.api.v1.agent.agent_runtime.dispatch", return_value=None):
        dispatched = await async_client.post(
            f"/api/v1/agent/sessions/{session_id}/commands",
            json={"type": "cancel", "command_id": "cancel-valid"},
        )

    assert dispatched.status_code == 202
    assert agent_api._session_mutation_locks == {}


@pytest.mark.asyncio
async def test_command_body_validation_and_state_conflicts_are_client_errors(
    async_client,
) -> None:
    with patch(
        "app.api.v1.agent.resolve_model_snapshot",
        return_value={"target": {"model_name": "fake"}},
    ):
        created = await async_client.post("/api/v1/agent/sessions", json={})
    session_id = created.json()["data"]["session"]["id"]

    missing_message_parts = await async_client.post(
        f"/api/v1/agent/sessions/{session_id}/commands",
        json={"type": "message", "command_id": "invalid-message"},
    )
    steer_without_run = await async_client.post(
        f"/api/v1/agent/sessions/{session_id}/commands",
        json={
            "type": "steer",
            "command_id": "invalid-steer",
            "parts": [{"type": "text", "text": "now"}],
        },
    )
    respond_without_run = await async_client.post(
        f"/api/v1/agent/sessions/{session_id}/commands",
        json={
            "type": "respond",
            "command_id": "invalid-response",
            "interaction_id": "tool:missing",
            "response": {"type": "approval", "approved": True},
        },
    )

    assert missing_message_parts.status_code == 422
    assert steer_without_run.status_code == 409
    assert respond_without_run.status_code == 409


@pytest.mark.asyncio
async def test_sse_releases_request_database_before_streaming(
    app,
    async_client,
    db_session,
) -> None:
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from app.api.deps import get_db

    with patch(
        "app.api.v1.agent.resolve_model_snapshot",
        return_value={"target": {"model_name": "fake"}},
    ):
        created = await async_client.post("/api/v1/agent/sessions", json={})
    session_id = created.json()["data"]["session"]["id"]

    factory = async_sessionmaker(
        db_session.bind,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    active_sessions = 0
    opened_sessions = 0

    async def tracked_get_db():
        nonlocal active_sessions, opened_sessions
        opened_sessions += 1
        active_sessions += 1
        try:
            async with factory() as session:
                yield session
        finally:
            active_sessions -= 1

    app.dependency_overrides[get_db] = tracked_get_db
    path = f"/api/v1/agent/sessions/{session_id}/events"
    base_scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [
            (b"accept", b"text/event-stream"),
            (b"host", b"test"),
        ],
        "client": ("127.0.0.1", 12345),
        "server": ("test", 80),
    }
    request_messages: list[asyncio.Queue[dict]] = []
    first_events = [asyncio.Event() for _ in range(3)]
    response_statuses: list[int | None] = [None, None, None]
    streaming: list[asyncio.Task] = []
    for index in range(3):
        messages: asyncio.Queue[dict] = asyncio.Queue()
        await messages.put({"type": "http.request", "body": b"", "more_body": False})
        request_messages.append(messages)

        async def receive(queue: asyncio.Queue[dict] = messages) -> dict:
            return await queue.get()

        async def send(message: dict, stream_index: int = index) -> None:
            if message["type"] == "http.response.start":
                response_statuses[stream_index] = message["status"]
            if message["type"] == "http.response.body" and message.get("body"):
                first_events[stream_index].set()

        streaming.append(asyncio.create_task(app(dict(base_scope), receive, send)))
    try:
        await asyncio.wait_for(
            asyncio.gather(*(event.wait() for event in first_events)),
            timeout=1,
        )
        assert response_statuses == [200, 200, 200]
        assert opened_sessions == 3
        assert active_sessions == 0
    finally:
        for messages in request_messages:
            await messages.put({"type": "http.disconnect"})
        await asyncio.wait_for(asyncio.gather(*streaming), timeout=1)


@pytest.mark.asyncio
async def test_session_delete_rejects_upload_from_another_worker_after_closing(
    async_client,
) -> None:
    with patch(
        "app.api.v1.agent.resolve_model_snapshot",
        return_value={"target": {"model_name": "fake"}},
    ):
        created = await async_client.post("/api/v1/agent/sessions", json={})
    session_id = created.json()["data"]["session"]["id"]

    import app.database as app_database
    from app.path_layout import agent_session_attachments_root
    from app.repositories.agent_harness_repo import AgentHarnessRepository

    delete_reached_database = asyncio.Event()
    release_delete = asyncio.Event()
    independent_locks = {
        "delete-worker": asyncio.Lock(),
        "upload-worker": asyncio.Lock(),
    }
    lock_calls = 0

    def independent_worker_lock(_session_id: str) -> asyncio.Lock:
        nonlocal lock_calls
        lock_calls += 1
        worker = "delete-worker" if lock_calls == 1 else "upload-worker"
        return independent_locks[worker]

    async def delayed_delete(target_session_id: str) -> None:
        delete_reached_database.set()
        await release_delete.wait()
        async with app_database.async_session_maker() as db:
            assert await AgentHarnessRepository(db).delete_session(target_session_id)

    with (
        patch(
            "app.api.v1.agent._session_mutation_lock",
            side_effect=independent_worker_lock,
        ),
        patch(
            "app.api.v1.agent.agent_runtime.delete_session",
            side_effect=delayed_delete,
        ),
    ):
        deleting = asyncio.create_task(
            async_client.delete(f"/api/v1/agent/sessions/{session_id}"),
            name="delete-worker",
        )
        await asyncio.wait_for(delete_reached_database.wait(), timeout=1)
        uploading = asyncio.create_task(
            async_client.post(
                f"/api/v1/agent/sessions/{session_id}/attachments",
                data={"kind": "file", "source": "upload"},
                files={"files": ("late.txt", b"late", "text/plain")},
            ),
            name="upload-worker",
        )
        uploaded = await asyncio.wait_for(uploading, timeout=1)
        assert uploaded.status_code == 409
        assert not agent_session_attachments_root(session_id).exists()
        messaged = await async_client.post(
            f"/api/v1/agent/sessions/{session_id}/commands",
            json={
                "type": "message",
                "command_id": "late-message",
                "parts": [{"type": "text", "text": "late"}],
            },
        )
        responded = await async_client.post(
            f"/api/v1/agent/sessions/{session_id}/commands",
            json={
                "type": "respond",
                "command_id": "late-response",
                "interaction_id": "tool:late",
                "response": {"type": "approval", "approved": True},
            },
        )
        assert messaged.status_code == 409
        assert responded.status_code == 409
        release_delete.set()
        deleted = await deleting

    assert deleted.status_code == 204
    assert not agent_session_attachments_root(session_id).exists()


@pytest.mark.asyncio
async def test_concurrent_session_delete_never_restores_files_after_db_delete(
    async_client,
) -> None:
    with patch(
        "app.api.v1.agent.resolve_model_snapshot",
        return_value={"target": {"model_name": "fake"}},
    ):
        created = await async_client.post("/api/v1/agent/sessions", json={})
    session_id = created.json()["data"]["session"]["id"]
    uploaded = await async_client.post(
        f"/api/v1/agent/sessions/{session_id}/attachments",
        data={"kind": "file", "source": "upload"},
        files={"files": ("notes.txt", b"hello", "text/plain")},
    )
    assert uploaded.status_code == 201

    import app.database as app_database
    from app.path_layout import agent_session_attachments_root
    from app.repositories.agent_harness_repo import AgentHarnessRepository

    first_entered = asyncio.Event()
    release_first = asyncio.Event()
    calls = 0

    async def serialized_delete(target_session_id: str) -> None:
        nonlocal calls
        calls += 1
        assert calls == 1
        first_entered.set()
        await release_first.wait()
        async with app_database.async_session_maker() as db:
            assert await AgentHarnessRepository(db).delete_session(target_session_id)

    with patch(
        "app.api.v1.agent.agent_runtime.delete_session",
        side_effect=serialized_delete,
    ):
        first = asyncio.create_task(
            async_client.delete(f"/api/v1/agent/sessions/{session_id}")
        )
        await asyncio.wait_for(first_entered.wait(), timeout=1)
        second_task = asyncio.create_task(
            async_client.delete(f"/api/v1/agent/sessions/{session_id}")
        )
        await asyncio.sleep(0)
        assert not second_task.done()
        release_first.set()
        first_response, second = await asyncio.gather(first, second_task)

    assert first_response.status_code == 204
    assert second.status_code == 404
    assert calls == 1
    assert not agent_session_attachments_root(session_id).exists()


@pytest.mark.asyncio
async def test_agent_api_creates_session_dispatches_message_and_returns_snapshot(
    async_client,
) -> None:
    with (
        patch(
            "app.api.v1.agent.resolve_model_snapshot",
            return_value={"target": {"model_name": "fake"}},
        ),
        patch(
            "app.api.v1.agent.agent_runtime.dispatch",
            return_value=None,
        ),
    ):
        created = await async_client.post(
            "/api/v1/agent/sessions",
            json={"title": "Demo", "permission_mode": "ask_dangerous"},
        )

    assert created.status_code == 201
    session_id = created.json()["data"]["session"]["id"]

    from app.repositories.agent_harness_repo import AgentHarnessRepository
    import app.database as app_database

    async with app_database.async_session_maker() as db:
        session = await AgentHarnessRepository(db).get_session(session_id)
        assert session is not None
        prompt = session.prompt_snapshot["content"]
        assert "## Workspace" in prompt
        assert "## Available tools" in prompt
        assert all(
            f"- {name}:" in prompt
            for name in ("read", "bash", "edit", "write", "ask_user")
        )

    with patch("app.api.v1.agent.agent_runtime.dispatch", return_value=None):
        dispatched = await async_client.post(
            f"/api/v1/agent/sessions/{session_id}/commands",
            json={
                "type": "message",
                "command_id": "message-1",
                "parts": [{"type": "text", "text": "hello"}],
            },
        )
    snapshot = await async_client.get(f"/api/v1/agent/sessions/{session_id}/snapshot")

    assert dispatched.status_code == 202
    assert snapshot.status_code == 200
    assert snapshot.json()["data"]["session"]["id"] == session_id


@pytest.mark.asyncio
async def test_agent_api_preserves_attachment_and_artifact_frontend_contracts(
    async_client,
) -> None:
    with patch(
        "app.api.v1.agent.resolve_model_snapshot",
        return_value={"target": {"model_name": "fake"}},
    ):
        created = await async_client.post("/api/v1/agent/sessions", json={})
    session_id = created.json()["data"]["session"]["id"]

    uploaded = await async_client.post(
        f"/api/v1/agent/sessions/{session_id}/attachments",
        data={"kind": "file", "source": "upload"},
        files={"files": ("notes.txt", b"hello", "text/plain")},
    )

    assert uploaded.status_code == 201
    attachment = uploaded.json()["data"][0]
    assert attachment.keys() >= {
        "id",
        "session_id",
        "workspace_id",
        "user_id",
        "kind",
        "source",
        "filename",
        "mime_type",
        "size_bytes",
        "status",
        "metadata",
        "created_at",
        "updated_at",
    }
    preview = await async_client.get(
        f"/api/v1/agent/attachments/{attachment['id']}/preview"
    )
    assert preview.status_code == 200
    assert preview.content == b"hello"

    from app.repositories.agent_harness_repo import AgentHarnessRepository, RunFence
    from app.services.agent_harness.assets import AgentHarnessArtifactService
    import app.database as app_database

    async with app_database.async_session_maker() as db:
        repository = AgentHarnessRepository(db)
        run = await repository.create_run(session_id)
        generation = await repository.claim_run(
            str(run.id),
            owner="api-test-worker",
            lease_expires_at=datetime.now(timezone.utc) + timedelta(minutes=1),
        )
        assert generation == 1
        artifact_result = await AgentHarnessArtifactService(db).writer(
            session_id=session_id,
            run_id=str(run.id),
            fence=RunFence(owner="api-test-worker", generation=generation),
        )({"type": "command_output", "command": "pytest", "stdout": "ok"})
        artifact_id = artifact_result["artifact_id"]

    artifacts = await async_client.get(f"/api/v1/agent/sessions/{session_id}/artifacts")
    detail = await async_client.get(f"/api/v1/agent/artifacts/{artifact_id}")
    download = await async_client.get(f"/api/v1/agent/artifacts/{artifact_id}/download")

    assert artifacts.status_code == 200
    assert artifacts.json()["data"][0]["id"] == artifact_id
    assert "turn_id" not in artifacts.json()["data"][0]
    assert "action_id" not in artifacts.json()["data"][0]
    assert "file_path" not in artifacts.json()["data"][0]
    assert detail.status_code == 200
    assert detail.json()["data"]["run_id"] == str(run.id)
    assert detail.json()["data"]["resource_ref"].keys() == {
        "kind",
        "filename",
        "mime_type",
        "size_bytes",
        "sha256",
    }
    assert "file_path" not in detail.json()["data"]
    assert download.status_code == 200
    assert download.headers["content-type"] == "application/json"
    assert b'"stdout":"ok"' in download.content

    deleted = await async_client.delete(f"/api/v1/agent/attachments/{attachment['id']}")
    assert deleted.status_code == 200
