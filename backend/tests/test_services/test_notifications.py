from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.models.project import Project
from app.services.notification_service import NotificationService
from app.workspace import DEFAULT_WORKSPACE_ID


def _identity() -> dict[str, str]:
    return {"user_id": "dev", "workspace_id": DEFAULT_WORKSPACE_ID}


@pytest.fixture(autouse=True)
def _bypass_ssrf_check(monkeypatch):
    """Bypass SSRF check for all notification tests.

    example.test is unresolvable, which causes _is_private_url to block it.
    These tests monkeypatch aiohttp.ClientSession so no real HTTP call is made.
    """
    monkeypatch.setattr(
        "app.services.notification_service._resolve_webhook_destination",
        lambda url: SimpleNamespace(
            hostname="example.test",
            port=443,
            addresses=(("93.184.216.34", 2),),
        ),
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

    async def post(
        self, url: str, *, json: dict, headers: dict, allow_redirects: bool
    ):
        assert allow_redirects is False
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

    async def post(
        self, url: str, *, json: dict, headers: dict, allow_redirects: bool
    ):
        del allow_redirects
        del url, json, headers
        raise RuntimeError("boom")


class _OkResponse:
    def raise_for_status(self) -> None:
        return None


class _ServerErrorResponse:
    def raise_for_status(self) -> None:
        raise RuntimeError("server error")


class _StatusFailingClient:
    def __init__(self, *args, **kwargs):
        del args, kwargs

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        del exc_type, exc, tb
        return False

    async def post(
        self, url: str, *, json: dict, headers: dict, allow_redirects: bool
    ):
        del allow_redirects
        del url, json, headers
        return _ServerErrorResponse()


class _RecordingSession:
    def __init__(self, *args, **kwargs):
        del args, kwargs

    async def __aenter__(self):
        return _RecordingClient()

    async def __aexit__(self, exc_type, exc, tb):
        del exc_type, exc, tb
        return False


class _FailingSession:
    def __init__(self, *args, **kwargs):
        del args, kwargs

    async def __aenter__(self):
        return _FailingClient()

    async def __aexit__(self, exc_type, exc, tb):
        del exc_type, exc, tb
        return False


class _StatusFailingSession:
    def __init__(self, *args, **kwargs):
        del args, kwargs

    async def __aenter__(self):
        return _StatusFailingClient()

    async def __aexit__(self, exc_type, exc, tb):
        del exc_type, exc, tb
        return False


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
        **_identity(),
        channel="webhook",
        trigger="on_complete",
        config={"url": "https://example.test/hook", "headers": {"X-Test": "1"}},
        enabled=True,
    )
    await service.create_config(
        project_id=str(project.id),
        **_identity(),
        channel="webhook",
        trigger="on_failure",
        config={"url": "https://example.test/ignored"},
        enabled=True,
    )
    await service.create_config(
        project_id=str(project.id),
        **_identity(),
        channel="webhook",
        trigger="on_complete",
        config={"url": "https://example.test/disabled"},
        enabled=False,
    )

    monkeypatch.setattr(
        "app.services.notification_service.aiohttp.ClientSession",
        _RecordingSession,
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
        **_identity(),
        channel="webhook",
        trigger="on_complete",
        config={"url": "https://example.test/fail"},
        enabled=True,
    )

    logged: list[dict] = []

    monkeypatch.setattr(
        "app.services.notification_service.aiohttp.ClientSession",
        _FailingSession,
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
        **_identity(),
        channel="webhook",
        trigger="on_complete",
        config={"url": "https://example.test/status-fail"},
        enabled=True,
    )

    logged: list[dict] = []

    monkeypatch.setattr(
        "app.services.notification_service.aiohttp.ClientSession",
        _StatusFailingSession,
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
