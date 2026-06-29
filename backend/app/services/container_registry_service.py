from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import os
from typing import Any
from urllib.parse import urlparse

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project
from app.models.container_registry import (
    ContainerRegistry,
    ContainerRegistryCredentialSource,
    ContainerRegistryStatus,
)
from app.repositories.container_registry_repo import ContainerRegistryRepository
from app.services.docker_service import normalize_registry
from app.services.llm.credentials import (
    decrypt_secret,
    encrypt_secret,
    generate_credential_fingerprint,
    mask_secret,
)
from app.utils.exceptions import ConflictError, NotFoundError


@dataclass(frozen=True)
class ContainerRegistryAuthMaterial:
    registry_id: str
    endpoint: str
    namespace: str | None
    insecure: bool
    source: str
    username: str | None
    password: str | None


@dataclass(frozen=True)
class ContainerRegistryImageTarget:
    name: str
    tag: str
    registry: str
    auth_config: dict[str, str] | None
    registry_id: str | None


class ContainerRegistryService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.registry_repo = ContainerRegistryRepository(session)

    async def list_registries(self) -> list[ContainerRegistry]:
        return await self.registry_repo.list_all()

    async def get_registry(self, registry_id: str) -> ContainerRegistry:
        registry = await self.registry_repo.get(registry_id)
        if registry is None:
            raise NotFoundError(f"Container registry not found: {registry_id}")
        return registry

    async def create_registry(self, data: dict[str, Any]) -> ContainerRegistry:
        endpoint = _normalize_endpoint(data.get("endpoint"), data.get("insecure", False))
        payload = {
            "name": _required_text(data.get("name"), "Registry name is required"),
            "endpoint": endpoint,
            "namespace": _normalize_namespace(data.get("namespace")),
            "insecure": bool(data.get("insecure", False)),
            "is_default": bool(data.get("is_default", False)),
            "last_status": ContainerRegistryStatus.UNTESTED,
            "last_error": None,
            "last_checked_at": None,
            "updated_by": data.get("updated_by"),
        }
        payload.update(_credential_payload(data, existing=None))
        if payload["is_default"]:
            await self.registry_repo.unset_default_except()
        try:
            return await self.registry_repo.create(**payload)
        except IntegrityError as exc:
            await self.registry_repo.session.rollback()
            raise ConflictError(
                "Only one container registry can be the default"
            ) from exc

    async def update_registry(
        self,
        registry_id: str,
        data: dict[str, Any],
    ) -> ContainerRegistry:
        registry = await self.get_registry(registry_id)
        updates = _registry_updates(data, registry)
        if updates.get("is_default") is True:
            await self.registry_repo.unset_default_except(str(registry.id))
        try:
            return await self.registry_repo.update_all(registry, **updates)
        except IntegrityError as exc:
            await self.registry_repo.session.rollback()
            raise ConflictError(
                "Only one container registry can be the default"
            ) from exc

    async def delete_registry(self, registry_id: str) -> None:
        registry = await self.get_registry(registry_id)
        await self.registry_repo.delete(registry)

    async def test_registry(self, registry_id: str) -> dict[str, Any]:
        registry = await self.get_registry(registry_id)
        checked_at = datetime.now(timezone.utc)
        error = self._availability_error(await self.resolve_auth_material(registry_id))
        status = (
            ContainerRegistryStatus.ERROR
            if error
            else ContainerRegistryStatus.OK
        )
        registry = await self.registry_repo.update_all(
            registry,
            last_status=status,
            last_error=error,
            last_checked_at=checked_at,
        )
        return {
            "registry_id": str(registry.id),
            "success": status == ContainerRegistryStatus.OK,
            "status": status,
            "error": error,
            "checked_at": registry.last_checked_at,
        }

    async def resolve_auth_material(
        self,
        registry_id: str,
    ) -> ContainerRegistryAuthMaterial:
        registry = await self.get_registry(registry_id)
        username: str | None = None
        password: str | None = None
        if registry.credential_source == ContainerRegistryCredentialSource.ENV:
            username = os.getenv(registry.env_username_var or "") or None
            password = os.getenv(registry.env_password_var or "") or None
        elif registry.credential_source == ContainerRegistryCredentialSource.STORED:
            username = decrypt_secret(registry.encrypted_username)
            password = decrypt_secret(registry.encrypted_password)
        return ContainerRegistryAuthMaterial(
            registry_id=str(registry.id),
            endpoint=registry.endpoint,
            namespace=registry.namespace,
            insecure=registry.insecure,
            source=registry.credential_source,
            username=username,
            password=password,
        )

    async def resolve_image_target(
        self,
        *,
        registry_id: str,
        name: str,
        tag: str | None = None,
    ) -> ContainerRegistryImageTarget:
        material = await self.resolve_auth_material(registry_id)
        reference = _image_reference_from_payload(name, tag)
        name_part, resolved_tag = _split_image_tag(reference)
        detected_registry, image_name, explicit_registry = _split_image_registry(
            name_part
        )
        if explicit_registry:
            registry_matches = detected_registry == normalize_registry(material.endpoint)
            return ContainerRegistryImageTarget(
                name=image_name,
                tag=resolved_tag,
                registry=detected_registry,
                auth_config=(
                    _auth_config_from_material(material) if registry_matches else None
                ),
                registry_id=material.registry_id if registry_matches else None,
            )

        namespace = _normalize_namespace(material.namespace)
        if namespace:
            image_name = f"{namespace}/{image_name}"
        return ContainerRegistryImageTarget(
            name=image_name,
            tag=resolved_tag,
            registry=normalize_registry(material.endpoint),
            auth_config=_auth_config_from_material(material),
            registry_id=material.registry_id,
        )

    async def get_effective_registry(
        self,
        *,
        project_id: str | None = None,
    ) -> ContainerRegistry | None:
        if project_id:
            project = await self.session.get(Project, project_id)
            if project is None:
                raise NotFoundError(f"Project not found: {project_id}")
            if project.container_registry_id:
                registry = await self.registry_repo.get(str(project.container_registry_id))
                if registry is not None:
                    return registry
        return await self.registry_repo.get_default()

    def registry_read_dict(self, registry: ContainerRegistry) -> dict[str, Any]:
        return {
            "id": str(registry.id),
            "name": registry.name,
            "endpoint": registry.endpoint,
            "namespace": registry.namespace,
            "insecure": registry.insecure,
            "is_default": registry.is_default,
            "credential_source": registry.credential_source,
            "env_username_var": registry.env_username_var,
            "env_password_var": registry.env_password_var,
            "username_hint": registry.username_hint,
            "password_hint": registry.password_hint,
            "last_status": registry.last_status,
            "last_error": registry.last_error,
            "last_checked_at": registry.last_checked_at,
            "created_at": registry.created_at,
            "updated_at": registry.updated_at,
        }

    def _availability_error(
        self,
        material: ContainerRegistryAuthMaterial,
    ) -> str | None:
        if material.source == ContainerRegistryCredentialSource.NONE:
            return None
        if material.username and material.password:
            return None
        return "Registry credentials are not available"


