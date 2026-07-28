from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from app.models.project import Project
from app.repositories.project_repo import ProjectRepository
from app.utils.exceptions import NotFoundError
from app.workspace import DEFAULT_WORKSPACE_ID


@pytest.mark.asyncio
async def test_registry_repository_get_by_endpoint_prefers_latest_record(db_session):
    from app.services.container_registry_service import ContainerRegistryService

    service = ContainerRegistryService(db_session)
    endpoint = "https://duplicate.example.test"
    older_at = datetime(2026, 7, 27, tzinfo=timezone.utc)
    latest_at = datetime(2026, 7, 28, tzinfo=timezone.utc)
    common = {
        "name": "Duplicate registry",
        "endpoint": endpoint,
        "insecure": False,
        "credential_source": "none",
        "last_status": "untested",
    }
    await service.registry_repo.create(
        **common,
        id="00000000-0000-0000-0000-000000000099",
        updated_at=older_at,
    )
    await service.registry_repo.create(
        **common,
        id="00000000-0000-0000-0000-000000000001",
        updated_at=latest_at,
    )
    expected = await service.registry_repo.create(
        **common,
        id="00000000-0000-0000-0000-000000000002",
        updated_at=latest_at,
    )

    registry = await service.registry_repo.get_by_endpoint(endpoint)

    assert registry is not None
    assert str(registry.id) == str(expected.id)


@pytest.mark.asyncio
async def test_registry_repository_list_all_uses_id_as_final_tie_breaker(db_session):
    from app.services.container_registry_service import ContainerRegistryService

    service = ContainerRegistryService(db_session)
    common = {
        "name": "Same registry",
        "endpoint": "https://same.example.test",
        "insecure": False,
        "credential_source": "none",
        "last_status": "untested",
    }
    await service.registry_repo.create(
        **common,
        id="00000000-0000-0000-0000-000000000002",
    )
    await service.registry_repo.create(
        **common,
        id="00000000-0000-0000-0000-000000000001",
    )

    registries = await service.registry_repo.list_all()

    assert [str(registry.id) for registry in registries] == [
        "00000000-0000-0000-0000-000000000001",
        "00000000-0000-0000-0000-000000000002",
    ]


@pytest.mark.asyncio
async def test_registry_service_resolves_stored_auth_material_and_redacts_reads(
    db_session,
):
    from app.models.container_registry import ContainerRegistryCredentialSource
    from app.services.container_registry_service import ContainerRegistryService

    service = ContainerRegistryService(db_session)

    registry = await service.create_registry(
        {
            "name": "Harbor Bio",
            "endpoint": "https://harbor.example.test",
            "namespace": "bio",
            "insecure": False,
            "credential_source": ContainerRegistryCredentialSource.STORED,
            "username": "robot-user",
            "password": "top-secret-value",
            "updated_by": "user-1",
        }
    )

    assert registry.encrypted_username != "robot-user"
    assert registry.encrypted_password != "top-secret-value"

    material = await service.resolve_auth_material(str(registry.id))
    assert material.registry_id == str(registry.id)
    assert material.endpoint == "https://harbor.example.test"
    assert material.namespace == "bio"
    assert material.insecure is False
    assert material.source == "stored"
    assert material.username == "robot-user"
    assert material.password == "top-secret-value"

    read_payload = service.registry_read_dict(registry)
    assert read_payload["credential_source"] == "stored"
    assert "is_default" not in read_payload
    assert read_payload["username_hint"] == "robo...user"
    assert read_payload["password_hint"] == "top-...alue"
    assert "username" not in read_payload
    assert "password" not in read_payload
    assert "encrypted_username" not in read_payload
    assert "encrypted_password" not in read_payload


@pytest.mark.asyncio
async def test_registry_service_resolves_env_auth_material(db_session, monkeypatch):
    from app.services.container_registry_service import ContainerRegistryService

    monkeypatch.setenv("BIO_REGISTRY_USER", "robot")
    monkeypatch.setenv("BIO_REGISTRY_PASSWORD", "secret")
    service = ContainerRegistryService(db_session)

    registry = await service.create_registry(
        {
            "name": "Env registry",
            "endpoint": "https://registry.example.test",
            "credential_source": "env",
            "env_username_var": "BIO_REGISTRY_USER",
            "env_password_var": "BIO_REGISTRY_PASSWORD",
            "updated_by": "user-1",
        }
    )

    material = await service.resolve_auth_material(str(registry.id))
    assert material.source == "env"
    assert material.username == "robot"
    assert material.password == "secret"


@pytest.mark.asyncio
async def test_registry_service_reports_docker_runtime_configuration_error(
    db_session,
    monkeypatch,
):
    from app.services import container_registry_service
    from app.services.container_registry_service import ContainerRegistryService

    class FakeDockerService:
        async def test_registry(self, endpoint, *, auth_config=None):
            assert endpoint == "http://10.227.4.56:80"
            assert auth_config is None
            return (
                'Docker is not configured to allow the HTTP registry "10.227.4.56:80". '
                "Add it to Docker's insecure-registries and restart Docker."
            )

    monkeypatch.setattr(container_registry_service, "DockerService", FakeDockerService)
    service = ContainerRegistryService(db_session)
    registry = await service.create_registry(
        {
            "name": "Harbor HTTP",
            "endpoint": "http://10.227.4.56:80",
            "insecure": True,
            "credential_source": "none",
            "updated_by": "user-1",
        }
    )

    result = await service.test_registry(str(registry.id))

    assert result["success"] is False
    assert result["status"] == "error"
    assert "insecure-registries" in result["error"]
    refreshed = await service.get_registry(str(registry.id))
    assert refreshed.last_status == "error"
    assert refreshed.last_error == result["error"]


@pytest.mark.asyncio
async def test_registry_service_returns_explicit_project_registry(
    db_session,
):
    from app.services.container_registry_service import ContainerRegistryService

    service = ContainerRegistryService(db_session)
    project_registry = await service.create_registry(
        {
            "name": "Project registry",
            "endpoint": "https://project-registry.example.test",
            "credential_source": "none",
            "updated_by": "user-1",
        }
    )
    project = Project(
        name="Override project",
        description=None,
        user_id="user-1",
        workspace_id=DEFAULT_WORKSPACE_ID,
        container_registry_id=str(project_registry.id),
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)

    registry = await service.get_project_registry(project_id=str(project.id))

    assert registry is not None
    assert str(registry.id) == str(project_registry.id)


@pytest.mark.asyncio
async def test_registry_service_returns_none_without_project(db_session):
    from app.services.container_registry_service import ContainerRegistryService

    service = ContainerRegistryService(db_session)

    assert await service.get_project_registry(project_id=None) is None


@pytest.mark.asyncio
async def test_registry_service_looks_up_project_through_repository(
    db_session,
    monkeypatch,
):
    from app.services.container_registry_service import ContainerRegistryService

    project_id = "00000000-0000-0000-0000-000000000001"
    project_get = AsyncMock(return_value=None)
    monkeypatch.setattr(ProjectRepository, "get", project_get)
    service = ContainerRegistryService(db_session)

    with pytest.raises(NotFoundError, match=f"Project not found: {project_id}"):
        await service.get_project_registry(project_id=project_id)

    project_get.assert_awaited_once_with(project_id)
