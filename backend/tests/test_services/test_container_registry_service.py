from __future__ import annotations

import pytest

from app.models.project import Project
from app.workspace import DEFAULT_WORKSPACE_ID


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
            "is_default": True,
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
async def test_registry_service_resolves_project_override_before_global_default(
    db_session,
):
    from app.services.container_registry_service import ContainerRegistryService

    service = ContainerRegistryService(db_session)
    default_registry = await service.create_registry(
        {
            "name": "Default registry",
            "endpoint": "https://default-registry.example.test",
            "is_default": True,
            "credential_source": "none",
            "updated_by": "user-1",
        }
    )
    override_registry = await service.create_registry(
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
        container_registry_id=str(override_registry.id),
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)

    effective = await service.get_effective_registry(project_id=str(project.id))
    assert effective is not None
    assert str(effective.id) == str(override_registry.id)

    fallback = await service.get_effective_registry(project_id=None)
    assert fallback is not None
    assert str(fallback.id) == str(default_registry.id)
