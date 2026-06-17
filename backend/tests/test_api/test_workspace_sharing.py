from __future__ import annotations

import pytest

from app.api.deps import get_current_user
from app.api.v1.events import stream_events
from app.auth.session import AuthUser
from app.models.agent_core import AgentSession
from app.models.image import DockerImage, ImageStatus
from app.models.project import Project
from app.models.run import Run, RunStatus
from app.config import settings
from app.utils.exceptions import PermissionDeniedError


DEV_USER_ID = "dev"
OTHER_USER_ID = "other-user"
DEFAULT_WORKSPACE_ID = "00000000-0000-0000-0000-000000000001"


async def _create_project_for_user(
    db_session,
    *,
    name: str,
    user_id: str,
    workspace_id: str = DEFAULT_WORKSPACE_ID,
) -> Project:
    project = Project(
        name=name,
        storage_mode="managed",
        external_root_path=None,
        user_id=user_id,
        created_by_user_id=user_id,
        workspace_id=workspace_id,
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)
    return project


async def _create_agent_session_for_user(
    db_session,
    *,
    project_id: str,
    user_id: str,
    title: str = "Test session",
    workspace_id: str = DEFAULT_WORKSPACE_ID,
    role_profile: str = "bioinformatician",
    lineage: dict | None = None,
) -> AgentSession:
    session = AgentSession(
        project_id=project_id,
        workspace_id=workspace_id,
        title=title,
        user_id=user_id,
        role_profile=role_profile,
        permission_mode="guarded_auto",
        automation_mode="assisted",
        lineage=lineage,
    )
    db_session.add(session)
    await db_session.commit()
    await db_session.refresh(session)
    return session


async def _create_run_for_project(
    db_session, *, project_id: str, run_id: str = "r-test-001"
) -> Run:
    run = Run(
        run_id=run_id,
        project_id=project_id,
        status=RunStatus.QUEUED.value,
        config={},
        samples_count=0,
        tasks_total=0,
        tasks_completed=0,
    )
    db_session.add(run)
    await db_session.commit()
    await db_session.refresh(run)
    return run


async def _create_global_image(
    db_session,
    *,
    name: str = "ubuntu",
    tag: str = "22.04",
) -> DockerImage:
    image = DockerImage(
        name=name,
        tag=tag,
        full_name=f"{name}:{tag}",
        registry="docker.io",
        status=ImageStatus.LOCAL.value,
    )
    db_session.add(image)
    await db_session.commit()
    await db_session.refresh(image)
    return image


def _auth_user(*, user_id: str, role: str = "member") -> AuthUser:
    return AuthUser(
        id=user_id,
        name=f"User {user_id}",
        email=f"{user_id}@bioinfoflow.test",
        role=role,
        workspace_id=DEFAULT_WORKSPACE_ID,
    )


@pytest.mark.asyncio
async def test_create_project_records_creator_and_default_workspace(
    async_client, db_session, tmp_path
):
    payload = {
        "name": "Shared Project",
        "description": "test",
    }
    resp = await async_client.post("/api/v1/projects", json=payload)
    assert resp.status_code == 201
    project_id = resp.json()["data"]["id"]

    from app.repositories.project_repo import ProjectRepository

    project = await ProjectRepository(db_session).get(project_id)
    assert project is not None
    assert project.user_id == DEV_USER_ID
    assert project.created_by_user_id == DEV_USER_ID
    assert str(project.workspace_id) == DEFAULT_WORKSPACE_ID


@pytest.mark.asyncio
async def test_list_projects_shows_workspace_shared_projects(async_client, db_session):
    await _create_project_for_user(
        db_session,
        name="My Project",
        user_id=DEV_USER_ID,
    )
    await _create_project_for_user(
        db_session,
        name="Teammate Project",
        user_id=OTHER_USER_ID,
    )

    resp = await async_client.get("/api/v1/projects")
    assert resp.status_code == 200
    names = [p["name"] for p in resp.json()["data"]]
    assert "My Project" in names
    assert "Teammate Project" in names


@pytest.mark.asyncio
async def test_list_projects_hides_system_owned_projects(async_client, db_session):
    await _create_project_for_user(
        db_session,
        name="Internal Fixture Project",
        user_id="system",
    )

    resp = await async_client.get("/api/v1/projects")
    assert resp.status_code == 200
    names = [p["name"] for p in resp.json()["data"]]
    assert "Internal Fixture Project" not in names


