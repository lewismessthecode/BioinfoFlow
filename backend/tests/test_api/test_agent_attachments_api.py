from __future__ import annotations

import base64

import pytest

from app.models.agent_core import AgentAttachment, AgentAttachmentStatus


PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUB"
    "AScY42YAAAAASUVORK5CYII="
)


@pytest.mark.asyncio
async def test_attachment_upload_preview_and_delete_api(async_client) -> None:
    created = await async_client.post("/api/v1/agent/sessions", json={})
    session_id = created.json()["data"]["id"]

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

    deleted = await async_client.delete(
        f"/api/v1/agent/attachments/{attachment['id']}"
    )
    assert deleted.status_code == 200
    missing = await async_client.get(
        f"/api/v1/agent/attachments/{attachment['id']}/preview"
    )
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_image_upload_preserves_the_explicit_picker_source(async_client) -> None:
    created = await async_client.post("/api/v1/agent/sessions", json={})
    session_id = created.json()["data"]["id"]

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
    session_id = created.json()["data"]["id"]

    uploaded = await async_client.post(
        f"/api/v1/agent/sessions/{session_id}/attachments",
        data={"kind": "image", "source": "remote-copy"},
        files={"files": ("figure.png", PNG_1X1, "image/png")},
    )

    assert uploaded.status_code == 400


@pytest.mark.asyncio
async def test_folder_upload_requires_matching_relative_paths(async_client) -> None:
    created = await async_client.post("/api/v1/agent/sessions", json={})
    session_id = created.json()["data"]["id"]

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
    session = created.json()["data"]
    foreign = AgentAttachment(
        session_id=session["id"],
        workspace_id=session["workspace_id"],
        user_id="another-user",
        kind="file",
        source="upload",
        filename="secret.txt",
        storage_path=f"{session['id']}/foreign",
        mime_type="text/plain",
        size_bytes=6,
        status=AgentAttachmentStatus.READY,
    )
    db_session.add(foreign)
    await db_session.commit()
    await db_session.refresh(foreign)

    preview = await async_client.get(
        f"/api/v1/agent/attachments/{foreign.id}/preview"
    )
    deleted = await async_client.delete(f"/api/v1/agent/attachments/{foreign.id}")

    assert preview.status_code == 404
    assert deleted.status_code == 404
