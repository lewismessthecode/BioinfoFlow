from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import Mock

import pytest

from app.models.image import DockerImage, ImageStatus
from app.models.project import Project
from app.repositories.image_repo import ImageRepository
from app.schemas.common import Pagination
from app.services import image_service
from app.services.image_service import (
    DockerUnavailableError,
    ImageDeleteConflictError,
    ImageService,
)
from app.utils.exceptions import ConfigurationError, PermissionDeniedError


@pytest.mark.asyncio
async def test_image_service_list_images_force_sync_bypasses_ttl(
    db_session, monkeypatch
):
    calls = {"list_images": 0}

    class FakeDockerService:
        async def list_images(self, search: str | None = None):
            calls["list_images"] += 1
            return []

    monkeypatch.setattr(image_service, "DockerService", FakeDockerService)
    monkeypatch.setattr(
        image_service.ImageService,
        "_last_sync_at",
        datetime.now(timezone.utc),
    )

    service = ImageService(db_session)

    _, pagination, status = await service.list_images(force_sync=True)

    assert calls["list_images"] == 1
    assert isinstance(pagination, Pagination)
    assert status["docker"] == "available"
    assert status["images_stale"] is False
    assert status["last_synced_at"] is not None


@pytest.mark.asyncio
async def test_image_service_list_images_reports_stale_metadata_when_docker_unavailable(
    db_session, monkeypatch
):
    stale_snapshot_time = datetime(2026, 4, 8, 8, 0, tzinfo=timezone.utc)
    target_full_name = "bioinfoflow/stale-snapshot:v1.2.3"

    image = DockerImage(
        name="bioinfoflow/stale-snapshot",
        tag="v1.2.3",
        full_name=target_full_name,
        status=ImageStatus.LOCAL,
        registry="docker.io",
    )
    db_session.add(image)
    await db_session.commit()

    class FakeDockerService:
        async def list_images(self, search: str | None = None):
            raise RuntimeError("docker unavailable")

    monkeypatch.setattr(image_service, "DockerService", FakeDockerService)
    monkeypatch.setattr(
        image_service.ImageService, "_last_sync_at", stale_snapshot_time
    )

    service = ImageService(db_session)

    images, _, status = await service.list_images(force_sync=True)

    assert target_full_name in {item.full_name for item in images}
    assert status == {
        "docker": "unavailable",
        "images_stale": True,
        "last_synced_at": stale_snapshot_time,
    }


@pytest.mark.asyncio
async def test_image_service_pull_checks_docker_before_creating_record(
    db_session, monkeypatch
):
    target_full_name = "bioinfoflow/test-no-create:v9.9.9"

    class FakeDockerService:
        async def is_available(self) -> bool:
            return False

    monkeypatch.setattr(image_service, "DockerService", FakeDockerService)

    service = ImageService(db_session)

    with pytest.raises(DockerUnavailableError):
        await service.pull_image(
            name="bioinfoflow/test-no-create",
            tag="v9.9.9",
            registry="docker.io",
        )

    repo = ImageRepository(db_session)
    images, _ = await repo.list(limit=20)
    assert target_full_name not in {image.full_name for image in images}


@pytest.mark.asyncio
async def test_image_service_pull_task_marks_failed_when_pull_raises(
    db_session, monkeypatch
):
    image = DockerImage(
        name="bioinfoflow/bwa",
        tag="v2.2.1",
        full_name="bioinfoflow/bwa:v2.2.1",
        status=ImageStatus.PULLING,
        registry="docker.io",
        pull_progress=0,
    )
    db_session.add(image)
    await db_session.commit()

    class FakeDockerService:
        async def pull_image(self, name: str, tag: str, registry: str):
            for progress in ():
                yield progress
            raise RuntimeError("pull exploded")

    pull_failed = Mock()
    monkeypatch.setattr(image_service, "DockerService", FakeDockerService)
    monkeypatch.setattr(
        image_service,
        "logger",
        type("FakeLogger", (), {"exception": pull_failed})(),
        raising=False,
    )

    service = ImageService(db_session)
    repo = ImageRepository(db_session)

    await service._pull_task_with_repo(
        repo,
        image.id,
        "bioinfoflow/bwa",
        "v2.2.1",
        "docker.io",
        None,
    )

    stored = await repo.get(str(image.id))
    assert stored is not None
    assert stored.status == ImageStatus.FAILED.value
    assert stored.error_message == "pull exploded"
    pull_failed.assert_called_once()
    assert pull_failed.call_args.args[0] == "image.pull.failed"
    assert pull_failed.call_args.kwargs["image_id"] == str(image.id)
    assert pull_failed.call_args.kwargs["error"] == "pull exploded"


