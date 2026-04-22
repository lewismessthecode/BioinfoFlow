from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import settings
from app.path_layout import project_data_root, project_home, project_runs_root


@pytest.fixture
def mock_session():
    return AsyncMock()


@pytest.fixture
def project_service(mock_session):
    from app.services.project_service import ProjectService

    svc = ProjectService(mock_session)
    svc.repo = MagicMock()
    svc.repo.create = AsyncMock(return_value=MagicMock(id="p-1", name="Test"))
    return svc


@pytest.mark.asyncio
async def test_create_project_provisions_managed_layout(project_service):
    data = {"name": "COVID Analysis"}
    with patch("app.services.project_service.uuid4", return_value="proj-uuid"):
        await project_service.create_project(data, user_id="u-1")

    call_kwargs = project_service.repo.create.call_args.kwargs
    assert call_kwargs["storage_mode"] == "managed"
    assert call_kwargs["external_root_path"] is None
    assert project_home("proj-uuid") == Path(settings.bioinfoflow_home) / "projects" / "proj-uuid"
    assert project_data_root("proj-uuid").exists()
    assert project_runs_root("proj-uuid").exists()


@pytest.mark.asyncio
async def test_create_project_uses_external_root_when_provided(project_service, tmp_path):
    external_root = tmp_path / "external-project"
    data = {"name": "My Project", "external_root_path": str(external_root)}

    await project_service.create_project(data, user_id="u-1")

    call_kwargs = project_service.repo.create.call_args.kwargs
    assert call_kwargs["storage_mode"] == "external"
    assert call_kwargs["external_root_path"] == str(external_root.resolve())
    assert (external_root / "data").exists()
    assert (external_root / "runs").exists()


@pytest.mark.asyncio
async def test_get_or_create_default_creates_managed_default_project(project_service):
    project_service.repo.get_default_for_workspace = AsyncMock(return_value=None)

    with patch("app.services.project_service.uuid4", return_value="proj-uuid"):
        await project_service.get_or_create_default(
            workspace_id="00000000-0000-0000-0000-000000000001",
            workspace_slug="bioinfoflow-team",
            user_id="user-123",
        )

    call_kwargs = project_service.repo.create.await_args.kwargs
    assert call_kwargs["is_default"] is True
    assert call_kwargs["storage_mode"] == "managed"
    assert call_kwargs["external_root_path"] is None
    assert project_data_root("proj-uuid").exists()
    assert project_runs_root("proj-uuid").exists()
