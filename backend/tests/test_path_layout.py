from __future__ import annotations

import pytest

from app.config import settings
from app.models.project import Project
from app.path_layout import (
    agent_attachment_root,
    agent_attachments_root,
    agent_session_attachments_root,
    project_home,
)
from app.utils.exceptions import BadRequestError


def test_agent_attachment_paths_are_session_scoped(tmp_path, monkeypatch) -> None:
    home = tmp_path / "bioinfoflow-home"
    monkeypatch.setattr(settings, "bioinfoflow_home", str(home))

    root = home / "state" / "agent_core" / "attachments"
    assert agent_attachments_root() == root
    assert agent_session_attachments_root("session-1") == root / "session-1"
    assert agent_attachment_root("session-1", "attachment-1") == (
        root / "session-1" / "attachment-1"
    )


@pytest.mark.parametrize(
    "unsafe_name",
    ["../escape", "/absolute", "nested/path", "", ".", ".."],
)
def test_agent_attachment_paths_reject_unsafe_ids(unsafe_name: str) -> None:
    with pytest.raises(ValueError):
        agent_session_attachments_root(unsafe_name)


def test_managed_project_home_uses_directory_name(tmp_path, monkeypatch) -> None:
    home = tmp_path / "bioinfoflow-home"
    monkeypatch.setattr(settings, "bioinfoflow_home", str(home))
    project = Project(
        id="00000000-0000-0000-0000-000000000001",
        name="Ce Shi",
        directory_name="ce-shi",
        storage_mode="managed",
        user_id="dev",
    )

    assert project_home(project) == home / "projects" / "ce-shi"


def test_legacy_managed_project_home_uses_project_id(tmp_path, monkeypatch) -> None:
    home = tmp_path / "bioinfoflow-home"
    monkeypatch.setattr(settings, "bioinfoflow_home", str(home))
    project_id = "00000000-0000-0000-0000-000000000002"
    project = Project(
        id=project_id,
        name="Legacy",
        directory_name=None,
        storage_mode="managed",
        user_id="dev",
    )

    assert project_home(project) == home / "projects" / project_id


def test_project_home_string_id_always_uses_project_id(tmp_path, monkeypatch) -> None:
    home = tmp_path / "bioinfoflow-home"
    monkeypatch.setattr(settings, "bioinfoflow_home", str(home))
    project_id = "00000000-0000-0000-0000-000000000003"

    assert project_home(project_id) == home / "projects" / project_id


def test_external_project_home_ignores_directory_name(tmp_path) -> None:
    external_root = tmp_path / "external-project"
    project = Project(
        id="00000000-0000-0000-0000-000000000004",
        name="External",
        directory_name="ignored-name",
        storage_mode="external",
        external_root_path=str(external_root),
        user_id="dev",
    )

    assert project_home(project) == external_root


def test_remote_project_home_still_raises_bad_request(tmp_path) -> None:
    project = Project(
        id="00000000-0000-0000-0000-000000000005",
        name="Remote",
        directory_name="ignored-name",
        storage_mode="remote",
        remote_root_path=str(tmp_path / "remote-project"),
        user_id="dev",
    )

    with pytest.raises(BadRequestError):
        project_home(project)
