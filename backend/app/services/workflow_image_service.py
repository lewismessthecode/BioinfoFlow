from __future__ import annotations

from dataclasses import dataclass, field, replace
import re
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.container_registry_service import (
    ContainerRegistryAuthMaterial,
    ContainerRegistryService,
)
from app.services.docker_service import normalize_registry, registry_authority
from app.services.image_service import DockerUnavailableError, ImageService


@dataclass(frozen=True)
class WorkflowImageRegistry:
    endpoint: str
    namespace: str | None = None
    registry_id: str | None = None
    auth_config: dict[str, Any] | None = None

    @property
    def normalized_endpoint(self) -> str:
        return registry_authority(self.endpoint)

    @property
    def normalized_namespace(self) -> str | None:
        namespace = str(self.namespace or "").strip().strip("/")
        return namespace or None

    def matches_registry(self, registry: str) -> bool:
        return normalize_registry(self.endpoint) == normalize_registry(registry)

    @property
    def image_prefix(self) -> str:
        endpoint = self.normalized_endpoint
        namespace = self.normalized_namespace
        if namespace:
            return f"{endpoint}/{namespace}"
        return endpoint


@dataclass(frozen=True)
class WorkflowImageRequirement:
    source_reference: str
    name: str
    tag: str
    registry: str
    full_name: str
    explicit_registry: bool
    rewrite_applied: bool
    registry_id: str | None = None
    auth_config: dict[str, Any] | None = None

    def runtime_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "full_name": self.full_name,
            "name": self.name,
            "tag": self.tag,
            "registry": self.registry,
        }
        if self.registry_id:
            payload["registry_id"] = self.registry_id
        return payload


@dataclass(frozen=True)
class WorkflowImagePrefetchFailure:
    requirement: WorkflowImageRequirement
    error: str


@dataclass(frozen=True)
class WorkflowImagePrefetchResult:
    enqueued: list[WorkflowImageRequirement] = field(default_factory=list)
    failed: list[WorkflowImagePrefetchFailure] = field(default_factory=list)


class WorkflowImagePrefetchService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def prefetch_workflow(self, workflow) -> WorkflowImagePrefetchResult:
        selected_registry = None
        registry_id = getattr(workflow, "container_registry_id", None)
        if registry_id:
            selected_registry = await self._load_registry(registry_id=str(registry_id))
        return await self.prefetch_schema(
            getattr(workflow, "schema_json", None),
            workflow_id=str(getattr(workflow, "id", "")),
            selected_registry=selected_registry,
        )

    async def prefetch_schema(
        self,
        schema_json: dict | None,
        *,
        workflow_id: str | None = None,
        project_id: str | None = None,
        selected_registry: WorkflowImageRegistry | None = None,
    ) -> WorkflowImagePrefetchResult:
        del workflow_id
        if selected_registry is None and project_id is not None:
            selected_registry = await self._load_project_registry(project_id=project_id)

        requirements = await resolve_workflow_image_requirements_with_credentials(
            self.session,
            schema_json,
            selected_registry=selected_registry,
        )
        image_service = ImageService(self.session)
        enqueued: list[WorkflowImageRequirement] = []
        failed: list[WorkflowImagePrefetchFailure] = []
        for requirement in requirements:
            pull_name = requirement.name
            pull_tag: str | None = requirement.tag
            registry_id = None
            if requirement.registry_id is not None:
                pull_name = requirement.full_name
                pull_tag = None
                registry_id = requirement.registry_id
            try:
                await image_service.pull_image(
                    name=pull_name,
                    tag=pull_tag,
                    registry=requirement.registry,
                    project_id=None,
                    user_id=None,
                    workspace_id=None,
                    auth_config=requirement.auth_config,
                    registry_id=registry_id,
                )
            except DockerUnavailableError as exc:
                failed.append(
                    WorkflowImagePrefetchFailure(
                        requirement=requirement,
                        error=str(exc),
                    )
                )
                continue
            enqueued.append(requirement)
        return WorkflowImagePrefetchResult(enqueued=enqueued, failed=failed)

    async def _load_project_registry(
        self,
        *,
        project_id: str | None,
    ) -> WorkflowImageRegistry | None:
        registry_service = ContainerRegistryService(self.session)
        registry = await registry_service.get_project_registry(project_id=project_id)
        if registry is None:
            return None
        material = await registry_service.resolve_auth_material(str(registry.id))
        return _registry_from_auth_material(material)

    async def _load_registry(self, *, registry_id: str) -> WorkflowImageRegistry:
        registry_service = ContainerRegistryService(self.session)
        registry = await registry_service.get_registry(registry_id)
        material = await registry_service.resolve_auth_material(str(registry.id))
        return _registry_from_auth_material(material)


