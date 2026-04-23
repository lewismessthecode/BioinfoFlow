from __future__ import annotations

from types import SimpleNamespace

import pytest
from docker.errors import APIError, ImageNotFound

from app.services.docker_service import DockerService, _split_tag


class _FakeImage:
    def __init__(
        self,
        *,
        tags: list[str],
        size: int = 0,
        labels: dict | None = None,
        env: list[str] | None = None,
        entrypoint: list[str] | None = None,
    ) -> None:
        self.tags = tags
        self.labels = labels or {}
        self.attrs = {
            "Size": size,
            "Config": {
                "Labels": labels or {},
                "Env": env,
                "Entrypoint": entrypoint,
            },
        }


class _FakeImages:
    def __init__(
        self,
        *,
        listed: list[_FakeImage] | None = None,
        inspected: dict[str, _FakeImage] | None = None,
        remove_error: Exception | None = None,
    ) -> None:
        self._listed = listed or []
        self._inspected = inspected or {}
        self._remove_error = remove_error
        self.removed: list[tuple[str, bool]] = []

    def list(self) -> list[_FakeImage]:
        return self._listed

    def get(self, full_name: str) -> _FakeImage:
        image = self._inspected.get(full_name)
        if image is None:
            raise ImageNotFound("missing")
        return image

    def remove(self, full_name: str, force: bool = False) -> None:
        if self._remove_error is not None:
            raise self._remove_error
        self.removed.append((full_name, force))


def _service_with_client(images: _FakeImages) -> DockerService:
    service = DockerService(socket="unix:///tmp/docker.sock")
    service._client = SimpleNamespace(
        images=images,
        api=SimpleNamespace(pull=lambda *args, **kwargs: iter(())),
        containers=SimpleNamespace(list=lambda *args, **kwargs: []),
    )
    return service


def test_split_tag_keeps_registry_port_without_explicit_tag():
    assert _split_tag("localhost:5000/demo/tool") == (
        "localhost:5000/demo/tool",
        "latest",
    )


@pytest.mark.asyncio
async def test_list_images_preserves_full_name_for_custom_registries():
    service = _service_with_client(
        _FakeImages(
            listed=[
                _FakeImage(
                    tags=["ghcr.io/demo/tool:1.2.3"],
                    size=128,
                    labels={"maintainer": "bioinfoflow"},
                    env=["A=B"],
                    entrypoint=["tool"],
                )
            ]
        )
    )

    images = await service.list_images()

    assert len(images) == 1
    assert images[0].name == "demo/tool"
    assert images[0].registry == "ghcr.io"
    assert images[0].tag == "1.2.3"
    assert images[0].full_name == "ghcr.io/demo/tool:1.2.3"


@pytest.mark.asyncio
async def test_inspect_image_preserves_full_name_for_custom_registries():
    full_name = "ghcr.io/demo/tool:1.2.3"
    service = _service_with_client(
        _FakeImages(
            inspected={
                full_name: _FakeImage(
                    tags=[full_name],
                    size=256,
                    labels={"source": "test"},
                )
            }
        )
    )

    image = await service.inspect_image(full_name)

    assert image is not None
    assert image.name == "demo/tool"
    assert image.registry == "ghcr.io"
    assert image.full_name == full_name


@pytest.mark.asyncio
async def test_inspect_image_returns_none_for_missing_images():
    service = _service_with_client(_FakeImages())

    image = await service.inspect_image("missing:latest")

    assert image is None


@pytest.mark.asyncio
async def test_delete_image_returns_false_when_docker_rejects_delete():
    service = _service_with_client(
        _FakeImages(remove_error=APIError("delete failed"))
    )

    deleted = await service.delete_image("ghcr.io/demo/tool:1.2.3", force=True)

    assert deleted is False
