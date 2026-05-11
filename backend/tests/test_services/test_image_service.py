from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.models.image import DockerImage, ImageStatus
from app.repositories.image_repo import ImageRepository
from app.schemas.common import Pagination
from app.services import image_service
from app.services.image_service import (
    DockerUnavailableError,
    ImageDeleteConflictError,
    ImageService,
)


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
    monkeypatch.setattr(image_service.ImageService, "_last_sync_at", stale_snapshot_time)

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

    monkeypatch.setattr(image_service, "DockerService", FakeDockerService)

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
