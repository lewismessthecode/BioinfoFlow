from __future__ import annotations

import asyncio

import pytest

from app.auth.session import AuthUser
from app.models.project import Project
from app.workspace import DEFAULT_WORKSPACE_ID
import app.api.v1.events as events_api
from app.runtime.events import build_event


class _OpenRequest:
    async def is_disconnected(self) -> bool:
        return False


@pytest.mark.asyncio
async def test_stream_events_filters_to_requested_run_and_unsubscribes(
    db_session, tmp_path, monkeypatch
):
    workspace = tmp_path / "events_ws"
    workspace.mkdir()
    project = Project(
        name="Events Project",
        storage_mode="external",
        external_root_path=str(workspace),
        user_id="dev",
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)

    queue: asyncio.Queue = asyncio.Queue()
    await queue.put(
        build_event(
            event="run.status",
            project_id=str(project.id),
            run_id="run-other",
            data={"run_id": "run-other", "status": "running"},
        )
    )
    await queue.put(
        build_event(
            event="run.status",
            project_id=str(project.id),
            run_id="run-123",
            data={"run_id": "run-123", "status": "running"},
        )
    )

    unsubscribed: list[tuple[str, asyncio.Queue]] = []

    async def fake_subscribe(project_id: str) -> asyncio.Queue:
        assert project_id == str(project.id)
        return queue

    def fake_unsubscribe(project_id: str, item: asyncio.Queue) -> None:
        unsubscribed.append((project_id, item))

    monkeypatch.setattr(events_api.events, "subscribe", fake_subscribe)
    monkeypatch.setattr(events_api.events, "unsubscribe", fake_unsubscribe)

    response = await events_api.stream_events(
        request=_OpenRequest(),
        project_id=str(project.id),
        run_id="run-123",
        user=AuthUser(
            id="dev",
            name="Local User",
            email="local@bioinfoflow",
            role="owner",
            workspace_id=DEFAULT_WORKSPACE_ID,
        ),
        db=db_session,
    )

    chunks: list[str] = []
    iterator = response.body_iterator
    for _ in range(3):
        chunks.append(await iterator.__anext__())
    await iterator.aclose()

    payload = "".join(chunks)
    assert "run-123" in payload
    assert "run-other" not in payload
    assert "event: run.status" in payload
    assert unsubscribed == [(str(project.id), queue)]