def _registry_updates(
    data: dict[str, Any],
    registry: ContainerRegistry,
) -> dict[str, Any]:
    updates: dict[str, Any] = {}
    if "name" in data:
        updates["name"] = _required_text(data.get("name"), "Registry name is required")
    if "endpoint" in data:
        insecure = data.get("insecure", registry.insecure)
        updates["endpoint"] = _normalize_endpoint(data.get("endpoint"), insecure)
    if "namespace" in data:
        updates["namespace"] = _normalize_namespace(data.get("namespace"))
    if "insecure" in data:
        updates["insecure"] = bool(data["insecure"])
        endpoint = updates.get("endpoint", registry.endpoint)
        _normalize_endpoint(endpoint, updates["insecure"])
    if "is_default" in data:
        updates["is_default"] = bool(data["is_default"])
    if "updated_by" in data:
        updates["updated_by"] = data.get("updated_by")

    credential_keys = {
        "credential_source",
        "env_username_var",
        "env_password_var",
        "username",
        "password",
    }
    if credential_keys.intersection(data):
        updates.update(_credential_payload(data, existing=registry))
    return updates


def _credential_payload(
    data: dict[str, Any],
    *,
    existing: ContainerRegistry | None,
) -> dict[str, Any]:
    source = str(
        data.get(
            "credential_source",
            existing.credential_source if existing is not None else "none",
        )
        or "none"
    )
    if source == ContainerRegistryCredentialSource.ENV:
        username_var = _text_or_existing(
            data,
            "env_username_var",
            existing.env_username_var if existing is not None else None,
        )
        password_var = _text_or_existing(
            data,
            "env_password_var",
            existing.env_password_var if existing is not None else None,
        )
        if not username_var or not password_var:
            raise ValueError("Registry environment username and password variables are required")
        return {
            "credential_source": source,
            "env_username_var": username_var,
            "env_password_var": password_var,
            "encrypted_username": None,
            "encrypted_password": None,
            "credential_fingerprint": None,
            "username_hint": f"env:{username_var}",
            "password_hint": f"env:{password_var}",
        }
    if source == ContainerRegistryCredentialSource.STORED:
        username_supplied = "username" in data
        password_supplied = "password" in data
        changing_source = (
            existing is None
            or existing.credential_source != ContainerRegistryCredentialSource.STORED
        )
        if username_supplied or password_supplied or changing_source:
            username = _required_text(data.get("username"), "Registry username is required")
            password = str(data.get("password") or "")
            if not password:
                raise ValueError("Registry password is required")
            return {
                "credential_source": source,
                "env_username_var": None,
                "env_password_var": None,
                "encrypted_username": encrypt_secret(username),
                "encrypted_password": encrypt_secret(password),
                "credential_fingerprint": generate_credential_fingerprint(),
                "username_hint": mask_secret(username),
                "password_hint": mask_secret(password),
            }
        return {
            "credential_source": source,
        }
    if source != ContainerRegistryCredentialSource.NONE:
        raise ValueError(f"Unknown registry credential source: {source}")
    return {
        "credential_source": ContainerRegistryCredentialSource.NONE,
        "env_username_var": None,
        "env_password_var": None,
        "encrypted_username": None,
        "encrypted_password": None,
        "credential_fingerprint": None,
        "username_hint": None,
        "password_hint": None,
    }