@pytest.mark.asyncio
async def test_image_service_rejects_http_registry_missing_from_docker_configuration(
    db_session,
    monkeypatch,
):
    from app.services.container_registry_service import ContainerRegistryService

    registry = await ContainerRegistryService(db_session).create_registry(
        {
            "name": "Harbor HTTP",
            "endpoint": "http://10.227.4.56:80",
            "namespace": "pipeline-dev",
            "insecure": True,
            "credential_source": "none",
            "updated_by": "user-1",
        }
    )

    class FakeDockerService:
        async def is_available(self) -> bool:
            return True

        async def registry_configuration_error(self, endpoint: str):
            assert endpoint == "http://10.227.4.56:80"
            return "Docker must trust this HTTP registry via insecure-registries"

    monkeypatch.setattr(image_service, "DockerService", FakeDockerService)
    service = ImageService(db_session)

    with pytest.raises(ConfigurationError, match="insecure-registries"):
        await service.pull_image(
            name="oseq-report",
            tag="V4.0.0",
            registry_id=str(registry.id),
        )

    images, _ = await ImageRepository(db_session).list(limit=20)
    assert "10.227.4.56:80/pipeline-dev/oseq-report:V4.0.0" not in {
        image.full_name for image in images
    }


@pytest.mark.asyncio
async def test_image_service_delete_image_rejects_pulling_state(db_session):
    image = DockerImage(
        name="bioinfoflow/bwa",
        tag="v2.2.1",
        full_name="bioinfoflow/bwa:v2.2.1",
        status=ImageStatus.PULLING,
        registry="docker.io",
    )
    db_session.add(image)
    await db_session.commit()

    service = ImageService(db_session)

    with pytest.raises(ImageDeleteConflictError) as exc_info:
        await service.delete_image(image)

    assert exc_info.value.code == "IMAGE_PULLING"


@pytest.mark.asyncio
async def test_image_service_delete_image_removes_failed_record_without_docker(
    db_session, monkeypatch
):
    image = DockerImage(
        name="bioinfoflow/bwa",
        tag="v2.2.1",
        full_name="bioinfoflow/bwa:v2.2.1",
        status=ImageStatus.FAILED,
        registry="docker.io",
    )
    db_session.add(image)
    await db_session.commit()
    image_id = str(image.id)

    class FakeDockerService:
        async def get_image_usage(self, full_name: str):
            raise AssertionError("failed image deletion should not inspect Docker")

    monkeypatch.setattr(image_service, "DockerService", FakeDockerService)

    service = ImageService(db_session)

    deleted = await service.delete_image(image)

    assert deleted is True
    assert await ImageRepository(db_session).get(image_id) is None


@pytest.mark.asyncio
async def test_image_service_delete_image_rejects_images_in_use(
    db_session, monkeypatch
):
    image = DockerImage(
        name="bioinfoflow/bwa",
        tag="v2.2.1",
        full_name="bioinfoflow/bwa:v2.2.1",
        status=ImageStatus.LOCAL,
        registry="docker.io",
    )
    db_session.add(image)
    await db_session.commit()

    class FakeDockerService:
        async def get_image_usage(self, full_name: str):
            return [{"id": "container-1", "name": "analysis-runner"}]

    monkeypatch.setattr(image_service, "DockerService", FakeDockerService)

    service = ImageService(db_session)

    with pytest.raises(ImageDeleteConflictError) as exc_info:
        await service.delete_image(image)

    assert exc_info.value.code == "IMAGE_IN_USE"
    assert exc_info.value.details == {
        "containers": [{"id": "container-1", "name": "analysis-runner"}]
    }


