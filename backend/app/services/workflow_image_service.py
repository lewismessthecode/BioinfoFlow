from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.container_registry_service import (
    ContainerRegistryAuthMaterial,
    ContainerRegistryService,
)
from app.services.docker_service import normalize_registry, qualified_image_reference
from app.services.image_service import DockerUnavailableError, ImageService


@dataclass(frozen=True)
class WorkflowImageRegistry:
    endpoint: str
    namespace: str | None = None
    registry_id: str | None = None
    auth_config: dict[str, Any] | None = None

    @property
    def normalized_endpoint(self) -> str:
        return normalize_registry(self.endpoint)

    @property
    def normalized_namespace(self) -> str | None:
        namespace = str(self.namespace or "").strip().strip("/")
        return namespace or None


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


@dataclass(frozen=True)
class WorkflowImagePrefetchFailure:
    requirement: WorkflowImageRequirement
    error: str


@dataclass(frozen=True)
class WorkflowImagePrefetchResult:
    enqueued: list[WorkflowImageRequirement] = field(default_factory=list)
    failed: list[WorkflowImagePrefetchFailure] = field(default_factory=list)


class WorkflowImagePrefetchService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        default_registry: WorkflowImageRegistry | None = None,
    ) -> None:
        self.session = session
        self.default_registry = default_registry

    async def prefetch_workflow(self, workflow) -> WorkflowImagePrefetchResult:
        selected_registry = None
        registry_id = getattr(workflow, "container_registry_id", None)
        if registry_id:
            selected_registry = await self._load_registry(registry_id=str(registry_id))
        return await self.prefetch_schema(
            getattr(workflow, "schema_json", None),
            workflow_id=str(getattr(workflow, "id", "")),
            registry=selected_registry,
        )

    async def prefetch_schema(
        self,
        schema_json: dict | None,
        *,
        workflow_id: str | None = None,
        project_id: str | None = None,
        registry: WorkflowImageRegistry | None = None,
    ) -> WorkflowImagePrefetchResult:
        del workflow_id
        selected_registry = registry or self.default_registry
        if selected_registry is None:
            selected_registry = await self._load_default_registry(project_id=project_id)

        requirements = resolve_workflow_image_requirements(
            schema_json,
            default_registry=selected_registry,
        )
        image_service = ImageService(self.session)
        enqueued: list[WorkflowImageRequirement] = []
        failed: list[WorkflowImagePrefetchFailure] = []
        for requirement in requirements:
            try:
                await image_service.pull_image(
                    name=requirement.name,
                    tag=requirement.tag,
                    registry=requirement.registry,
                    project_id=None,
                    user_id=None,
                    workspace_id=None,
                    auth_config=requirement.auth_config,
                    registry_id=requirement.registry_id,
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

    async def _load_default_registry(
        self,
        *,
        project_id: str | None,
    ) -> WorkflowImageRegistry | None:
        registry_service = ContainerRegistryService(self.session)
        registry = await registry_service.get_effective_registry(project_id=project_id)
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
    default_registry: WorkflowImageRegistry | None = None,
) -> list[WorkflowImageRequirement]:
    return [
        resolve_container_image_reference(image, default_registry=default_registry)
        for image in workflow_container_images(schema_json)
    ]


def resolve_container_image_reference(
    reference: str,
    *,
    default_registry: WorkflowImageRegistry | None,
) -> WorkflowImageRequirement:
    image = reference.strip()
    name_part, tag = _split_tag(image)
    registry, name, explicit_registry = _split_registry(name_part)
    rewrite_applied = False
    auth_config: dict[str, Any] | None = None
    registry_id: str | None = None

    if not explicit_registry and default_registry is not None:
        default_endpoint = default_registry.normalized_endpoint
        if default_endpoint:
            namespace = default_registry.normalized_namespace
            if namespace:
                name = f"{namespace}/{name}"
            registry = default_endpoint
            rewrite_applied = True
            auth_config = default_registry.auth_config
            registry_id = default_registry.registry_id

    full_name = qualified_image_reference(name, tag, registry)
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


def _split_registry(name: str) -> tuple[str, str, bool]:
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


def _is_dynamic_container_expression(image: str) -> bool:
    return "${" in image or "~{" in image or any(char.isspace() for char in image)


def _registry_from_auth_material(
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
