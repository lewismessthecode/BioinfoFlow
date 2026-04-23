from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import docker
from docker.errors import APIError, ImageNotFound

from app.config import settings


@dataclass
class DockerImageInfo:
    name: str
    tag: str
    full_name: str
    registry: str
    size_bytes: int | None
    labels: dict[str, Any] | None
    env: list[str] | None
    entrypoint: list[str] | None


class DockerService:
    def __init__(self, socket: str | None = None) -> None:
        self.socket = socket or settings.docker_socket
        self._client: docker.DockerClient | None = None

    @property
    def client(self) -> docker.DockerClient:
        if self._client is None:
            self._client = docker.DockerClient(base_url=self.socket)
        return self._client

    async def list_images(self, search: str | None = None) -> list[DockerImageInfo]:
        def _list() -> list[DockerImageInfo]:
            images: list[DockerImageInfo] = []
            for image in self.client.images.list():
                for tag in image.tags:
                    name, version = _split_tag(tag)
                    registry, normalized_name = _split_registry(name)
                    if search and search.lower() not in normalized_name.lower():
                        continue
                    config = image.attrs.get("Config") or {}
                    images.append(
                        DockerImageInfo(
                            name=normalized_name,
                            tag=version,
                            full_name=tag,
                            registry=registry,
                            size_bytes=image.attrs.get("Size"),
                            labels=image.labels or config.get("Labels") or {},
                            env=config.get("Env"),
                            entrypoint=config.get("Entrypoint"),
                        )
                    )
            return images

        return await asyncio.to_thread(_list)

    async def is_available(self) -> bool:
        def _ping() -> bool:
            try:
                return bool(self.client.ping())
            except Exception:
                return False

        return await asyncio.to_thread(_ping)

    async def check_nvidia_runtime(self) -> bool:
        """Check if Docker NVIDIA runtime is available."""

        def _check() -> bool:
            try:
                info = self.client.info()
                runtimes = info.get("Runtimes", {})
                return "nvidia" in runtimes
            except Exception:
                return False

        return await asyncio.to_thread(_check)

    async def get_parabricks_image(self) -> DockerImageInfo | None:
        """Check if Parabricks image is available locally."""
        parabricks_images = [
            "nvcr.io/nvidia/clara/clara-parabricks:4.6.0-1",
            "nvcr.io/nvidia/clara/clara-parabricks:4.5.0-1",
            "nvcr.io/nvidia/clara/clara-parabricks:4.4.0-1",
        ]
        for image_name in parabricks_images:
            image = await self.inspect_image(image_name)
            if image:
                return image
        return None

    async def inspect_image(self, full_name: str) -> DockerImageInfo | None:
        def _inspect() -> DockerImageInfo | None:
            try:
                image = self.client.images.get(full_name)
            except ImageNotFound:
                return None

            name, version = _split_tag(full_name)
            registry, normalized_name = _split_registry(name)
            config = image.attrs.get("Config") or {}
            return DockerImageInfo(
                name=normalized_name,
                tag=version,
                full_name=full_name,
                registry=registry,
                size_bytes=image.attrs.get("Size"),
                labels=image.labels or config.get("Labels") or {},
                env=config.get("Env"),
                entrypoint=config.get("Entrypoint"),
            )

        return await asyncio.to_thread(_inspect)

    async def pull_image(self, name: str, tag: str, registry: str) -> Any:
        def _pull():
            repository = _apply_registry(name, registry)
            return self.client.api.pull(repository, tag=tag, stream=True, decode=True)

        stream = await asyncio.to_thread(_pull)
        for event in stream:
            yield event

    async def delete_image(self, full_name: str, force: bool = False) -> bool:
        def _delete() -> bool:
            try:
                self.client.images.remove(full_name, force=force)
                return True
            except APIError:
                return False

        return await asyncio.to_thread(_delete)

    async def get_image_usage(self, full_name: str) -> list[dict[str, str]]:
        def _list_usage() -> list[dict[str, str]]:
            containers = self.client.containers.list(
                all=True,
                filters={"ancestor": full_name},
            )
            return [
                {
                    "id": container.id[:12],
                    "name": getattr(container, "name", container.id[:12]),
                }
                for container in containers
            ]

        return await asyncio.to_thread(_list_usage)

    async def load_image(self, content: bytes) -> list[str]:
        def _load() -> list[str]:
            result = self.client.images.load(content)
            tags: list[str] = []
            for image in result:
                tags.extend(image.tags)
            return tags

        return await asyncio.to_thread(_load)


def _split_tag(full_name: str) -> tuple[str, str]:
    last_segment = full_name.rsplit("/", 1)[-1]
    if ":" in last_segment:
        name, tag = full_name.rsplit(":", 1)
        return name, tag
    return full_name, "latest"


def _split_registry(name: str) -> tuple[str, str]:
    parts = name.split("/")
    if len(parts) > 1 and (
        "." in parts[0] or ":" in parts[0] or parts[0] == "localhost"
    ):
        return parts[0], "/".join(parts[1:])
    return "docker.io", name


def _apply_registry(name: str, registry: str) -> str:
    if not registry or registry == "docker.io":
        return name
    if name.startswith(f"{registry}/"):
        return name
    return f"{registry}/{name}"