@pytest.mark.asyncio
async def test_can_access_and_update_project_created_by_another_user(
    async_client, db_session
):
    other_project = await _create_project_for_user(
        db_session,
        name="Shared Ownership Project",
        user_id=OTHER_USER_ID,
    )

    get_resp = await async_client.get(f"/api/v1/projects/{other_project.id}")
    assert get_resp.status_code == 200

    patch_resp = await async_client.patch(
        f"/api/v1/projects/{other_project.id}",
        json={"name": "Renamed By Teammate"},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["data"]["name"] == "Renamed By Teammate"


@pytest.mark.asyncio
async def test_create_agent_session_records_owner_and_is_user_scoped(
    async_client, db_session
):
    project = await _create_project_for_user(
        db_session,
        name="AgentCore Session Project",
        user_id=DEV_USER_ID,
    )
    resp = await async_client.post(
        "/api/v1/agent/sessions",
        json={"project_id": str(project.id), "title": "Shared chat"},
    )
    assert resp.status_code == 201
    session_id = resp.json()["data"]["id"]

    from app.repositories.agent_core_repo import AgentSessionRepository

    session = await AgentSessionRepository(db_session).get(session_id)
    assert session is not None
    assert session.user_id == DEV_USER_ID
    assert str(session.workspace_id) == DEFAULT_WORKSPACE_ID

    other_session = await _create_agent_session_for_user(
        db_session,
        project_id=str(project.id),
        user_id=OTHER_USER_ID,
        title="Teammate Session",
    )
    list_resp = await async_client.get(
        "/api/v1/agent/sessions",
        params={"project_id": str(project.id)},
    )
    assert list_resp.status_code == 200
    titles = [c["title"] for c in list_resp.json()["data"]]
    assert "Shared chat" in titles
    assert "Teammate Session" not in titles

    get_resp = await async_client.get(f"/api/v1/agent/sessions/{other_session.id}")
    assert get_resp.status_code == 403


@pytest.mark.asyncio
async def test_global_agent_session_list_is_user_scoped(async_client, db_session):
    shared_project = await _create_project_for_user(
        db_session,
        name="Shared Session Project",
        user_id=OTHER_USER_ID,
    )
    other_workspace_project = await _create_project_for_user(
        db_session,
        name="Other Workspace Session Project",
        user_id=OTHER_USER_ID,
        workspace_id="00000000-0000-0000-0000-000000000002",
    )

    my_project = await _create_project_for_user(
        db_session,
        name="My Session Project",
        user_id=DEV_USER_ID,
    )
    parent_session = await _create_agent_session_for_user(
        db_session,
        project_id=str(my_project.id),
        user_id=DEV_USER_ID,
        title="My AgentCore Session",
    )
    await _create_agent_session_for_user(
        db_session,
        project_id=str(my_project.id),
        user_id=DEV_USER_ID,
        title="Subagent: inspect workflow files",
        role_profile="worker",
        lineage={
            "parent_session_id": str(parent_session.id),
            "parent_turn_id": "turn-1",
        },
    )
    await _create_agent_session_for_user(
        db_session,
        project_id=str(shared_project.id),
        user_id=OTHER_USER_ID,
        title="Shared Workspace Session",
    )
    await _create_agent_session_for_user(
        db_session,
        project_id=str(other_workspace_project.id),
        user_id=OTHER_USER_ID,
        title="Other Workspace Session",
        workspace_id="00000000-0000-0000-0000-000000000002",
    )

    resp = await async_client.get("/api/v1/agent/sessions")
    assert resp.status_code == 200
    titles = [item["title"] for item in resp.json()["data"]]
    assert "My AgentCore Session" in titles
    assert "Subagent: inspect workflow files" not in titles
    assert "Shared Workspace Session" not in titles
    assert "Other Workspace Session" not in titles

    child_resp = await async_client.get("/api/v1/agent/sessions?include_children=true")
    assert child_resp.status_code == 200
    child_titles = [item["title"] for item in child_resp.json()["data"]]
    assert "My AgentCore Session" in child_titles
    assert "Subagent: inspect workflow files" in child_titles


@pytest.mark.asyncio
async def test_runs_are_workspace_shared(async_client, db_session):
    my_project = await _create_project_for_user(
        db_session,
        name="My Run Project",
        user_id=DEV_USER_ID,
    )
    other_project = await _create_project_for_user(
        db_session,
        name="Other Run Project",
        user_id=OTHER_USER_ID,
    )
    await _create_run_for_project(
        db_session, project_id=str(my_project.id), run_id="r-mine-001"
    )
    other_run = await _create_run_for_project(
        db_session, project_id=str(other_project.id), run_id="r-other-001"
    )

    list_resp = await async_client.get("/api/v1/runs")
    assert list_resp.status_code == 200
    run_ids = [r["run_id"] for r in list_resp.json()["data"]]
    assert "r-mine-001" in run_ids
    assert "r-other-001" in run_ids

    get_resp = await async_client.get(f"/api/v1/runs/{other_run.run_id}")
    assert get_resp.status_code == 200


@pytest.mark.asyncio
async def test_runs_for_system_owned_project_are_not_visible_within_workspace(
    async_client, db_session
):
    demo_project = await _create_project_for_user(
        db_session,
        name="Internal Fixture Run Project",
        user_id="system",
    )
    demo_run = await _create_run_for_project(
        db_session, project_id=str(demo_project.id), run_id="r-demo-001"
    )

    list_resp = await async_client.get(
        "/api/v1/runs",
        params={"project_id": str(demo_project.id)},
    )
    assert list_resp.status_code == 200
    run_ids = [r["run_id"] for r in list_resp.json()["data"]]
    assert "r-demo-001" not in run_ids

    get_resp = await async_client.get(f"/api/v1/runs/{demo_run.run_id}")
    assert get_resp.status_code in (403, 404)


@pytest.mark.asyncio
async def test_event_stream_rejects_workspace_access_for_system_owned_project(
    db_session,
):
    demo_project = await _create_project_for_user(
        db_session,
        name="Internal Fixture Stream Project",
        user_id="system",
    )

    class _DisconnectedRequest:
        async def is_disconnected(self) -> bool:
            return True

    with pytest.raises(PermissionDeniedError, match="event stream"):
        await stream_events(
            request=_DisconnectedRequest(),
            project_id=str(demo_project.id),
            user=AuthUser(
                id=DEV_USER_ID,
                name="Local User",
                email="local@bioinfoflow",
                role="owner",
                workspace_id=DEFAULT_WORKSPACE_ID,
            ),
            db=db_session,
        )


@pytest.mark.asyncio
async def test_run_dag_is_workspace_shared(async_client, db_session):
    other_project = await _create_project_for_user(
        db_session,
        name="Other DAG Project",
        user_id=OTHER_USER_ID,
    )
    other_run = await _create_run_for_project(
        db_session, project_id=str(other_project.id), run_id="r-dag-other-001"
    )

    dag_resp = await async_client.get(f"/api/v1/runs/{other_run.run_id}/dag")
    assert dag_resp.status_code in (200, 404)


@pytest.mark.asyncio
async def test_team_member_cannot_delete_shared_resources(
    async_client, db_session, app, monkeypatch
):
    monkeypatch.setattr(settings, "auth_mode", "team")
    monkeypatch.setattr(settings, "auth_enabled", True)
    app.dependency_overrides[get_current_user] = lambda: _auth_user(
        user_id=DEV_USER_ID,
        role="member",
    )

    project = await _create_project_for_user(
        db_session,
        name="Team Shared Project",
        user_id=OTHER_USER_ID,
    )
    run = await _create_run_for_project(
        db_session,
        project_id=str(project.id),
        run_id="r-team-shared-001",
    )

    project_resp = await async_client.delete(f"/api/v1/projects/{project.id}")
    run_resp = await async_client.delete(f"/api/v1/runs/{run.run_id}")

    assert project_resp.status_code == 403
    assert run_resp.status_code == 403

    app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_team_admin_can_delete_shared_resources(
    async_client, db_session, app, monkeypatch
):
    monkeypatch.setattr(settings, "auth_mode", "team")
    monkeypatch.setattr(settings, "auth_enabled", True)
    app.dependency_overrides[get_current_user] = lambda: _auth_user(
        user_id=DEV_USER_ID,
        role="admin",
    )

    project = await _create_project_for_user(
        db_session,
        name="Team Admin Project",
        user_id=OTHER_USER_ID,
    )
    run = await _create_run_for_project(
        db_session,
        project_id=str(project.id),
        run_id="r-team-admin-001",
    )

    run_resp = await async_client.delete(f"/api/v1/runs/{run.run_id}")

    assert run_resp.status_code == 204

    project_resp = await async_client.delete(f"/api/v1/projects/{project.id}")
    assert project_resp.status_code == 204

    app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_workspace_stats_include_shared_runs_and_images(async_client, db_session):
    project = await _create_project_for_user(
        db_session,
        name="Stats Shared Project",
        user_id=OTHER_USER_ID,
    )
    await _create_run_for_project(
        db_session,
        project_id=str(project.id),
        run_id="r-stats-shared-001",
    )
    await _create_global_image(db_session, name="stats-image", tag="1")

    resp = await async_client.get("/api/v1/stats")
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["projects"]["total"] >= 1
    assert data["runs"]["total"] >= 1
    assert data["images"]["total"] >= 1