@pytest.mark.asyncio
async def test_image_service_pull_allows_project_context_within_same_workspace(
    db_session, monkeypatch
):
    project = Project(
        name="Image Project",
        storage_mode="managed",
        external_root_path=None,
        user_id="project-owner",
        created_by_user_id="project-owner",
        workspace_id="workspace-a",
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)

    class FakeDockerService:
        async def is_available(self) -> bool:
            return True

    captured: dict[str, object] = {}

    def fake_submit(func, *args, **kwargs):
        captured["func"] = func
        captured["args"] = args
        captured["kwargs"] = kwargs

    monkeypatch.setattr(image_service, "DockerService", FakeDockerService)
    monkeypatch.setattr(image_service.background_tasks, "submit", fake_submit)

    service = ImageService(db_session)

    image = await service.pull_image(
        name="bioinfoflow/bwa",
        tag="v2.2.1",
        registry="docker.io",
        project_id=str(project.id),
        user_id="requestor",
        workspace_id="workspace-a",
    )

    assert image.status == ImageStatus.PULLING.value
    assert captured["func"] == service._pull_task
    assert captured["args"][-1] == str(project.id)


@pytest.mark.asyncio
async def test_image_service_pull_without_custom_registry_keeps_unqualified_full_name(
    db_session, monkeypatch
):
    captured: dict[str, object] = {}

    class FakeDockerService:
        async def is_available(self) -> bool:
            return True

    def fake_submit(func, *args, **kwargs):
        captured["func"] = func
        captured["args"] = args
        captured["kwargs"] = kwargs

    monkeypatch.setattr(image_service, "DockerService", FakeDockerService)
    monkeypatch.setattr(image_service.background_tasks, "submit", fake_submit)

    service = ImageService(db_session)

    image = await service.pull_image(name="ubuntu", tag="22.04")

    assert image.name == "ubuntu"
    assert image.tag == "22.04"
    assert image.full_name == "ubuntu:22.04"
    assert image.registry == "docker.io"
    assert captured["args"] == (
        image.id,
        "ubuntu",
        "22.04",
        "docker.io",
        None,
    )
    assert captured["kwargs"] == {}


@pytest.mark.asyncio
async def test_image_service_pull_records_custom_registry_and_auth_task_metadata(
    db_session, monkeypatch
):
    captured: dict[str, object] = {}

    class FakeDockerService:
        async def is_available(self) -> bool:
            return True

    def fake_submit(func, *args, **kwargs):
        captured["func"] = func
        captured["args"] = args
        captured["kwargs"] = kwargs

    monkeypatch.setattr(image_service, "DockerService", FakeDockerService)
    monkeypatch.setattr(image_service.background_tasks, "submit", fake_submit)

    service = ImageService(db_session)

    image = await service.pull_image(
        name="team/tool",
        tag="1.0.0",
        registry="registry.example.com",
        auth_config={"username": "bioinfoflow", "password": "secret"},
    )

    assert image.name == "team/tool"
    assert image.tag == "1.0.0"
    assert image.full_name == "registry.example.com/team/tool:1.0.0"
    assert image.registry == "registry.example.com"
    assert captured["args"] == (
        image.id,
        "team/tool",
        "1.0.0",
        "registry.example.com",
        None,
    )
    assert captured["kwargs"] == {
        "auth_config": {"username": "bioinfoflow", "password": "secret"},
    }


@pytest.mark.asyncio
async def test_image_service_pull_resolves_registry_id_namespace_and_auth(
    db_session,
    monkeypatch,
):
    from app.services.container_registry_service import ContainerRegistryService

    registry = await ContainerRegistryService(db_session).create_registry(
        {
            "name": "Harbor Bio",
            "endpoint": "https://harbor.example.test",
            "namespace": "bio",
            "credential_source": "stored",
            "username": "robot-user",
            "password": "top-secret-value",
            "updated_by": "user-1",
        }
    )
    captured: dict[str, object] = {}

    class FakeDockerService:
        async def is_available(self) -> bool:
            return True

    def fake_submit(func, *args, **kwargs):
        captured["func"] = func
        captured["args"] = args
        captured["kwargs"] = kwargs

    monkeypatch.setattr(image_service, "DockerService", FakeDockerService)
    monkeypatch.setattr(image_service.background_tasks, "submit", fake_submit)

    service = ImageService(db_session)

    image = await service.pull_image(
        name="bwa",
        tag="0.7.17",
        registry_id=str(registry.id),
    )

    assert image.name == "bio/bwa"
    assert image.tag == "0.7.17"
    assert image.registry == "harbor.example.test"
    assert image.full_name == "harbor.example.test/bio/bwa:0.7.17"
    assert captured["args"] == (
        image.id,
        "bio/bwa",
        "0.7.17",
        "harbor.example.test",
        None,
    )
    assert captured["kwargs"] == {
        "auth_config": {"username": "robot-user", "password": "top-secret-value"},
        "registry_id": str(registry.id),
    }


