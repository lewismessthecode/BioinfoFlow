from __future__ import annotations

import pytest

from app.api.deps import get_current_user
from app.auth.session import AuthUser
from app.models.conversation import Conversation
from app.models.project import Project
from app.repositories.conversation_repo import ConversationRepository
from app.services.agent.trace_service import AgentTraceService
from app.services.agent.agent_service import AgentService
from app.utils.exceptions import PermissionDeniedError


@pytest.mark.asyncio
async def test_conversation_repository_list_filters_by_user_id(db_session, tmp_path):
    project = Project(
        name="Auth Project",
        storage_mode="external",
        external_root_path=str(tmp_path / "workspace"),
        user_id="owner",
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)

    mine = Conversation(project_id=str(project.id), user_id="owner", title="Mine")
    theirs = Conversation(project_id=str(project.id), user_id="other", title="Theirs")
    db_session.add_all([mine, theirs])
    await db_session.commit()

    repo = ConversationRepository(db_session)
    conversations, pagination = await repo.list(
        project_id=str(project.id),
        user_id="owner",
        limit=20,
    )

    assert [item.title for item in conversations] == ["Mine"]
    assert pagination.total_count == 1


@pytest.mark.asyncio
async def test_require_conversation_rejects_other_users(db_session, tmp_path):
    project = Project(
        name="Agent Auth Project",
        storage_mode="external",
        external_root_path=str(tmp_path / "workspace"),
        user_id="owner",
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)

    conversation = Conversation(
        project_id=str(project.id),
        user_id="owner",
        title="Private Thread",
    )
    db_session.add(conversation)
    await db_session.commit()
    await db_session.refresh(conversation)

    service = AgentService(db_session)

    with pytest.raises(
        PermissionDeniedError, match="conversation does not belong to user"
    ):
        await service._require_conversation(str(conversation.id), user_id="intruder")


@pytest.mark.asyncio
async def test_update_conversation_rejects_other_users(db_session, tmp_path):
    project = Project(
        name="Conversation Update Project",
        storage_mode="external",
        external_root_path=str(tmp_path / "workspace"),
        user_id="owner",
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)

    conversation = Conversation(
        project_id=str(project.id),
        user_id="owner",
        title="Original",
    )
    db_session.add(conversation)
    await db_session.commit()
    await db_session.refresh(conversation)

    service = AgentService(db_session)

    with pytest.raises(
        PermissionDeniedError, match="conversation does not belong to user"
    ):
        await service.update_conversation(
            conversation_id=str(conversation.id),
            user_id="intruder",
            title="Compromised",
        )


@pytest.mark.asyncio
async def test_create_conversation_persists_execution_policy(db_session, tmp_path):
    project = Project(
        name="Execution Policy Project",
        storage_mode="external",
        external_root_path=str(tmp_path / "workspace"),
        user_id="owner",
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)

    service = AgentService(db_session)
    conversation = await service.create_conversation(
        project_id=str(project.id),
        user_id="owner",
        execution_policy="bypass",
    )

    assert conversation.execution_policy == "bypass"


@pytest.mark.asyncio
async def test_trace_endpoint_requires_conversation_access(
    async_client, app, db_session, tmp_path
):
    project = Project(
        name="Trace Project",
        storage_mode="external",
        external_root_path=str(tmp_path / "workspace"),
        user_id="owner",
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)

    conversation = Conversation(
        project_id=str(project.id),
        user_id="owner",
        title="Private Trace",
    )
    db_session.add(conversation)
    await db_session.commit()
    await db_session.refresh(conversation)

    async def override_user():
        return AuthUser(
            id="intruder",
            name="Intruder",
            email="intruder@example.com",
            workspace_id="",
        )

    app.dependency_overrides[get_current_user] = override_user
    try:
        response = await async_client.get(
            f"/api/v1/agent/conversations/{conversation.id}/trace"
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_get_trace_checks_conversation_before_listing(
    monkeypatch, async_client, app, db_session, tmp_path
):
    project = Project(
        name="Trace Guard Project",
        storage_mode="external",
        external_root_path=str(tmp_path / "workspace"),
        user_id="owner",
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)

    conversation = Conversation(
        project_id=str(project.id),
        user_id="owner",
        title="Guarded Trace",
    )
    db_session.add(conversation)
    await db_session.commit()
    await db_session.refresh(conversation)

    listed = {"called": False}

    async def fail_if_called(self, **kwargs):
        listed["called"] = True
        return []

    async def override_user():
        return AuthUser(
            id="intruder",
            name="Intruder",
            email="intruder@example.com",
            workspace_id="",
        )

    monkeypatch.setattr(AgentTraceService, "list_trace", fail_if_called)
    app.dependency_overrides[get_current_user] = override_user
    try:
        response = await async_client.get(
            f"/api/v1/agent/conversations/{conversation.id}/trace"
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 403
    assert listed["called"] is False
