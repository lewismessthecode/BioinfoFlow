from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.models.project import Project
from app.path_layout import project_data_root, project_home, project_runs_root
from app.services.project_service import ProjectService


@pytest.mark.asyncio
async def test_create_managed_project_uses_readable_directory(db_session):
    project = await ProjectService(db_session).create_project(
        {
            "name": "COVID Analysis",
            "workspace_id": "00000000-0000-0000-0000-000000000001",
        },
        user_id="u-1",
    )

    assert project.directory_name == "covid-analysis"
    assert project_home(project) == (
        Path(settings.bioinfoflow_home) / "projects" / "covid-analysis"
    )
    assert project_data_root(project).is_dir()
    assert project_runs_root(project).is_dir()


@pytest.mark.asyncio
async def test_create_managed_projects_suffix_duplicate_names(db_session):
    service = ProjectService(db_session)

    first = await service.create_project(
        {"name": "COVID Analysis"},
        user_id="u-1",
    )
    second = await service.create_project(
        {"name": "COVID Analysis"},
        user_id="u-1",
    )

    assert first.directory_name == "covid-analysis"
    assert second.directory_name == "covid-analysis-2"


@pytest.mark.asyncio
async def test_rename_managed_project_keeps_directory(db_session):
    service = ProjectService(db_session)
    project = await service.create_project(
        {"name": "COVID Analysis"},
        user_id="u-1",
    )
    original_home = project_home(project)

    updated = await service.update_project(project, {"name": "Renamed Analysis"})

    assert updated.name == "Renamed Analysis"
    assert updated.directory_name == "covid-analysis"
    assert project_home(updated) == original_home


@pytest.mark.asyncio
async def test_create_external_project_keeps_legacy_path_behavior(db_session, tmp_path):
    external_root = tmp_path / "external-project"

    project = await ProjectService(db_session).create_project(
        {
            "name": "External Project",
            "external_root_path": str(external_root),
        },
        user_id="u-1",
    )

    assert project.storage_mode == "external"
    assert project.directory_name is None
    assert project_home(project) == external_root.resolve()
    assert project_data_root(project).is_dir()
    assert project_runs_root(project).is_dir()


@pytest.mark.asyncio
async def test_update_legacy_project_to_managed_keeps_uuid_directory(db_session):
    project = Project(
        id=str(uuid4()),
        name="Legacy External",
        storage_mode="external",
        external_root_path="/tmp/legacy-external",
        user_id="u-1",
    )
    db_session.add(project)
    await db_session.commit()

    updated = await ProjectService(db_session).update_project(
        project,
        {"storage_mode": "managed"},
    )

    assert updated.directory_name is None
    assert project_home(updated).name == str(project.id)
    assert project_data_root(updated).is_dir()
    assert project_runs_root(updated).is_dir()


@pytest.mark.asyncio
async def test_update_readable_project_to_managed_reuses_directory(db_session):
    project = Project(
        name="Readable",
        directory_name="readable-project",
        storage_mode="external",
        external_root_path="/tmp/readable-external",
        user_id="u-1",
    )
    db_session.add(project)
    await db_session.commit()

    updated = await ProjectService(db_session).update_project(
        project,
        {"storage_mode": "managed"},
    )

    assert updated.directory_name == "readable-project"
    assert project_home(updated).name == "readable-project"
    assert project_data_root(updated).is_dir()
    assert project_runs_root(updated).is_dir()


@pytest.mark.asyncio
async def test_default_project_uses_readable_directory_and_is_stable(db_session):
    service = ProjectService(db_session)

    first = await service.get_or_create_default(
        workspace_id="00000000-0000-0000-0000-000000000001",
        workspace_slug="bioinfoflow-team",
        user_id="user-123",
    )
    second = await service.get_or_create_default(
        workspace_id="00000000-0000-0000-0000-000000000001",
        workspace_slug="bioinfoflow-team",
        user_id="user-123",
    )

    assert first.id == second.id
    assert first.directory_name == "recent"
    assert project_home(first).name == "recent"


@pytest.mark.asyncio
async def test_existing_legacy_default_keeps_uuid_directory(db_session):
    legacy = Project(
        name="Recent",
        storage_mode="managed",
        user_id="user-123",
        workspace_id="00000000-0000-0000-0000-000000000001",
        is_default=True,
    )
    db_session.add(legacy)
    await db_session.commit()

    project = await ProjectService(db_session).get_or_create_default(
        workspace_id="00000000-0000-0000-0000-000000000001",
        workspace_slug="bioinfoflow-team",
        user_id="user-123",
    )

    assert project.id == legacy.id
    assert project.directory_name is None
    assert project_home(project).name == str(legacy.id)


@pytest.mark.asyncio
async def test_default_project_unique_race_cleans_loser_and_returns_existing(
    db_session, monkeypatch
):
    service = ProjectService(db_session)
    existing = Project(
        name="Recent",
        directory_name="recent",
        storage_mode="managed",
        user_id="other-user",
        workspace_id="00000000-0000-0000-0000-000000000001",
        is_default=True,
    )
    service.repo.get_default_for_workspace = AsyncMock(side_effect=[None, existing])
    reservations = []
    real_add_pending = service.directory_service.add_pending

    async def capture_reservation(data):
        reservation = await real_add_pending(data)
        reservations.append(reservation)
        return reservation

    monkeypatch.setattr(
        service.directory_service,
        "add_pending",
        capture_reservation,
    )
    real_commit = db_session.commit

    async def fail_unique_default_commit():
        raise IntegrityError(
            "insert project",
            {},
            Exception("UNIQUE constraint failed: projects.workspace_id"),
        )

    monkeypatch.setattr(db_session, "commit", fail_unique_default_commit)

    result = await service.get_or_create_default(
        workspace_id="00000000-0000-0000-0000-000000000001",
        workspace_slug="bioinfoflow-team",
        user_id="user-123",
    )

    monkeypatch.setattr(db_session, "commit", real_commit)
    assert result is existing
    assert len(reservations) == 1
    assert reservations[0].root_fd is None
    assert reservations[0].parent_fd is None
    assert not (Path(settings.bioinfoflow_home) / "projects" / "recent").exists()
