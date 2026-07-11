from __future__ import annotations

from dataclasses import dataclass

import pytest

from app.schemas.common import Pagination
from app.config import settings
from app.services import image_service
from app.services.docker_service import DockerImageInfo
from app.services.image_service import (
    DockerUnavailableError,
    ImageDeleteConflictError,
)
from app.utils.exceptions import PermissionDeniedError
from tests.support.auth import TEST_SESSION_COOKIE, create_better_auth_db


@dataclass
class FakeDockerService:
    async def is_available(self) -> bool:
        return True

    async def list_images(self, search: str | None = None):
        return [
            DockerImageInfo(
                name="bioinfoflow/listed-image",
                tag="v1.0.0",
                full_name="bioinfoflow/listed-image:v1.0.0",
                registry="docker.io",
                size_bytes=123,
                labels={"maintainer": "bioinfoflow"},
                env=["PATH=/usr/bin"],
                entrypoint=["/bin/bash"],
            )
        ]

    async def pull_image(self, name: str, tag: str, registry: str):
        yield {"progressDetail": {"current": 50, "total": 100}}

    async def inspect_image(self, full_name: str):
        return DockerImageInfo(
            name="bioinfoflow/bwa",
            tag="v2.2.1",
            full_name="bioinfoflow/bwa:v2.2.1",
            registry="docker.io",
            size_bytes=456,
            labels={"maintainer": "bioinfoflow"},
            env=["PATH=/usr/bin"],
            entrypoint=["/bin/bash"],
        )

    async def delete_image(self, full_name: str, force: bool = False) -> bool:
        return True

    async def get_image_usage(self, full_name: str):
        return []


@pytest.mark.asyncio
async def test_images_list_pull_delete(async_client, monkeypatch):
    monkeypatch.setattr(image_service, "DockerService", FakeDockerService)
    monkeypatch.setattr(
        image_service.background_tasks, "submit", lambda *args, **kwargs: None
    )

    list_resp = await async_client.get("/api/v1/images")
    assert list_resp.status_code == 200
    data = list_resp.json()["data"]
    assert data
    image_id = data[0]["id"]

    pull_resp = await async_client.post(
        "/api/v1/images/pull",
        json={"name": "bioinfoflow/bwa", "tag": "v2.2.1"},
    )
    assert pull_resp.status_code == 202
    assert pull_resp.json()["data"]["status"] == "pulling"

    delete_resp = await async_client.delete(f"/api/v1/images/{image_id}")
    assert delete_resp.status_code == 204


@pytest.mark.asyncio
async def test_images_pull_forwards_selected_registry_id(
    async_client,
    monkeypatch,
):
    registry_resp = await async_client.post(
        "/api/v1/container-registries",
        json={
            "name": "Harbor Bio",
            "endpoint": "https://harbor.example.test",
            "namespace": "bio",
            "credential_source": "stored",
            "username": "robot-user",
            "password": "top-secret-value",
        },
    )
    assert registry_resp.status_code == 201
    registry_id = registry_resp.json()["data"]["id"]
    captured: dict[str, object] = {}

    async def fake_pull(self, **kwargs):
        captured.update(kwargs)
        return type(
            "PulledImage",
            (),
            {
                "id": "00000000-0000-0000-0000-000000000001",
                "name": kwargs["name"],
                "tag": kwargs["tag"],
                "full_name": f"{kwargs['registry']}/{kwargs['name']}:{kwargs['tag']}",
                "registry": kwargs["registry"],
                "status": "pulling",
                "description": None,
                "size_bytes": None,
                "pull_progress": 0,
                "error_message": None,
                "labels": None,
                "env": None,
                "entrypoint": None,
                "created_at": "2026-06-29T00:00:00+00:00",
                "updated_at": "2026-06-29T00:00:00+00:00",
            },
        )()

    monkeypatch.setattr(image_service.ImageService, "pull_image", fake_pull)

    pull_resp = await async_client.post(
        "/api/v1/images/pull",
        json={
            "name": "bwa",
            "tag": "0.7.17",
            "registry_id": registry_id,
        },
    )

    assert pull_resp.status_code == 202
    assert captured["name"] == "bwa"
    assert captured["tag"] == "0.7.17"
    assert captured["registry"] == "docker.io"
    assert captured["registry_id"] == registry_id