def workflow_container_images(schema_json: dict | None) -> list[str]:
    images: list[str] = []
    seen: set[str] = set()
    for task in list((schema_json or {}).get("tasks") or []):
        container = task.get("container") if isinstance(task, dict) else None
        if not isinstance(container, str):
            continue
        image = container.strip().strip("\"'")
        if not image or image in seen:
            continue
        if _is_dynamic_container_expression(image):
            continue
        seen.add(image)
        images.append(image)
    return images


def resolve_workflow_image_requirements(
    schema_json: dict | None,
    *,
    selected_registry: WorkflowImageRegistry | None = None,
) -> list[WorkflowImageRequirement]:
    return [
        resolve_container_image_reference(image, selected_registry=selected_registry)
        for image in workflow_container_images(schema_json)
    ]


async def resolve_workflow_image_requirements_with_credentials(
    session: AsyncSession,
    schema_json: dict | None,
    *,
    selected_registry: WorkflowImageRegistry | None,
) -> list[WorkflowImageRequirement]:
    requirements = resolve_workflow_image_requirements(
        schema_json,
        selected_registry=selected_registry,
    )
    unresolved_hosts = {
        normalize_registry(requirement.registry)
        for requirement in requirements
        if requirement.explicit_registry and requirement.registry_id is None
    }
    if not unresolved_hosts:
        return requirements

    registry_service = ContainerRegistryService(session)
    registries_by_host: dict[str, Any] = {}
    for registry in await registry_service.list_registries():
        normalized_host = normalize_registry(registry.endpoint)
        if normalized_host not in unresolved_hosts:
            continue
        current = registries_by_host.get(normalized_host)
        if current is None or str(registry.id) < str(current.id):
            registries_by_host[normalized_host] = registry
    resolved: list[WorkflowImageRequirement] = []
    materials: dict[str, WorkflowImageRegistry] = {}
    for requirement in requirements:
        registry = registries_by_host.get(normalize_registry(requirement.registry))
        if registry is None or requirement.registry_id is not None:
            resolved.append(requirement)
            continue
        registry_id = str(registry.id)
        material_registry = materials.get(registry_id)
        if material_registry is None:
            material_registry = workflow_registry_from_auth_material(
                await registry_service.resolve_auth_material(registry_id)
            )
            materials[registry_id] = material_registry
        resolved.append(
            replace(
                requirement,
                registry_id=material_registry.registry_id,
                auth_config=material_registry.auth_config,
            )
        )
    return resolved


def resolved_workflow_container_images(
    schema_json: dict | None,
    *,
    selected_registry: WorkflowImageRegistry | None = None,
) -> list[str]:
    return [
        requirement.full_name
        for requirement in resolve_workflow_image_requirements(
            schema_json,
            selected_registry=selected_registry,
        )
    ]


def runtime_workflow_container_images(
    schema_json: dict | None,
    *,
    selected_registry: WorkflowImageRegistry | None = None,
) -> list[dict[str, Any]]:
    return [
        requirement.runtime_dict()
        for requirement in resolve_workflow_image_requirements(
            schema_json,
            selected_registry=selected_registry,
        )
    ]