def _required_text(value: Any, message: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(message)
    return text


def _text_or_existing(
    data: dict[str, Any],
    key: str,
    existing: str | None,
) -> str | None:
    if key not in data:
        return existing
    text = str(data.get(key) or "").strip()
    return text or None


def _normalize_namespace(value: Any) -> str | None:
    if value is None:
        return None
    namespace = str(value).strip().strip("/")
    return namespace or None


def _normalize_endpoint(value: Any, insecure: bool) -> str:
    endpoint = _required_text(value, "Registry endpoint is required").rstrip("/")
    parsed = urlparse(endpoint)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Registry endpoint must be an absolute HTTP(S) URL")
    if parsed.scheme == "http" and not insecure:
        raise ValueError("Plain HTTP registry endpoints must set insecure=true")
    return endpoint


def _image_reference_from_payload(name: str, tag: str | None) -> str:
    image = _required_text(name, "Image name is required")
    last_segment = image.rsplit("/", 1)[-1]
    if ":" in last_segment:
        return image
    return f"{image}:{tag or 'latest'}"


def _split_image_tag(full_name: str) -> tuple[str, str]:
    last_segment = full_name.rsplit("/", 1)[-1]
    if ":" in last_segment:
        name, tag = full_name.rsplit(":", 1)
        return name, tag or "latest"
    return full_name, "latest"


def _split_image_registry(name: str) -> tuple[str, str, bool]:
    parts = name.split("/", 1)
    if len(parts) == 2 and _looks_like_registry(parts[0]):
        return normalize_registry(parts[0]), parts[1], True
    return "docker.io", name, False


def _looks_like_registry(first_segment: str) -> bool:
    return (
        "." in first_segment
        or ":" in first_segment
        or first_segment == "localhost"
    )


def _auth_config_from_material(
    material: ContainerRegistryAuthMaterial,
) -> dict[str, str] | None:
    auth_config: dict[str, str] = {}
    if material.username:
        auth_config["username"] = material.username
    if material.password:
        auth_config["password"] = material.password
    return auth_config or None