@pytest.mark.asyncio
async def test_images_pull_registry_id_requires_admin_in_team_mode(
    async_client,
    tmp_path,
    monkeypatch,
):
    registry_resp = await async_client.post(
        "/api/v1/container-registries",
        json={
            "name": "Harbor Bio",
            "endpoint": "https://harbor.example.test",
            "credential_source": "none",
        },
    )
    assert registry_resp.status_code == 201
    registry_id = registry_resp.json()["data"]["id"]

    auth_db_path = tmp_path / "better-auth-member.db"
    create_better_auth_db(auth_db_path)
    monkeypatch.setattr(settings, "auth_mode", "team")
    monkeypatch.setattr(settings, "auth_enabled", True)
    monkeypatch.setattr(settings, "better_auth_db_path", str(auth_db_path))
    async_client.cookies.set("better-auth.session_token", TEST_SESSION_COOKIE)

    async def fake_pull(self, **kwargs):
        raise AssertionError("explicit registry pull should be rejected first")

    monkeypatch.setattr(image_service.ImageService, "pull_image", fake_pull)

    resp = await async_client.post(
        "/api/v1/images/pull",
        json={"name": "bwa", "tag": "0.7.17", "registry_id": registry_id},
    )

    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "PERMISSION_DENIED"


@pytest.mark.asyncio
async def test_images_load_tarball_ignores_default_registry(
    async_client,
    monkeypatch,
):
    registry_resp = await async_client.post(
        "/api/v1/container-registries",
        json={
            "name": "Harbor Bio",
            "endpoint": "https://harbor.example.test",
            "is_default": True,
            "credential_source": "none",
        },
    )
    assert registry_resp.status_code == 201
    captured: dict[str, object] = {}

    async def fake_load(self, **kwargs):
        captured.update(kwargs)
        return [
            type(
                "LoadedImage",
                (),
                {
                    "id": "00000000-0000-0000-0000-000000000001",
                    "name": "loaded/tool",
                    "tag": "latest",
                    "full_name": "loaded/tool:latest",
                    "registry": "docker.io",
                    "status": "local",
                    "description": None,
                    "size_bytes": None,
                    "pull_progress": None,
                    "error_message": None,
                    "labels": None,
                    "env": None,
                    "entrypoint": None,
                    "created_at": "2026-06-29T00:00:00+00:00",
                    "updated_at": "2026-06-29T00:00:00+00:00",
                },
            )()
        ]

    monkeypatch.setattr(image_service.ImageService, "load_image_tarball", fake_load)

    resp = await async_client.post(
        "/api/v1/images/load",
        files={"file": ("image.tar", b"tarball", "application/x-tar")},
    )

    assert resp.status_code == 201
    assert "registry_id" not in captured
    assert captured["content"] == b"tarball"


@pytest.mark.asyncio
async def test_images_list_reports_docker_status_metadata_and_force_sync(
    async_client, monkeypatch
):
    captured: dict[str, object] = {}

    async def fake_list_images(self, **kwargs):
        captured.update(kwargs)
        return (
            [],
            Pagination(limit=20, has_more=False, next_cursor=None, total_count=0),
            {
                "docker": "unavailable",
                "images_stale": True,
                "last_synced_at": "2026-04-08T08:00:00+00:00",
            },
        )

    monkeypatch.setattr(image_service.ImageService, "list_images", fake_list_images)

    resp = await async_client.get("/api/v1/images", params={"force_sync": "true"})

    assert resp.status_code == 200
    assert resp.json()["data"] == []
    assert resp.json()["meta"]["status"] == {
        "docker": "unavailable",
        "images_stale": True,
        "last_synced_at": "2026-04-08T08:00:00+00:00",
    }
    assert captured["force_sync"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ["/api/v1/images/pull", "/api/v1/images/load"])
