from __future__ import annotations

import asyncio
import ipaddress
import os
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

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


_PLAYWRIGHT_FAKE_IMAGES: dict[str, DockerImageInfo] = {}
_PLAYWRIGHT_TARBALL_IMAGE_PATTERN = re.compile(
    rb"BIOINFOFLOW_TEST_IMAGE=(?P<full_name>[^\s]+)"
)


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
        if _use_playwright_fake_docker():
            images = list(_PLAYWRIGHT_FAKE_IMAGES.values())
            if search:
                query = search.lower()
                return [image for image in images if query in image.name.lower()]
            return images

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
        if _use_playwright_fake_docker():
            return True

        def _ping() -> bool:
            try:
                return bool(self.client.ping())
            except Exception:
                return False

        return await asyncio.to_thread(_ping)

    async def registry_configuration_error(self, endpoint: str) -> str | None:
        parsed = urlparse(endpoint)
        if parsed.scheme != "http":
            return None
        registry = normalize_registry(endpoint)

        def _check() -> str | None:
            try:
                info = self.client.info()
            except Exception as exc:  # noqa: BLE001
                return f"Unable to inspect Docker registry configuration: {exc}"
            config = info.get("RegistryConfig") or {}
            index = (config.get("IndexConfigs") or {}).get(registry) or {}
            if index.get("Secure") is False:
                return None
            hostname = parsed.hostname
            if hostname:
                try:
                    address = ipaddress.ip_address(hostname)
                except ValueError:
                    # Docker resolves registry hostnames in the daemon's network
                    # namespace, which may differ from the backend container. A
                    # hostname may therefore be covered by an insecure CIDR even
                    # though this process cannot prove which address Docker uses.
                    return None
                for value in config.get("InsecureRegistryCIDRs") or []:
                    try:
                        if address in ipaddress.ip_network(value, strict=False):
                            return None
                    except ValueError:
                        continue
            return (
                f'Docker is not configured to allow the HTTP registry "{registry}". '
                "Add it to Docker's insecure-registries and restart Docker."
            )

        return await asyncio.to_thread(_check)

    async def test_registry(
        self,
        endpoint: str,
        *,
        auth_config: dict[str, Any] | None = None,
    ) -> str | None:
        configuration_error = await self.registry_configuration_error(endpoint)
        if configuration_error:
            return configuration_error
        registry = normalize_registry(endpoint)
        if auth_config:

            def _login() -> None:
                self.client.login(
                    username=auth_config.get("username"),
                    password=auth_config.get("password"),
                    registry=registry,
                    reauth=True,
                )

            try:
                await asyncio.to_thread(_login)
            except Exception as exc:  # noqa: BLE001
                return f"Registry authentication failed: {exc}"
            return None

        # Without credentials there is no repository-scoped Docker API call that
        # can probe a registry. A direct HTTP request would use the backend
        # container's network rather than the Docker daemon's pull boundary and
        # can reject registries that Docker can reach. Configuration validation is
        # therefore the strongest reliable preflight; the pull reports reachability.
        return None

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
        if _use_playwright_fake_docker():
            return _PLAYWRIGHT_FAKE_IMAGES.get(full_name)

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

    async def pull_image(
        self,
        name: str,
        tag: str,
        registry: str,
        *,
        auth_config: dict[str, Any] | None = None,
    ) -> Any:
        if _use_playwright_fake_docker():
            yield {"progressDetail": {"current": 50, "total": 100}}
            await asyncio.sleep(0)
            full_name = qualified_image_reference(name, tag, registry)
            _PLAYWRIGHT_FAKE_IMAGES[full_name] = _make_playwright_fake_image(
                full_name, registry=registry
            )
            return

        def _pull():
            repository = _apply_registry(name, registry)
            kwargs: dict[str, Any] = {
                "tag": tag,
                "stream": True,
                "decode": True,
            }
            if auth_config is not None:
                kwargs["auth_config"] = auth_config
            return self.client.api.pull(repository, **kwargs)

        stream = await asyncio.to_thread(_pull)
        iterator = iter(stream)
        done = object()

        def _next_event():
            try:
                return next(iterator)
            except StopIteration:
                return done

        while True:
            event = await asyncio.to_thread(_next_event)
            if event is done:
                break
            yield event

    async def delete_image(self, full_name: str, force: bool = False) -> bool:
        if _use_playwright_fake_docker():
            return _PLAYWRIGHT_FAKE_IMAGES.pop(full_name, None) is not None

        def _delete() -> bool:
            try:
                self.client.images.remove(full_name, force=force)
                return True
            except APIError:
                return False

        return await asyncio.to_thread(_delete)

    async def get_image_usage(self, full_name: str) -> list[dict[str, str]]:
        if _use_playwright_fake_docker():
            return []

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
        if _use_playwright_fake_docker():
            full_name = _parse_playwright_tarball_image(content)
            _PLAYWRIGHT_FAKE_IMAGES[full_name] = _make_playwright_fake_image(full_name)
            return [full_name]

        def _load() -> list[str]:
            result = self.client.images.load(content)
            tags: list[str] = []
            for image in result:
                tags.extend(image.tags)
            return tags

        return await asyncio.to_thread(_load)


def _use_playwright_fake_docker() -> bool:
    return os.getenv("BIOINFOFLOW_E2E_FAKE_DOCKER") == "1"


def _make_playwright_fake_image(
    full_name: str, *, registry: str | None = None
) -> DockerImageInfo:
    name, tag = _split_tag(full_name)
    detected_registry, normalized_name = _split_registry(name)
    return DockerImageInfo(
        name=normalized_name,
        tag=tag,
        full_name=full_name,
        registry=registry or detected_registry,
        size_bytes=32 * 1024 * 1024,
        labels={"maintainer": "bioinfoflow-e2e"},
        env=["PATH=/usr/local/bin"],
        entrypoint=["/bin/sh"],
    )


def _parse_playwright_tarball_image(content: bytes) -> str:
    match = _PLAYWRIGHT_TARBALL_IMAGE_PATTERN.search(content)
    if match:
        return match.group("full_name").decode("utf-8")
    return "bioinfoflow/tarball-import:1.0.0"


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


def normalize_registry(registry: str | None) -> str:
    value = str(registry or "").strip().rstrip("/")
    if "://" in value:
        parsed = urlparse(value)
        if parsed.netloc:
            value = parsed.netloc
    return value


def qualified_image_reference(name: str, tag: str, registry: str) -> str:
    return f"{_apply_registry(name, registry)}:{tag or 'latest'}"


def _apply_registry(name: str, registry: str) -> str:
    registry = normalize_registry(registry)
    if not registry or registry == "docker.io":
        return name
    detected_registry, _normalized_name = _split_registry(name)
    if detected_registry != "docker.io":
        return name
    if name.startswith(f"{registry}/"):
        return name
    return f"{registry}/{name}"
