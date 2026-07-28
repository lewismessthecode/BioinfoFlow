from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services import workflow_image_service as workflow_image_module
from app.services.workflow_image_service import (
    WorkflowImagePrefetchService,
    WorkflowImageRegistry,
    resolve_container_image_reference,
    resolve_workflow_image_requirements_with_credentials,
    resolve_workflow_image_requirements,
    workflow_container_images,
)


def _schema(*containers: object) -> dict:
    return {
        "tasks": [
            {"name": f"task_{index}", "container": container}
            for index, container in enumerate(containers)
        ]
    }


def test_workflow_container_images_skips_dynamic_and_deduplicates_static_images():
    assert workflow_container_images(
        _schema(
            "ubuntu:22.04",
            '"biocontainers/fastqc:0.12.1"',
            "ubuntu:22.04",
            "${params.image}",
            "~{task_image}",
            "python 3.12",
            "python\n3.12",
            "python\t3.12",
            None,
        )
    ) == ["ubuntu:22.04", "biocontainers/fastqc:0.12.1"]


def test_resolver_preserves_unqualified_image_without_selected_registry():
    requirement = resolve_container_image_reference(
        "ubuntu:22.04",
        selected_registry=None,
    )

    assert requirement.full_name == "ubuntu:22.04"
    assert requirement.registry == "docker.io"
    assert requirement.rewrite_applied is False


def test_resolver_rewrites_unqualified_images_with_selected_registry_namespace():
    registry = WorkflowImageRegistry(
        endpoint="http://10.227.4.56:80",
        namespace="pipeline-dev",
        registry_id="registry-1",
        auth_config={"username": "bioinfoflow", "password": "secret"},
    )

    requirements = resolve_workflow_image_requirements(
        _schema("ubuntu:22.04"),
        selected_registry=registry,
    )

    assert len(requirements) == 1
    requirement = requirements[0]
    assert requirement.source_reference == "ubuntu:22.04"
    assert requirement.name == "pipeline-dev/ubuntu"
    assert requirement.tag == "22.04"
    assert requirement.registry == "10.227.4.56:80"
    assert requirement.full_name == "10.227.4.56:80/pipeline-dev/ubuntu:22.04"
    assert requirement.explicit_registry is False
    assert requirement.rewrite_applied is True
    assert requirement.registry_id == "registry-1"
    assert requirement.auth_config == {"username": "bioinfoflow", "password": "secret"}


def test_resolver_never_rewrites_explicit_registry_when_selected_registry_is_configured():
    registry = WorkflowImageRegistry(
        endpoint="registry.example.com",
        namespace="bioinfoflow",
    )

    requirements = resolve_workflow_image_requirements(
        _schema(
            "quay.io/biocontainers/fastqc:0.12.1",
            "localhost:5000/demo/tool",
        ),
        selected_registry=registry,
    )

    assert [item.full_name for item in requirements] == [
        "quay.io/biocontainers/fastqc:0.12.1",
        "localhost:5000/demo/tool",
    ]
    assert [(item.name, item.tag, item.registry) for item in requirements] == [
        ("biocontainers/fastqc", "0.12.1", "quay.io"),
        ("demo/tool", "latest", "localhost:5000"),
    ]
    assert [item.explicit_registry for item in requirements] == [True, True]
    assert [item.rewrite_applied for item in requirements] == [False, False]
    assert [item.auth_config for item in requirements] == [None, None]


