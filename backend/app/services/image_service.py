from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_maker
from app.models.image import ImageStatus
from app.repositories.project_repo import ProjectRepository
from app.repositories.image_repo import ImageRepository
from app.runtime.background_tasks import background_tasks
from app.runtime.events import publish_image_progress
from app.services.container_registry_service import ContainerRegistryService
from app.services.docker_service import (
    DockerImageInfo,
    DockerService,
    normalize_registry,
    qualified_image_reference,
)
from app.utils.authorization import can_access_project
from app.utils.exceptions import ConfigurationError, PermissionDeniedError
from app.utils.logging import get_logger


logger = get_logger(__name__)


class DockerUnavailableError(RuntimeError):
    pass


class ImageDeleteConflictError(RuntimeError):
    def __init__(self, code: str, message: str, *, details: dict | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.details = details


class ImageService:
    _sync_lock: asyncio.Lock | None = None
    _last_sync_at: datetime | None = None
    _sync_ttl_seconds = 30

    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = ImageRepository(session)
        self.project_repo = ProjectRepository(session)
        self.docker = DockerService()

    async def list_images(
        self,
        *,
        limit: int = 20,
        cursor: str | None = None,
        search: str | None = None,
        status: str | None = None,
        force_sync: bool = False,
    ):
        docker_status = "available"
        if status in (None, ImageStatus.LOCAL.value):
            try:
                await self._sync_local_images(force=force_sync)
            except DockerUnavailableError:
                docker_status = "unavailable"
        images, pagination = await self.repo.list(
            limit=limit,
            cursor=cursor,
            search=search,
            status=status,
        )
        last_synced_at = self.__class__._last_sync_at
        return (
            images,
            pagination,
            {
                "docker": docker_status,
                "images_stale": docker_status == "unavailable"
                and last_synced_at is not None,
                "last_synced_at": last_synced_at,
            },
        )

    async def list_catalog_images(
        self,
        *,
        limit: int = 20,
        cursor: str | None = None,
        search: str | None = None,
        status: str | None = None,
    ):
        images, pagination = await self.repo.list(
            limit=limit,
            cursor=cursor,
            search=search,
            status=status,
        )
        return (
            images,
            pagination,
            {
                "docker": "not_synced",
                "images_stale": False,
                "last_synced_at": self.__class__._last_sync_at,
            },
        )

    async def get_image(self, image_id: str):
        return await self.repo.get(image_id)

    async def pull_image(
        self,
        *,
        name: str,
        tag: str = "latest",
        registry: str = "docker.io",
        project_id: str | None = None,
        user_id: str | None = None,
        workspace_id: str | None = None,
        auth_config: dict[str, Any] | None = None,
        registry_id: str | None = None,
    ):
        if not await self.docker.is_available():
            raise DockerUnavailableError("docker unavailable")
        await self._validate_project_context(
            project_id=project_id,
            workspace_id=workspace_id,
            user_id=user_id,
        )
        if registry_id:
            registry_service = ContainerRegistryService(self.session)
            material = await registry_service.resolve_auth_material(registry_id)
            target = await registry_service.resolve_image_target(
                registry_id=registry_id,
                name=name,
                tag=tag,
            )
            if target.registry_id is not None and material.endpoint.startswith("http://"):
                configuration_error = await self.docker.registry_configuration_error(
                    material.endpoint
                )
                if configuration_error:
                    raise ConfigurationError(configuration_error)
            name = target.name
            tag = target.tag
            registry = target.registry
            auth_config = target.auth_config
            registry_id = target.registry_id
        registry = normalize_registry(registry) or "docker.io"
        full_name = qualified_image_reference(name, tag, registry)
        existing = await self.repo.get_by_full_name(full_name)
        if existing:
            image = await self.repo.update(
                existing,
                status=ImageStatus.PULLING.value,
                registry=registry,
                pull_progress=0,
                error_message="",
            )
        else:
            image = await self.repo.create(
                name=name,
                tag=tag,
                full_name=full_name,
                registry=registry,
                status=ImageStatus.PULLING.value,
                pull_progress=0,
            )

        task_kwargs: dict[str, Any] = {}
        if auth_config is not None:
            task_kwargs["auth_config"] = auth_config
        if registry_id is not None:
            task_kwargs["registry_id"] = registry_id
        background_tasks.submit(
            self._pull_task, image.id, name, tag, registry, project_id, **task_kwargs
        )
        return image

    async def delete_image(self, image, *, force: bool = False) -> bool:
        if image.status == ImageStatus.PULLING.value:
            raise ImageDeleteConflictError(
                "IMAGE_PULLING",
                "Image pull is still in progress",
            )
        if image.status == ImageStatus.FAILED.value:
            await self.repo.delete(image)
            return True

        usage = await self.docker.get_image_usage(image.full_name)
        if usage:
            raise ImageDeleteConflictError(
                "IMAGE_IN_USE",
                "Image is in use by one or more containers",
                details={"containers": usage},
            )

        full_name = image.full_name
        deleted = await self.docker.delete_image(full_name, force=force)
        if deleted:
            await self.repo.delete(image)
            return True

        # If Docker reports missing but the image is already gone, remove stale record.
        try:
            info = await self.docker.inspect_image(full_name)
        except Exception:  # noqa: BLE001
            return False
        if info is None:
            await self.repo.delete(image)
            return True
        return False

    async def load_image_tarball(
        self,
        *,
        content: bytes,
        project_id: str | None = None,
        user_id: str | None = None,
        workspace_id: str | None = None,
    ):
        await self._validate_project_context(
            project_id=project_id,
            workspace_id=workspace_id,
            user_id=user_id,
        )
        tags = await self.docker.load_image(content)
        images = []
        for tag in tags:
            info = await self.docker.inspect_image(tag)
            if info:
                await self._upsert_local_image(info)
                image = await self.repo.get_by_full_name(info.full_name)
                if image:
                    images.append(image)

        if project_id:
            for image in images:
                await publish_image_progress(
                    project_id=project_id,
                    image_id=str(image.id),
                    progress=100,
                    status=ImageStatus.LOCAL.value,
                )
        self._touch_sync()
        return images

    def _sync_expired(self) -> bool:
        last = self.__class__._last_sync_at
        if not last:
            return True
        age = datetime.now(timezone.utc) - last
        return age.total_seconds() >= self.__class__._sync_ttl_seconds

    def _touch_sync(self) -> None:
        self.__class__._last_sync_at = datetime.now(timezone.utc)

    async def _sync_local_images(
        self,
        *,
        force: bool = False,
    ) -> None:
        if not force and not self._sync_expired():
            return
        if self.__class__._sync_lock is None:
            self.__class__._sync_lock = asyncio.Lock()
        async with self.__class__._sync_lock:
            if not force and not self._sync_expired():
                return
            try:
                images = await self.docker.list_images()
            except Exception as exc:  # noqa: BLE001
                raise DockerUnavailableError("docker unavailable") from exc
            local_full_names = {info.full_name for info in images}
            for info in images:
                await self._upsert_local_image(info)
            await self._mark_missing_local_images(local_full_names)
            await self._prune_remote_images(local_full_names)
            self._touch_sync()

    async def _mark_missing_local_images(self, local_full_names: set[str]) -> None:
        stale_cutoff = datetime.now(timezone.utc) - timedelta(minutes=30)
        candidates = await self.repo.list_by_statuses(
            [ImageStatus.LOCAL.value, ImageStatus.PULLING.value]
        )
        for image in candidates:
            if image.full_name in local_full_names:
                continue
            if image.status == ImageStatus.PULLING.value and getattr(
                image, "updated_at", None
            ):
                updated_at = image.updated_at
                if updated_at.tzinfo is None:
                    if updated_at > stale_cutoff.replace(tzinfo=None):
                        continue
                else:
                    if updated_at > stale_cutoff:
                        continue
            await self.repo.delete(image)

    async def _prune_remote_images(self, local_full_names: set[str]) -> None:
        remotes = await self.repo.list_not_in_full_names(
            local_full_names,
            statuses=[ImageStatus.REMOTE.value],
        )
        for image in remotes:
            await self.repo.delete(image)

    async def _upsert_local_image(self, info: DockerImageInfo):
        existing = await self.repo.get_by_full_name(info.full_name)
        payload = {
            "name": info.name,
            "tag": info.tag,
            "full_name": info.full_name,
            "registry": info.registry,
            "status": ImageStatus.LOCAL.value,
            "size_bytes": info.size_bytes,
            "labels": info.labels,
            "env": info.env,
            "entrypoint": info.entrypoint,
        }
        if existing:
            await self.repo.update(existing, **payload)
            return
        await self.repo.create(**payload)

    async def _pull_task(
        self,
        image_id: str,
        name: str,
        tag: str,
        registry: str,
        project_id: str | None,
        *,
        auth_config: dict[str, Any] | None = None,
        registry_id: str | None = None,
    ) -> None:
        async with async_session_maker() as session:
            repo = ImageRepository(session)
            await self._pull_task_with_repo(
                repo,
                image_id,
                name,
                tag,
                registry,
                project_id,
                auth_config=auth_config,
                registry_id=registry_id,
            )

    async def _pull_task_with_repo(
        self,
        repo: ImageRepository,
        image_id: str,
        name: str,
        tag: str,
        registry: str,
        project_id: str | None,
        *,
        auth_config: dict[str, Any] | None = None,
        registry_id: str | None = None,
    ) -> None:
        del registry_id
        progress = 0
        try:
            pull_kwargs: dict[str, Any] = {}
            if auth_config is not None:
                pull_kwargs["auth_config"] = auth_config
            async for event in self.docker.pull_image(
                name,
                tag,
                registry,
                **pull_kwargs,
            ):
                progress_detail = event.get("progressDetail") or {}
                total = progress_detail.get("total")
                current = progress_detail.get("current")
                if total and current is not None:
                    next_progress = int((current / total) * 100)
                else:
                    next_progress = progress
                if next_progress != progress:
                    progress = next_progress
                    await self._update_progress(repo, image_id, progress, project_id)
        except Exception as exc:  # noqa: BLE001
            logger.exception(
                "image.pull.failed",
                image_id=str(image_id),
                image=qualified_image_reference(name, tag, registry),
                registry=registry,
                error=str(exc),
            )
            await self._mark_pull_failed(repo, image_id, str(exc), project_id)
            return

        await self._finalize_pull(repo, image_id, name, tag, registry, project_id)

    async def _update_progress(
        self,
        repo: ImageRepository,
        image_id: str,
        progress: int,
        project_id: str | None,
    ) -> None:
        image = await repo.get(image_id)
        if not image:
            return
        await repo.update(
            image, pull_progress=progress, status=ImageStatus.PULLING.value
        )
        if project_id:
            await publish_image_progress(
                project_id=project_id,
                image_id=str(image_id),
                progress=progress,
                status=ImageStatus.PULLING.value,
            )

    async def _finalize_pull(
        self,
        repo: ImageRepository,
        image_id: str,
        name: str,
        tag: str,
        registry: str,
        project_id: str | None,
    ) -> None:
        image = await repo.get(image_id)
        if not image:
            return
        full_name = qualified_image_reference(name, tag, registry)
        info = await self.docker.inspect_image(full_name)
        payload = {"status": ImageStatus.LOCAL.value, "pull_progress": 100}
        if info:
            payload.update(
                {
                    "size_bytes": info.size_bytes,
                    "labels": info.labels,
                    "env": info.env,
                    "entrypoint": info.entrypoint,
                    "registry": registry or info.registry,
                }
            )
        await self._persist_image(
            repo,
            image,
            error_message=None,
            **payload,
        )
        self._touch_sync()
        if project_id:
            await publish_image_progress(
                project_id=project_id,
                image_id=str(image_id),
                progress=100,
                status=ImageStatus.LOCAL.value,
            )

    async def _mark_pull_failed(
        self,
        repo: ImageRepository,
        image_id: str,
        error_message: str,
        project_id: str | None,
    ) -> None:
        image = await repo.get(image_id)
        if not image:
            return
        await self._persist_image(
            repo,
            image,
            status=ImageStatus.FAILED.value,
            error_message=error_message,
        )
        if project_id:
            await publish_image_progress(
                project_id=project_id,
                image_id=str(image_id),
                progress=image.pull_progress,
                status=ImageStatus.FAILED.value,
            )

    async def _persist_image(self, repo: ImageRepository, image, **data):
        return await repo.update_all(image, **data)

    async def _validate_project_context(
        self,
        *,
        project_id: str | None,
        workspace_id: str | None,
        user_id: str | None,
    ) -> None:
        if not project_id or (user_id is None and workspace_id is None):
            return
        project = await self.project_repo.get(project_id)
        if project is None or not can_access_project(
            project,
            user_id=user_id,
            workspace_id=workspace_id,
        ):
            raise PermissionDeniedError("project does not belong to workspace")
