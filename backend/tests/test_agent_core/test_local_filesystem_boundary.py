from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.config import settings
from app.models.project import Project
from app.models.workspace import Workspace
from app.path_layout import deliveries_root, project_home
from app.services.agent_core.sandbox.local_boundary import (
    LocalFilesystemBoundaryResolver,
)
from app.utils.exceptions import PermissionDeniedError
from app.workspace import DEFAULT_WORKSPACE_ID


@pytest.mark.asyncio
async def test_local_boundary_defaults_to_active_project_and_allows_configured_root(
    db_session,
    tmp_path,
    monkeypatch,
):
    repo_root = tmp_path / "bioinfoflow-product"
    data_root = repo_root / "data"
    external_root = tmp_path / "shared-analysis"
    repo_root.mkdir()
    data_root.mkdir()
    external_root.mkdir()
    monkeypatch.setattr(settings, "repo_root", str(repo_root))
    monkeypatch.setattr(settings, "bioinfoflow_home", str(data_root))
    monkeypatch.setattr(settings, "agent_filesystem_roots", str(external_root), raising=False)

    workspace = Workspace(id=DEFAULT_WORKSPACE_ID, name="Team", slug="team")
    project = Project(
        name="Project",
        user_id="dev",
        created_by_user_id="dev",
        workspace_id=DEFAULT_WORKSPACE_ID,
    )
    db_session.add_all([workspace, project])
    await db_session.commit()
    await db_session.refresh(project)
    project_home(project).mkdir(parents=True)

    boundary = await LocalFilesystemBoundaryResolver(db_session).resolve(
        SimpleNamespace(
            project_id=str(project.id),
            workspace_id=DEFAULT_WORKSPACE_ID,
        )
    )

    assert boundary.working_directory == project_home(project)
    assert project_home(project) in boundary.write_roots
    assert external_root.resolve() in boundary.write_roots
    assert boundary.policy.require_allowed_path(project_home(project)) == project_home(project)


@pytest.mark.asyncio
async def test_local_boundary_never_exposes_product_source_or_internal_state(
    db_session,
    tmp_path,
    monkeypatch,
):
    repo_root = tmp_path / "bioinfoflow-product"
    data_root = repo_root / "data"
    source_file = repo_root / "backend" / "app.py"
    state_file = data_root / "state" / "bioinfoflow.db"
    source_file.parent.mkdir(parents=True)
    state_file.parent.mkdir(parents=True)
    source_file.write_text("source", encoding="utf-8")
    state_file.write_text("state", encoding="utf-8")
    monkeypatch.setattr(settings, "repo_root", str(repo_root))
    monkeypatch.setattr(settings, "bioinfoflow_home", str(data_root))
    # Even an operator mistake that declares an ancestor cannot authorize the
    # product checkout.
    monkeypatch.setattr(settings, "agent_filesystem_roots", str(tmp_path), raising=False)

    boundary = await LocalFilesystemBoundaryResolver(db_session).resolve(
        SimpleNamespace(project_id=None, workspace_id=DEFAULT_WORKSPACE_ID)
    )

    with pytest.raises(PermissionDeniedError, match="protected"):
        boundary.policy.require_allowed_path(source_file)
    with pytest.raises(PermissionDeniedError, match="protected"):
        boundary.policy.require_allowed_path(state_file)
    assert tmp_path.resolve() not in boundary.read_roots


@pytest.mark.asyncio
async def test_workspace_scoped_boundary_defaults_to_deliveries(
    db_session,
    tmp_path,
    monkeypatch,
):
    repo_root = tmp_path / "bioinfoflow-product"
    data_root = repo_root / "data"
    data_root.mkdir(parents=True)
    monkeypatch.setattr(settings, "repo_root", str(repo_root))
    monkeypatch.setattr(settings, "bioinfoflow_home", str(data_root))
    monkeypatch.setattr(settings, "agent_filesystem_roots", "", raising=False)
    deliveries_root().mkdir(parents=True)

    boundary = await LocalFilesystemBoundaryResolver(db_session).resolve(
        SimpleNamespace(project_id=None, workspace_id=DEFAULT_WORKSPACE_ID)
    )

    assert boundary.working_directory == deliveries_root()
    assert deliveries_root() in boundary.write_roots