@pytest.mark.asyncio
async def test_prefetch_service_enqueues_resolved_static_image_pulls(
    db_session, monkeypatch
):
    calls: list[dict] = []

    class FakeImageService:
        def __init__(self, session):
            assert session is db_session

        async def pull_image(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(id="image-1")

    monkeypatch.setattr(workflow_image_module, "ImageService", FakeImageService)
    registry = WorkflowImageRegistry(
        endpoint="registry.example.com",
        namespace="team-a",
        registry_id="registry-1",
        auth_config={"identitytoken": "token"},
    )
    service = WorkflowImagePrefetchService(db_session, selected_registry=registry)

    result = await service.prefetch_schema(
        _schema(
            "bwa:0.7.17",
            "quay.io/biocontainers/fastqc:0.12.1",
            "${params.dynamic_image}",
        ),
        workflow_id="workflow-1",
    )

    assert [item.source_reference for item in result.enqueued] == [
        "bwa:0.7.17",
        "quay.io/biocontainers/fastqc:0.12.1",
    ]
    assert calls == [
        {
            "name": "team-a/bwa",
            "tag": "0.7.17",
            "registry": "registry.example.com",
            "project_id": None,
            "user_id": None,
            "workspace_id": None,
            "auth_config": {"identitytoken": "token"},
            "registry_id": None,
        },
        {
            "name": "biocontainers/fastqc",
            "tag": "0.12.1",
            "registry": "quay.io",
            "project_id": None,
            "user_id": None,
            "workspace_id": None,
            "auth_config": None,
            "registry_id": None,
        },
    ]


@pytest.mark.asyncio
async def test_prefetch_workflow_uses_workflow_selected_registry(
    db_session,
    monkeypatch,
):
    from app.services.container_registry_service import ContainerRegistryService

    registry = await ContainerRegistryService(db_session).create_registry(
        {
            "name": "Selected workflow registry",
            "endpoint": "https://selected-registry.example.test",
            "namespace": "selected",
            "credential_source": "stored",
            "username": "robot",
            "password": "secret",
            "updated_by": "user-1",
        }
    )
    calls: list[dict] = []

    class FakeImageService:
        def __init__(self, session):
            assert session is db_session

        async def pull_image(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(id="image-1")

    monkeypatch.setattr(workflow_image_module, "ImageService", FakeImageService)

    service = WorkflowImagePrefetchService(db_session)
    await service.prefetch_workflow(
        SimpleNamespace(
            id="workflow-1",
            container_registry_id=str(registry.id),
            schema_json=_schema("bwa:0.7.17"),
        )
    )

    assert calls == [
        {
            "name": "selected/bwa",
            "tag": "0.7.17",
            "registry": "selected-registry.example.test",
            "project_id": None,
            "user_id": None,
            "workspace_id": None,
            "auth_config": {"username": "robot", "password": "secret"},
            "registry_id": None,
        },
    ]


@pytest.mark.asyncio
async def test_async_resolver_attaches_credentials_by_exact_normalized_endpoint(
    db_session,
):
    from app.services.container_registry_service import ContainerRegistryService

    registry = await ContainerRegistryService(db_session).create_registry(
        {
            "name": "Harbor",
            "endpoint": "https://harbor.example.test",
            "namespace": "bio",
            "credential_source": "stored",
            "username": "robot",
            "password": "secret",
            "updated_by": "user-1",
        }
    )

    requirements = await resolve_workflow_image_requirements_with_credentials(
        db_session,
        _schema("harbor.example.test/bio/tool:1.0"),
        selected_registry=None,
    )

    assert len(requirements) == 1
    requirement = requirements[0]
    assert requirement.full_name == "harbor.example.test/bio/tool:1.0"
    assert requirement.name == "bio/tool"
    assert requirement.registry_id == str(registry.id)
    assert requirement.auth_config == {"username": "robot", "password": "secret"}


@pytest.mark.asyncio
async def test_async_resolver_does_not_attach_credentials_for_nonmatching_endpoint(
    db_session,
):
    from app.services.container_registry_service import ContainerRegistryService

    await ContainerRegistryService(db_session).create_registry(
        {
            "name": "Harbor",
            "endpoint": "https://harbor.example.test",
            "namespace": "bio",
            "credential_source": "stored",
            "username": "robot",
            "password": "secret",
            "updated_by": "user-1",
        }
    )

    requirements = await resolve_workflow_image_requirements_with_credentials(
        db_session,
        _schema("quay.io/biocontainers/tool:1.0"),
        selected_registry=None,
    )

    assert requirements[0].full_name == "quay.io/biocontainers/tool:1.0"
    assert requirements[0].registry_id is None
    assert requirements[0].auth_config is None


def test_resolver_uses_matching_selected_registry_credentials_for_explicit_host():
    registry = WorkflowImageRegistry(
        endpoint="https://harbor.example.test",
        namespace="bio",
        registry_id="registry-1",
        auth_config={"username": "robot", "password": "secret"},
    )

    requirements = resolve_workflow_image_requirements(
        _schema("harbor.example.test/bio/bwa:0.7.17"),
        selected_registry=registry,
    )

    assert len(requirements) == 1
    requirement = requirements[0]
    assert requirement.name == "bio/bwa"
    assert requirement.tag == "0.7.17"
    assert requirement.registry == "harbor.example.test"
    assert requirement.full_name == "harbor.example.test/bio/bwa:0.7.17"
    assert requirement.explicit_registry is True
    assert requirement.rewrite_applied is False
    assert requirement.registry_id == "registry-1"
    assert requirement.auth_config == {"username": "robot", "password": "secret"}
