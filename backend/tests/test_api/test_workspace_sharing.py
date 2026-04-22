from __future__ import annotations

import pytest

from app.api.v1.events import stream_events
from app.auth.session import AuthUser
from app.models.conversation import Conversation
from app.models.project import Project
from app.models.run import Run, RunStatus
from app.utils.exceptions import PermissionDeniedError


DEV_USER_ID = "dev"
OTHER_USER_ID = "other-user"
DEFAULT_WORKSPACE_ID = "00000000-0000-0000-0000-000000000001"


async def _create_project_for_user(db_session, *, name: str, user_id: str) -> Project:
    project = Project(
        name=name,
        storage_mode="managed",
        external_root_path=None,
        user_id=user_id,
        created_by_user_id=user_id,
        workspace_id=DEFAULT_WORKSPACE_ID,
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)
    return project


async def _create_conversation_for_user(
    db_session, *, project_id: str, user_id: str, title: str = "Test conversation"
) -> Conversation:
    conversation = Conversation(
        project_id=project_id,
        title=title,
        user_id=user_id,
        created_by_user_id=user_id,
    )
    db_session.add(conversation)
    await db_session.commit()
    await db_session.refresh(conversation)
    return conversation


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
async def test_create_conversation_preserves_creator_but_is_workspace_shared(
    async_client, db_session
):
    project = await _create_project_for_user(
        db_session,
        name="Conversation Project",
        user_id=DEV_USER_ID,
    )
    resp = await async_client.post(
        "/api/v1/agent/conversations",
        json={"project_id": str(project.id), "title": "Shared chat"},
    )
    assert resp.status_code == 201
    conv_id = resp.json()["data"]["id"]

    from app.repositories.conversation_repo import ConversationRepository

    conversation = await ConversationRepository(db_session).get(conv_id)
    assert conversation is not None
    assert conversation.user_id == DEV_USER_ID
    assert conversation.created_by_user_id == DEV_USER_ID

    other_conv = await _create_conversation_for_user(
        db_session,
        project_id=str(project.id),
        user_id=OTHER_USER_ID,
        title="Teammate Conversation",
    )
    list_resp = await async_client.get(
        "/api/v1/agent/conversations",
        params={"project_id": str(project.id)},
    )
    assert list_resp.status_code == 200
    titles = [c["title"] for c in list_resp.json()["data"]]
    assert "Shared chat" in titles
    assert "Teammate Conversation" in titles

    get_resp = await async_client.get(f"/api/v1/agent/conversations/{other_conv.id}")
    assert get_resp.status_code == 200


@pytest.mark.asyncio
async def test_runs_are_scoped_to_project_owner(async_client, db_session):
    """Runs are user-scoped via their parent project.

    Per the 2026-04-17 security review, RunRepository.list and the
    single-run access check must filter by Project.user_id so that
    cross-user run visibility (previously implicit via workspace sharing)
    is closed off. Workspace-level sharing remains only for the Project
    surface itself.
    """
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
    assert "r-other-001" not in run_ids

    get_resp = await async_client.get(f"/api/v1/runs/{other_run.run_id}")
    assert get_resp.status_code in (403, 404)


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
async def test_run_dag_is_scoped_to_project_owner(async_client, db_session):
    """RunDagService enforces ownership just like RunLifecycleService.

    Regression guard for a gap where `_require_run_access` in
    RunDagService accepted `user_id` but never checked it, leaving
    /runs/{id}/dag readable across users even after the rest of the
    2026-04-17 security fixes landed.
    """
    other_project = await _create_project_for_user(
        db_session,
        name="Other DAG Project",
        user_id=OTHER_USER_ID,
    )
    other_run = await _create_run_for_project(
        db_session, project_id=str(other_project.id), run_id="r-dag-other-001"
    )

    dag_resp = await async_client.get(f"/api/v1/runs/{other_run.run_id}/dag")
    assert dag_resp.status_code in (403, 404)