def resolve_container_image_reference(
    reference: str,
    *,
    selected_registry: WorkflowImageRegistry | None,
) -> WorkflowImageRequirement:
    image = reference.strip()
    digest = ""
    name_and_tag = image
    if "@" in image:
        name_and_tag, digest_value = image.split("@", 1)
        digest = f"@{digest_value}"
    name_part, tag = _split_tag(name_and_tag)
    registry, name, explicit_registry = _split_registry(name_part)
    rewrite_applied = False
    auth_config: dict[str, Any] | None = None
    registry_id: str | None = None

    if not explicit_registry and selected_registry is not None:
        selected_endpoint = selected_registry.normalized_endpoint
        if selected_endpoint:
            namespace = selected_registry.normalized_namespace
            if namespace:
                name = f"{namespace}/{name}"
            registry = selected_endpoint
            rewrite_applied = True
            auth_config = selected_registry.auth_config
            registry_id = selected_registry.registry_id
    elif explicit_registry and selected_registry is not None:
        if selected_registry.matches_registry(registry):
            auth_config = selected_registry.auth_config
            registry_id = selected_registry.registry_id

    if rewrite_applied:
        full_name = f"{registry}/{name}"
        if _reference_has_tag(name_and_tag):
            full_name = f"{full_name}:{tag}"
        full_name = f"{full_name}{digest}"
    else:
        full_name = image
    if digest:
        name = full_name
        tag = ""
    return WorkflowImageRequirement(
        source_reference=image,
        name=name,
        tag=tag,
        registry=registry,
        full_name=full_name,
        explicit_registry=explicit_registry,
        rewrite_applied=rewrite_applied,
        registry_id=registry_id,
        auth_config=auth_config,
    )


def _split_tag(full_name: str) -> tuple[str, str]:
    last_segment = full_name.rsplit("/", 1)[-1]
    if ":" in last_segment:
        name, tag = full_name.rsplit(":", 1)
        return name, tag
    return full_name, "latest"


def _reference_has_tag(full_name: str) -> bool:
    return ":" in full_name.rsplit("/", 1)[-1]


def _split_registry(name: str) -> tuple[str, str, bool]:
    parts = name.split("/", 1)
    if len(parts) == 2 and _looks_like_registry(parts[0]):
        return registry_authority(parts[0]), parts[1], True
    return "docker.io", name, False


def _looks_like_registry(first_segment: str) -> bool:
    return (
        "." in first_segment
        or ":" in first_segment
        or first_segment == "localhost"
    )


def _is_dynamic_container_expression(image: str) -> bool:
    return "${" in image or "~{" in image or any(char.isspace() for char in image)


def workflow_registry_from_auth_material(
    material: ContainerRegistryAuthMaterial,
) -> WorkflowImageRegistry:
    auth_config: dict[str, Any] = {}
    if material.username:
        auth_config["username"] = material.username
    if material.password:
        auth_config["password"] = material.password
    return WorkflowImageRegistry(
        endpoint=material.endpoint,
        namespace=material.namespace,
        registry_id=material.registry_id,
        auth_config=auth_config or None,
    )


_WDL_CONTAINER_LITERAL_RE = re.compile(
    r"(?P<prefix>\b(?:docker|container)\s*:\s*)"
    r"(?P<quote>[\"'])"
    r"(?P<image>[^\"']+)"
    r"(?P=quote)"
)


def rewrite_wdl_static_container_literals(
    content: str,
    *,
    selected_registry: WorkflowImageRegistry | None,
) -> str:
    if selected_registry is None:
        return content

    def replace(match: re.Match[str]) -> str:
        image = match.group("image").strip()
        if _is_dynamic_container_expression(image):
            return match.group(0)
        requirement = resolve_container_image_reference(
            image,
            selected_registry=selected_registry,
        )
        if requirement.full_name == image:
            return match.group(0)
        return f"{match.group('prefix')}{match.group('quote')}{requirement.full_name}{match.group('quote')}"

    return _WDL_CONTAINER_LITERAL_RE.sub(replace, content)


_registry_from_auth_material = workflow_registry_from_auth_material
