"""Tests for NotificationService config CRUD operations.

Covers create_config validation, list_configs delegation, and delete_config.
The webhook delivery tests live in test_notifications.py; SSRF tests in
test_notification_ssrf.py.
"""
from __future__ import annotations

from uuid import uuid4

import pytest

from app.models.project import Project
from app.services.notification_service import NotificationService


@pytest.mark.asyncio
async def test_create_config_succeeds_with_valid_input(db_session):
    """Happy path: creating a webhook config for an existing project."""
    project = Project(name=f"Cfg {uuid4()}", storage_mode="managed", external_root_path=None, user_id="dev")
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)

    service = NotificationService(db_session)
    config = await service.create_config(
        project_id=str(project.id),
        channel="webhook",
        trigger="on_complete",
        config={"url": "https://hooks.example.com/test"},
        enabled=True,
    )

    assert str(config.project_id) == str(project.id)
    assert config.channel == "webhook"
    assert config.trigger == "on_complete"
    assert config.config["url"] == "https://hooks.example.com/test"
    assert config.enabled is True


@pytest.mark.asyncio
async def test_create_config_raises_on_missing_project(db_session):
    """Creating a config for a nonexistent project should raise FileNotFoundError."""
    service = NotificationService(db_session)

    with pytest.raises(FileNotFoundError, match="project not found"):
        await service.create_config(
            project_id=str(uuid4()),
            channel="webhook",
            trigger="on_complete",
            config={"url": "https://example.com/hook"},
        )


@pytest.mark.asyncio
async def test_create_config_raises_on_unsupported_channel(db_session):
    """Using a channel other than 'webhook' should raise ValueError."""
    project = Project(name=f"Cfg {uuid4()}", storage_mode="managed", external_root_path=None, user_id="dev")
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)

    service = NotificationService(db_session)

    with pytest.raises(ValueError, match="unsupported notification channel"):
        await service.create_config(
            project_id=str(project.id),
            channel="email",
            trigger="on_complete",
            config={"url": "https://example.com/hook"},
        )


@pytest.mark.asyncio
async def test_create_config_raises_on_missing_url(db_session):
    """A webhook config with no url should raise ValueError."""
    project = Project(name=f"Cfg {uuid4()}", storage_mode="managed", external_root_path=None, user_id="dev")
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)

    service = NotificationService(db_session)

    with pytest.raises(ValueError, match="webhook url is required"):
        await service.create_config(
            project_id=str(project.id),
            channel="webhook",
            trigger="on_complete",
            config={"url": ""},
        )


@pytest.mark.asyncio
async def test_delete_config_removes_existing(db_session):
    """Deleting an existing config should return True."""
    project = Project(name=f"Cfg {uuid4()}", storage_mode="managed", external_root_path=None, user_id="dev")
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)

    service = NotificationService(db_session)
    config = await service.create_config(
        project_id=str(project.id),
        channel="webhook",
        trigger="on_complete",
        config={"url": "https://example.com/hook"},
    )

    result = await service.delete_config(str(config.id))
    assert result is True

    # Verify it's gone
    configs = await service.list_configs(project_id=str(project.id))
    assert len(configs) == 0


@pytest.mark.asyncio
async def test_delete_config_returns_false_for_nonexistent(db_session):
    """Deleting a nonexistent config should return False."""
    service = NotificationService(db_session)
    result = await service.delete_config(str(uuid4()))
    assert result is False
