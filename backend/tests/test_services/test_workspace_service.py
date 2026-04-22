"""Tests for WorkspaceService — workspace and membership management.

Validates ensure_default_workspace idempotency and ensure_membership
creation/update logic.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.auth.session import AuthUser
from app.services.workspace_service import WorkspaceService
from app.workspace import (
    DEFAULT_WORKSPACE_ID,
    DEFAULT_WORKSPACE_NAME,
    DEFAULT_WORKSPACE_SLUG,
)


def _make_auth_user(**overrides) -> AuthUser:
    defaults = {
        "id": "user-1",
        "name": "Test User",
        "email": "test@example.com",
        "role": "member",
        "workspace_id": DEFAULT_WORKSPACE_ID,
    }
    defaults.update(overrides)
    return AuthUser(**defaults)


@pytest.mark.asyncio
async def test_ensure_default_workspace_creates_when_missing():
    """When no default workspace exists, it should be created."""
    mock_session = MagicMock()

    with (
        patch("app.services.workspace_service.WorkspaceRepository") as MockWsRepo,
        patch("app.services.workspace_service.WorkspaceMembershipRepository"),
    ):
        ws_repo = MockWsRepo.return_value
        ws_repo.get_default = AsyncMock(return_value=None)
        ws_repo.create = AsyncMock()

        service = WorkspaceService(mock_session)
        await service.ensure_default_workspace()

    ws_repo.create.assert_called_once_with(
        id=DEFAULT_WORKSPACE_ID,
        name=DEFAULT_WORKSPACE_NAME,
        slug=DEFAULT_WORKSPACE_SLUG,
        is_default=True,
    )


@pytest.mark.asyncio
async def test_ensure_default_workspace_skips_when_exists():
    """When the default workspace already exists, create should not be called."""
    mock_session = MagicMock()
    existing_ws = MagicMock()

    with (
        patch("app.services.workspace_service.WorkspaceRepository") as MockWsRepo,
        patch("app.services.workspace_service.WorkspaceMembershipRepository"),
    ):
        ws_repo = MockWsRepo.return_value
        ws_repo.get_default = AsyncMock(return_value=existing_ws)
        ws_repo.create = AsyncMock()

        service = WorkspaceService(mock_session)
        await service.ensure_default_workspace()

    ws_repo.create.assert_not_called()


@pytest.mark.asyncio
async def test_ensure_membership_creates_when_no_membership():
    """When the user has no membership, one should be created."""
    mock_session = MagicMock()
    user = _make_auth_user(id="user-new", role="admin")

    with (
        patch("app.services.workspace_service.WorkspaceRepository") as MockWsRepo,
        patch("app.services.workspace_service.WorkspaceMembershipRepository") as MockMemberRepo,
    ):
        ws_repo = MockWsRepo.return_value
        ws_repo.get_default = AsyncMock(return_value=MagicMock())
        ws_repo.create = AsyncMock()

        member_repo = MockMemberRepo.return_value
        member_repo.get_for_user = AsyncMock(return_value=None)
        member_repo.create = AsyncMock()
        member_repo.update = AsyncMock()

        service = WorkspaceService(mock_session)
        await service.ensure_membership(user)

    member_repo.create.assert_called_once_with(
        workspace_id=DEFAULT_WORKSPACE_ID,
        user_id="user-new",
        role="admin",
    )
    member_repo.update.assert_not_called()


@pytest.mark.asyncio
async def test_ensure_membership_updates_role_when_changed():
    """When the user's role has changed, the membership should be updated."""
    mock_session = MagicMock()
    user = _make_auth_user(id="user-promoted", role="admin")

    existing_membership = MagicMock()
    existing_membership.role = "member"

    with (
        patch("app.services.workspace_service.WorkspaceRepository") as MockWsRepo,
        patch("app.services.workspace_service.WorkspaceMembershipRepository") as MockMemberRepo,
    ):
        ws_repo = MockWsRepo.return_value
        ws_repo.get_default = AsyncMock(return_value=MagicMock())

        member_repo = MockMemberRepo.return_value
        member_repo.get_for_user = AsyncMock(return_value=existing_membership)
        member_repo.update = AsyncMock()
        member_repo.create = AsyncMock()

        service = WorkspaceService(mock_session)
        await service.ensure_membership(user)

    member_repo.update.assert_called_once_with(existing_membership, role="admin")
    member_repo.create.assert_not_called()


@pytest.mark.asyncio
async def test_ensure_membership_noop_when_role_unchanged():
    """When the user already has the correct role, no update should occur."""
    mock_session = MagicMock()
    user = _make_auth_user(id="user-same", role="member")

    existing_membership = MagicMock()
    existing_membership.role = "member"

    with (
        patch("app.services.workspace_service.WorkspaceRepository") as MockWsRepo,
        patch("app.services.workspace_service.WorkspaceMembershipRepository") as MockMemberRepo,
    ):
        ws_repo = MockWsRepo.return_value
        ws_repo.get_default = AsyncMock(return_value=MagicMock())

        member_repo = MockMemberRepo.return_value
        member_repo.get_for_user = AsyncMock(return_value=existing_membership)
        member_repo.update = AsyncMock()
        member_repo.create = AsyncMock()

        service = WorkspaceService(mock_session)
        await service.ensure_membership(user)

    member_repo.update.assert_not_called()
    member_repo.create.assert_not_called()
