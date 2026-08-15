from __future__ import annotations

import base64
from unittest.mock import AsyncMock

import pytest

from app.models.agent_harness import AgentHarnessAttachment


PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUB"
    "AScY42YAAAAASUVORK5CYII="
)


@pytest.fixture(autouse=True)
def configured_agent_model(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.api.v1.agent.resolve_model_snapshot",
        AsyncMock(return_value={"target": {"model_name": "test-model"}}),
    )


@pytest.mark.asyncio
async def test_attachment_upload_preview_and_delete_api(async_client) -> None:
    created = await async_client.post("/api/v1/agent/sessions", json={})
    session_id = created.json()["data"]["session"]["id"]

    uploaded = await async_client.post(
        f"/api/v1/agent/sessions/{session_id}/attachments",
        data={"kind": "image"},
        files={"files": ("clipboard.png", PNG_1X1, "image/png")},
    )

    assert uploaded.status_code == 201
    attachment = uploaded.json()["data"][0]
    assert attachment["kind"] == "image"
    assert attachment["source"] == "clipboard"
    assert attachment["mime_type"] == "image/png"

    preview = await async_client.get(
        f"/api/v1/agent/attachments/{attachment['id']}/preview"
    )
    assert preview.status_code == 200
    assert preview.headers["content-type"].startswith("image/png")
    assert preview.content == PNG_1X1

    deleted = await async_client.delete(f"/api/v1/agent/attachments/{attachment['id']}")
    assert deleted.status_code == 200
    missing = await async_client.get(
        f"/api/v1/agent/attachments/{attachment['id']}/preview"
    )
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_attachment_delete_rejects_permanent_history_reference(
    async_client,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "app.services.agent_harness.runtime.agent_runtime._schedule",
        lambda *args, **kwargs: None,
    )
    created = await async_client.post("/api/v1/agent/sessions", json={})
    session_id = created.json()["data"]["session"]["id"]
    uploaded = await async_client.post(
        f"/api/v1/agent/sessions/{session_id}/attachments",
        data={"kind": "image"},
        files={"files": ("history.png", PNG_1X1, "image/png")},
    )
    attachment_id = uploaded.json()["data"][0]["id"]
    prompted = await async_client.post(
        f"/api/v1/agent/sessions/{session_id}/commands",
        json={
            "type": "message",
            "command_id": "keep-attachment",
            "parts": [
                {"type": "text", "text": "Use this image"},
                {"type": "attachment_ref", "attachment_id": attachment_id},
            ],
        },
    )
    assert prompted.status_code == 202

    deleted = await async_client.delete(f"/api/v1/agent/attachments/{attachment_id}")

    assert deleted.status_code == 409
    assert deleted.json()["error"]["code"] == "CONFLICT"
    preview = await async_client.get(
        f"/api/v1/agent/attachments/{attachment_id}/preview"
    )
    assert preview.status_code == 200


@pytest.mark.asyncio
async def test_image_upload_preserves_the_explicit_picker_source(async_client) -> None:
    created = await async_client.post("/api/v1/agent/sessions", json={})
    session_id = created.json()["data"]["session"]["id"]

    uploaded = await async_client.post(
        f"/api/v1/agent/sessions/{session_id}/attachments",
        data={"kind": "image", "source": "upload"},
        files={"files": ("figure.png", PNG_1X1, "image/png")},
    )

    assert uploaded.status_code == 201
    assert uploaded.json()["data"][0]["source"] == "upload"


@pytest.mark.asyncio
async def test_image_upload_rejects_an_unknown_source(async_client) -> None:
    created = await async_client.post("/api/v1/agent/sessions", json={})
    session_id = created.json()["data"]["session"]["id"]

    uploaded = await async_client.post(
        f"/api/v1/agent/sessions/{session_id}/attachments",
        data={"kind": "image", "source": "remote-copy"},
        files={"files": ("figure.png", PNG_1X1, "image/png")},
    )

    assert uploaded.status_code == 400


@pytest.mark.asyncio
async def test_folder_upload_requires_matching_relative_paths(async_client) -> None:
    created = await async_client.post("/api/v1/agent/sessions", json={})
    session_id = created.json()["data"]["session"]["id"]

    response = await async_client.post(
        f"/api/v1/agent/sessions/{session_id}/attachments",
        data={"kind": "folder", "relative_paths": ["folder/a.txt"]},
        files=[
            ("files", ("a.txt", b"a", "text/plain")),
            ("files", ("b.txt", b"b", "text/plain")),
        ],
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_attachment_api_does_not_leak_other_user_records(
    async_client,
    db_session,
) -> None:
    created = await async_client.post("/api/v1/agent/sessions", json={})
    session = created.json()["data"]["session"]
    foreign = AgentHarnessAttachment(
        session_id=session["id"],
        workspace_id=session["workspace_id"],
        user_id="another-user",
        kind="file",
        source="upload",
        filename="secret.txt",
        storage_path=f"{session['id']}/foreign",
        mime_type="text/plain",
        size_bytes=6,
        status="ready",
    )
    db_session.add(foreign)
    await db_session.commit()
    await db_session.refresh(foreign)

    preview = await async_client.get(f"/api/v1/agent/attachments/{foreign.id}/preview")
    deleted = await async_client.delete(f"/api/v1/agent/attachments/{foreign.id}")

    assert preview.status_code == 404
    assert deleted.status_code == 404