@pytest.mark.asyncio
async def test_image_service_pull_respects_explicit_registry_with_registry_id(
    db_session,
    monkeypatch,
):
    from app.services.container_registry_service import ContainerRegistryService

    registry = await ContainerRegistryService(db_session).create_registry(
        {
            "name": "Harbor Bio",
            "endpoint": "http://harbor.example.test",
            "insecure": True,
            "namespace": "bio",
            "credential_source": "stored",
            "username": "robot-user",
            "password": "top-secret-value",
            "updated_by": "user-1",
        }
    )
    captured: dict[str, object] = {}

    class FakeDockerService:
        async def is_available(self) -> bool:
            return True

        async def registry_configuration_error(self, endpoint: str):
            raise AssertionError(
                f"unused selected registry should not be checked: {endpoint}"
            )

    def fake_submit(func, *args, **kwargs):
        captured["func"] = func
        captured["args"] = args
        captured["kwargs"] = kwargs

    monkeypatch.setattr(image_service, "DockerService", FakeDockerService)
    monkeypatch.setattr(image_service.background_tasks, "submit", fake_submit)

    service = ImageService(db_session)

    image = await service.pull_image(
        name="quay.io/biocontainers/fastqc",
        tag="0.12.1",
        registry_id=str(registry.id),
    )

    assert image.name == "biocontainers/fastqc"
    assert image.tag == "0.12.1"
    assert image.registry == "quay.io"
    assert image.full_name == "quay.io/biocontainers/fastqc:0.12.1"
    assert captured["args"] == (
        image.id,
        "biocontainers/fastqc",
        "0.12.1",
        "quay.io",
        None,
    )
    assert captured["kwargs"] == {}


@pytest.mark.asyncio
async def test_image_service_pull_uses_auth_for_matching_explicit_registry(
    db_session,
    monkeypatch,
):
    from app.services.container_registry_service import ContainerRegistryService

    registry = await ContainerRegistryService(db_session).create_registry(
        {
            "name": "Harbor Bio",
            "endpoint": "https://harbor.example.test",
            "namespace": "bio",
            "credential_source": "stored",
            "username": "robot-user",
            "password": "top-secret-value",
            "updated_by": "user-1",
        }
    )
    captured: dict[str, object] = {}

    class FakeDockerService:
        async def is_available(self) -> bool:
            return True

    def fake_submit(func, *args, **kwargs):
        captured["func"] = func
        captured["args"] = args
        captured["kwargs"] = kwargs

    monkeypatch.setattr(image_service, "DockerService", FakeDockerService)
    monkeypatch.setattr(image_service.background_tasks, "submit", fake_submit)

    service = ImageService(db_session)

    image = await service.pull_image(
        name="harbor.example.test/bio/bwa",
        tag="0.7.17",
        registry_id=str(registry.id),
    )

    assert image.name == "bio/bwa"
    assert image.tag == "0.7.17"
    assert image.registry == "harbor.example.test"
    assert image.full_name == "harbor.example.test/bio/bwa:0.7.17"
    assert captured["args"] == (
        image.id,
        "bio/bwa",
        "0.7.17",
        "harbor.example.test",
        None,
    )
    assert captured["kwargs"] == {
        "auth_config": {"username": "robot-user", "password": "top-secret-value"},
        "registry_id": str(registry.id),
    }


@pytest.mark.asyncio
async def test_image_service_pull_rejects_project_context_from_other_workspace(
    db_session, monkeypatch
):
    project = Project(
        name="Other Workspace Project",
        storage_mode="managed",
        external_root_path=None,
        user_id="project-owner",
        created_by_user_id="project-owner",
        workspace_id="workspace-b",
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)

    class FakeDockerService:
        async def is_available(self) -> bool:
            return True

    monkeypatch.setattr(image_service, "DockerService", FakeDockerService)

    service = ImageService(db_session)

    with pytest.raises(PermissionDeniedError, match="project does not belong"):
        await service.pull_image(
            name="bioinfoflow/bwa",
            tag="v2.2.1",
            registry="docker.io",
            project_id=str(project.id),
            user_id="requestor",
            workspace_id="workspace-a",
        )
