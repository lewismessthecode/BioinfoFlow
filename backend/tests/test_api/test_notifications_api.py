from __future__ import annotations

from uuid import uuid4

import pytest

from app.models.project import Project


@pytest.mark.asyncio
async def test_notification_crud(async_client, db_session, tmp_path):
    """Create, list, and delete a notification config."""
    workspace = tmp_path / "notif_ws"
    workspace.mkdir()

    project = Project(
        name="Notif Project", storage_mode="external", external_root_path=str(workspace), user_id="dev"
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)

    # Create
    payload = {
        "project_id": str(project.id),
        "channel": "webhook",
        "trigger": "on_complete",
        "config": {"url": "https://example.com/hook"},
        "enabled": True,
    }
    create_resp = await async_client.post("/api/v1/notifications", json=payload)
    assert create_resp.status_code == 201

    body = create_resp.json()
    assert body["success"] is True

    config_data = body["data"]
    assert config_data["project_id"] == str(project.id)
    assert config_data["channel"] == "webhook"
    assert config_data["trigger"] == "on_complete"
    assert config_data["config"] == {"url": "https://example.com/hook"}
    assert config_data["enabled"] is True
    notification_id = config_data["id"]

    # List all
    list_resp = await async_client.get("/api/v1/notifications")
    assert list_resp.status_code == 200

    list_body = list_resp.json()
    assert list_body["success"] is True
    assert any(c["id"] == notification_id for c in list_body["data"])

    # Delete
    delete_resp = await async_client.delete(f"/api/v1/notifications/{notification_id}")
    assert delete_resp.status_code == 200
    assert delete_resp.json()["data"]["deleted"] is True

    # Verify deleted — list should no longer contain it
    list_after = await async_client.get("/api/v1/notifications")
    assert not any(c["id"] == notification_id for c in list_after.json()["data"])


@pytest.mark.asyncio
async def test_notification_create_missing_project_returns_404(async_client):
    """Creating a config for a non-existent project returns 404."""
    payload = {
        "project_id": str(uuid4()),
        "channel": "webhook",
        "trigger": "on_complete",
        "config": {"url": "https://example.com/hook"},
    }
    resp = await async_client.post("/api/v1/notifications", json=payload)
    assert resp.status_code == 404
    assert resp.json()["success"] is False
    assert resp.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_notification_create_unsupported_channel_returns_422(
    async_client, db_session, tmp_path
):
    """Creating a config with an unsupported channel returns 422."""
    workspace = tmp_path / "notif_channel_ws"
    workspace.mkdir()

    project = Project(
        name="Notif Channel Project", storage_mode="external", external_root_path=str(workspace), user_id="dev"
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)

    # The schema only allows "webhook" as a channel value, so pydantic
    # validation rejects anything else before the service even runs.
    payload = {
        "project_id": str(project.id),
        "channel": "email",
        "trigger": "on_complete",
        "config": {"url": "https://example.com/hook"},
    }
    resp = await async_client.post("/api/v1/notifications", json=payload)
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_notification_create_missing_webhook_url_returns_422(
    async_client, db_session, tmp_path
):
    """Creating a webhook config without a URL returns 422."""
    workspace = tmp_path / "notif_url_ws"
    workspace.mkdir()

    project = Project(
        name="Notif URL Project", storage_mode="external", external_root_path=str(workspace), user_id="dev"
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)

    payload = {
        "project_id": str(project.id),
        "channel": "webhook",
        "trigger": "on_complete",
        "config": {},
    }
    resp = await async_client.post("/api/v1/notifications", json=payload)
    assert resp.status_code == 422
    assert resp.json()["success"] is False
    assert resp.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_notification_list_filters_by_project(async_client, db_session, tmp_path):
    """Listing configs with project_id filter returns only that project's configs."""
    ws_a = tmp_path / "notif_proj_a"
    ws_a.mkdir()
    ws_b = tmp_path / "notif_proj_b"
    ws_b.mkdir()

    project_a = Project(name="Notif Filter A", storage_mode="external", external_root_path=str(ws_a), user_id="dev")
    project_b = Project(name="Notif Filter B", storage_mode="external", external_root_path=str(ws_b), user_id="dev")
    db_session.add_all([project_a, project_b])
    await db_session.commit()
    await db_session.refresh(project_a)
    await db_session.refresh(project_b)

    for proj in (project_a, project_b):
        await async_client.post(
            "/api/v1/notifications",
            json={
                "project_id": str(proj.id),
                "channel": "webhook",
                "trigger": "on_complete",
                "config": {"url": "https://example.com/hook"},
            },
        )

    resp = await async_client.get(f"/api/v1/notifications?project_id={project_a.id}")
    assert resp.status_code == 200

    data = resp.json()["data"]
    assert len(data) >= 1
    assert all(c["project_id"] == str(project_a.id) for c in data)


@pytest.mark.asyncio
async def test_notification_delete_nonexistent_returns_404(async_client):
    """Deleting a notification that does not exist returns 404."""
    resp = await async_client.delete(f"/api/v1/notifications/{uuid4()}")
    assert resp.status_code == 404
    assert resp.json()["success"] is False
    assert resp.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_notification_create_all_triggers(async_client, db_session, tmp_path):
    """All supported trigger values can be used to create configs."""
    workspace = tmp_path / "notif_triggers_ws"
    workspace.mkdir()

    project = Project(
        name="Notif Triggers Project", storage_mode="external", external_root_path=str(workspace), user_id="dev"
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)

    for trigger in ("on_complete", "on_failure", "on_batch_complete"):
        resp = await async_client.post(
            "/api/v1/notifications",
            json={
                "project_id": str(project.id),
                "channel": "webhook",
                "trigger": trigger,
                "config": {"url": f"https://example.com/{trigger}"},
            },
        )
        assert resp.status_code == 201
        assert resp.json()["data"]["trigger"] == trigger
