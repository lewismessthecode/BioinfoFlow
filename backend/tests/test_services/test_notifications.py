from __future__ import annotations

from uuid import uuid4

import httpx
import pytest

from app.models.project import Project
from app.services.notification_service import NotificationService


@pytest.fixture(autouse=True)
def _bypass_ssrf_check(monkeypatch):
    """Bypass SSRF check for all notification tests.

    example.test is unresolvable, which causes _is_private_url to block it.
    These tests monkeypatch httpx.AsyncClient so no real HTTP call is made.
    """
    monkeypatch.setattr(
        "app.services.notification_service._is_private_url",
        lambda url: False,
    )


class _RecordingClient:
    calls: list[dict] = []

    def __init__(self, *args, **kwargs):
        del args, kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        del exc_type, exc, tb
        return False

    async def post(self, url: str, *, json: dict, headers: dict):
        self.calls.append({"url": url, "json": json, "headers": headers})
        return _OkResponse()


class _FailingClient:
    def __init__(self, *args, **kwargs):
        del args, kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        del exc_type, exc, tb
        return False

    async def post(self, url: str, *, json: dict, headers: dict):
        del url, json, headers
        raise RuntimeError("boom")


class _OkResponse:
    def raise_for_status(self) -> None:
        return None


class _ServerErrorResponse:
    def __init__(self) -> None:
        self.request = httpx.Request("POST", "https://example.test/status-fail")
        self.response = httpx.Response(500, request=self.request)

    def raise_for_status(self) -> None:
        raise httpx.HTTPStatusError(
            "server error",
            request=self.request,
            response=self.response,
        )


class _StatusFailingClient:
    def __init__(self, *args, **kwargs):
        del args, kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        del exc_type, exc, tb
        return False

    async def post(self, url: str, *, json: dict, headers: dict):
        del url, json, headers
        return _ServerErrorResponse()


@pytest.mark.asyncio
async def test_notify_posts_only_matching_enabled_webhook_configs(
    db_session, monkeypatch
):
    project = Project(name=f"Notify {uuid4()}", storage_mode="managed", external_root_path=None, user_id="dev")
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)

    service = NotificationService(db_session)
    await service.create_config(
        project_id=str(project.id),
        channel="webhook",
        trigger="on_complete",
        config={"url": "https://example.test/hook", "headers": {"X-Test": "1"}},
        enabled=True,
    )
    await service.create_config(
        project_id=str(project.id),
        channel="webhook",
        trigger="on_failure",
        config={"url": "https://example.test/ignored"},
        enabled=True,
    )
    await service.create_config(
        project_id=str(project.id),
        channel="webhook",
        trigger="on_complete",
        config={"url": "https://example.test/disabled"},
        enabled=False,
    )

    monkeypatch.setattr(
        "app.services.notification_service.httpx.AsyncClient",
        _RecordingClient,
    )
    _RecordingClient.calls.clear()

    await service.notify(
        str(project.id),
        "on_complete",
        {"run_id": "run_123", "status": "completed"},
    )

    assert _RecordingClient.calls == [
        {
            "url": "https://example.test/hook",
            "json": {"run_id": "run_123", "status": "completed"},
            "headers": {"X-Test": "1"},
        }
    ]


@pytest.mark.asyncio
async def test_notify_logs_and_swallows_webhook_failures(db_session, monkeypatch):
    project = Project(name=f"Notify {uuid4()}", storage_mode="managed", external_root_path=None, user_id="dev")
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)

    service = NotificationService(db_session)
    await service.create_config(
        project_id=str(project.id),
        channel="webhook",
        trigger="on_complete",
        config={"url": "https://example.test/fail"},
        enabled=True,
    )

    logged: list[dict] = []

    monkeypatch.setattr(
        "app.services.notification_service.httpx.AsyncClient",
        _FailingClient,
    )
    monkeypatch.setattr(
        "app.services.notification_service.logger.exception",
        lambda event, **kwargs: logged.append({"event": event, **kwargs}),
    )

    await service.notify(
        str(project.id),
        "on_complete",
        {"run_id": "run_456", "status": "completed"},
    )

    assert logged == [
        {
            "event": "notification.webhook.failed",
            "url": "https://example.test/fail",
            "trigger": "on_complete",
        }
    ]


@pytest.mark.asyncio
async def test_notify_logs_http_status_failures(db_session, monkeypatch):
    project = Project(name=f"Notify {uuid4()}", storage_mode="managed", external_root_path=None, user_id="dev")
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)

    service = NotificationService(db_session)
    await service.create_config(
        project_id=str(project.id),
        channel="webhook",
        trigger="on_complete",
        config={"url": "https://example.test/status-fail"},
        enabled=True,
    )

    logged: list[dict] = []

    monkeypatch.setattr(
        "app.services.notification_service.httpx.AsyncClient",
        _StatusFailingClient,
    )
    monkeypatch.setattr(
        "app.services.notification_service.logger.exception",
        lambda event, **kwargs: logged.append({"event": event, **kwargs}),
    )

    await service.notify(
        str(project.id),
        "on_complete",
        {"run_id": "run_789", "status": "completed"},
    )

    assert logged == [
        {
            "event": "notification.webhook.failed",
            "url": "https://example.test/status-fail",
            "trigger": "on_complete",
        }
    ]