async def test_images_docker_unavailable_for_pull_and_load(
    async_client, monkeypatch, route
):
    async def fake_pull(self, **kwargs):
        raise DockerUnavailableError("docker unavailable")

    async def fake_load(self, **kwargs):
        raise DockerUnavailableError("docker unavailable")

    monkeypatch.setattr(image_service.ImageService, "pull_image", fake_pull)
    monkeypatch.setattr(image_service.ImageService, "load_image_tarball", fake_load)

    if route.endswith("/pull"):
        resp = await async_client.post(
            route,
            json={"name": "bioinfoflow/bwa", "tag": "v2.2.1"},
        )
    else:
        resp = await async_client.post(
            route,
            files={"file": ("image.tar", b"tarball", "application/x-tar")},
        )

    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "SERVICE_UNAVAILABLE"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("route", "payload"),
    [
        ("/api/v1/images/pull", {"json": {"name": "bioinfoflow/bwa", "tag": "v2.2.1"}}),
        (
            "/api/v1/images/load",
            {"files": {"file": ("image.tar", b"tarball", "application/x-tar")}},
        ),
    ],
)
async def test_images_service_errors_have_stable_docker_error_semantics(
    async_client, monkeypatch, route, payload
):
    async def fake_pull(self, **kwargs):
        raise RuntimeError("pull exploded")

    async def fake_load(self, **kwargs):
        raise RuntimeError("load exploded")

    monkeypatch.setattr(image_service.ImageService, "pull_image", fake_pull)
    monkeypatch.setattr(image_service.ImageService, "load_image_tarball", fake_load)

    resp = await async_client.post(route, **payload)

    assert resp.status_code == 500
    assert resp.json()["error"]["code"] == "DOCKER_ERROR"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("route", "payload"),
    [
        ("/api/v1/images/pull", {"json": {"name": "bioinfoflow/bwa", "tag": "v2.2.1"}}),
        (
            "/api/v1/images/load",
            {"files": {"file": ("image.tar", b"tarball", "application/x-tar")}},
        ),
    ],
)
async def test_images_app_errors_escape_docker_error_catch_all(
    async_client, monkeypatch, route, payload
):
    async def fake_pull(self, **kwargs):
        raise PermissionDeniedError("project does not belong to workspace")

    async def fake_load(self, **kwargs):
        raise PermissionDeniedError("project does not belong to workspace")

    monkeypatch.setattr(image_service.ImageService, "pull_image", fake_pull)
    monkeypatch.setattr(image_service.ImageService, "load_image_tarball", fake_load)

    resp = await async_client.post(route, **payload)

    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "PERMISSION_DENIED"


@pytest.mark.asyncio
async def test_images_delete_missing_image_returns_not_found(async_client):
    resp = await async_client.delete(
        "/api/v1/images/00000000-0000-0000-0000-000000000001"
    )

    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_images_delete_failure_returns_docker_error(async_client, monkeypatch):
    class FakeImage:
        id = "img-1"
        full_name = "bioinfoflow/bwa:v2.2.1"

    async def fake_get(self, image_id: str):
        return FakeImage()

    async def fake_delete(self, image, force: bool = False):
        return False

    monkeypatch.setattr(image_service.ImageService, "get_image", fake_get)
    monkeypatch.setattr(image_service.ImageService, "delete_image", fake_delete)

    resp = await async_client.delete("/api/v1/images/img-1")

    assert resp.status_code == 500
    assert resp.json()["error"]["code"] == "DOCKER_ERROR"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("code", "details"),
    [
        ("IMAGE_PULLING", None),
        (
            "IMAGE_IN_USE",
            {"containers": [{"id": "container-1", "name": "analysis-runner"}]},
        ),
    ],
)
async def test_images_delete_conflicts_return_http_409(
    async_client, monkeypatch, code, details
):
    class FakeImage:
        id = "img-1"
        full_name = "bioinfoflow/bwa:v2.2.1"

    async def fake_get(self, image_id: str):
        return FakeImage()

    async def fake_delete(self, image, force: bool = False):
        raise ImageDeleteConflictError(code, "cannot delete image", details=details)

    monkeypatch.setattr(image_service.ImageService, "get_image", fake_get)
    monkeypatch.setattr(image_service.ImageService, "delete_image", fake_delete)

    resp = await async_client.delete("/api/v1/images/img-1")

    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == code
    assert resp.json()["error"]["details"] == details


# --- Phase 2 Fix 16: Image upload size limits ---


@pytest.mark.asyncio
async def test_image_load_rejects_oversized_tarball(async_client, monkeypatch):
    """Image tarballs exceeding max_image_upload_size_bytes must be rejected."""
    from app import config as config_module

    monkeypatch.setattr(config_module.settings, "max_image_upload_size_bytes", 100)

    oversized_content = b"x" * 200

    resp = await async_client.post(
        "/api/v1/images/load",
        files={"file": ("big.tar", oversized_content, "application/x-tar")},
    )
    assert resp.status_code == 413
    assert resp.json()["error"]["code"] == "FILE_TOO_LARGE"
