from __future__ import annotations

import hashlib
import mimetypes
import shutil
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

import aiofiles
from sqlalchemy.exc import IntegrityError

from app.models.agent_harness import AgentHarnessArtifact, AgentHarnessSession
from app.path_layout import (
    agent_artifact_root,
    agent_artifacts_root,
    agent_session_artifacts_root,
    bioinfoflow_home,
    safe_join,
)
from app.repositories.agent_harness_repo import AgentHarnessArtifactRepository, RunFence
from app.utils.exceptions import BadRequestError, ConflictError, NotFoundError


class AgentHarnessArtifactService:
    """Own durable artifact queries, downloads, and publication storage."""

    def __init__(self, db) -> None:
        self.repo = AgentHarnessArtifactRepository(db)

    async def list_for_session(
        self,
        *,
        session_id: str,
        workspace_id: str,
        user_id: str,
    ) -> list[AgentHarnessArtifact]:
        session = await self.repo.session.get(AgentHarnessSession, session_id)
        if (
            session is None
            or session.status == "deleted"
            or str(session.workspace_id) != workspace_id
            or session.user_id != user_id
        ):
            raise NotFoundError(f"Agent session not found: {session_id}")
        return await self.repo.list_latest_for_session(session_id)

    async def get(
        self,
        *,
        artifact_id: str,
        workspace_id: str,
        user_id: str,
    ) -> AgentHarnessArtifact:
        artifact = await self.repo.get_latest_owned(
            artifact_id,
            workspace_id=workspace_id,
            user_id=user_id,
        )
        if artifact is None:
            raise NotFoundError(f"Agent artifact not found: {artifact_id}")
        return artifact

    async def list_versions(
        self,
        *,
        artifact_id: str,
        workspace_id: str,
        user_id: str,
    ) -> list[AgentHarnessArtifact]:
        latest = await self.get(
            artifact_id=artifact_id, workspace_id=workspace_id, user_id=user_id
        )
        return await self.repo.list_versions_owned(
            artifact_id,
            session_id=str(latest.session_id),
            workspace_id=workspace_id,
            user_id=user_id,
        )

    async def get_version(
        self,
        *,
        artifact_id: str,
        version_id: str,
        workspace_id: str,
        user_id: str,
    ) -> AgentHarnessArtifact:
        latest = await self.get(
            artifact_id=artifact_id, workspace_id=workspace_id, user_id=user_id
        )
        artifact = await self.repo.get_version_owned(
            artifact_id,
            version_id,
            session_id=str(latest.session_id),
            workspace_id=workspace_id,
            user_id=user_id,
        )
        if artifact is None:
            raise NotFoundError(f"Agent artifact version not found: {version_id}")
        return artifact

    def delete_session_files(self, session_id: str) -> None:
        shutil.rmtree(agent_session_artifacts_root(session_id), ignore_errors=True)

    async def download_path(
        self,
        *,
        artifact_id: str,
        workspace_id: str,
        user_id: str,
        version_id: str | None = None,
    ) -> tuple[Path, str, str]:
        artifact = (
            await self.get_version(
                artifact_id=artifact_id,
                version_id=version_id,
                workspace_id=workspace_id,
                user_id=user_id,
            )
            if version_id is not None
            else await self.get(
                artifact_id=artifact_id,
                workspace_id=workspace_id,
                user_id=user_id,
            )
        )
        raw_path = str(artifact.file_path or "").strip()
        if not raw_path:
            raise NotFoundError("Agent artifact has no downloadable file")
        stored = Path(raw_path)
        if stored.is_absolute():
            candidate = stored.expanduser().resolve()
            if not candidate.is_relative_to(bioinfoflow_home()):
                raise NotFoundError("Agent artifact file is outside managed storage")
        else:
            try:
                candidate = safe_join(
                    agent_artifacts_root(),
                    raw_path,
                    escape_message="Agent artifact path escapes managed storage",
                )
            except PermissionError as exc:
                raise NotFoundError("Agent artifact file is invalid") from exc
        if not candidate.is_file():
            raise NotFoundError("Agent artifact file was not found")
        resource = artifact.resource_ref or {}
        filename = str(resource.get("filename") or candidate.name)
        media_type = str(
            resource.get("mime_type")
            or mimetypes.guess_type(filename)[0]
            or "application/octet-stream"
        )
        return candidate, filename, media_type

    def writer(self, *, session_id: str, run_id: str, fence: RunFence):
        async def write(payload: dict[str, Any]) -> dict[str, Any]:
            if payload.get("type") == "published_file":
                return await self._publish_declared_file(
                    payload,
                    session_id=session_id,
                    run_id=run_id,
                    fence=fence,
                )
            raise ValueError("Artifact writer accepts only published_file payloads")

        return write

    async def _publish_declared_file(
        self,
        payload: dict[str, Any],
        *,
        session_id: str,
        run_id: str,
        fence: RunFence,
        version_conflict_retries: int = 1,
    ) -> dict[str, Any]:
        """Copy an explicitly declared workspace result into managed storage.

        The logical identity is session-scoped and derived from the declaration
        unless the Agent explicitly continues an existing Artifact. A run plus
        declaration is the idempotency key for a version, so retries return the
        original immutable row instead of replacing its content.
        """

        declaration_id = _required_artifact_text(
            payload.get("declaration_id"), "artifact declaration id"
        )
        filename = _artifact_filename(payload.get("filename"))
        title = _required_artifact_text(payload.get("title"), "artifact title")
        summary = _optional_artifact_text(payload.get("summary"), "artifact summary")
        mime_type = _required_artifact_text(
            payload.get("mime_type"), "artifact mime type"
        )
        content = payload.get("content")
        if not isinstance(content, bytes):
            raise BadRequestError("Artifact declaration content must be bytes")
        requested_artifact_id = _optional_artifact_id(payload.get("artifact_id"))
        artifact_id = requested_artifact_id or str(
            uuid5(
                NAMESPACE_URL,
                f"bioinfoflow:agent-artifact:{session_id}:{declaration_id}",
            )
        )
        existing_identity = await self.repo.get_for_session_identity(
            artifact_id, session_id=session_id
        )
        if requested_artifact_id is not None and existing_identity is None:
            raise NotFoundError(f"Agent artifact not found: {artifact_id}")
        digest = hashlib.sha256(content).hexdigest()
        resource_ref = {
            "kind": "stored_file",
            "filename": filename,
            "mime_type": mime_type,
            "size_bytes": len(content),
            "sha256": digest,
        }
        same_declaration_in_run = (
            existing_identity is not None
            and str(existing_identity.run_id) == run_id
            and (
                existing_identity.declaration_id
                or (existing_identity.payload or {}).get("declaration_id")
            )
            == declaration_id
        )
        if (
            same_declaration_in_run
            and (
                existing_identity.resource_ref != resource_ref
                or existing_identity.title != title
                or existing_identity.summary != summary
            )
        ):
            raise ConflictError(
                "Artifact declaration conflicts with an existing publication"
            )
        if (
            existing_identity is not None
            and existing_identity.resource_ref == resource_ref
            and existing_identity.title == title
            and existing_identity.summary == summary
        ):
            # Re-publishing unchanged bytes does not create a meaningless
            # version. The existing row remains the durable source of truth.
            return _artifact_reference(existing_identity)
        version = (
            (existing_identity.version or 1) + 1
            if existing_identity is not None
            else 1
        )
        version_id = artifact_id if existing_identity is None else str(
            uuid5(
                NAMESPACE_URL,
                f"bioinfoflow:agent-artifact-version:{artifact_id}:{version}",
            )
        )
        root = agent_artifact_root(session_id, version_id)
        staging_root = root.with_name(f".{version_id}.{uuid4()}.staging")
        staging_root.mkdir(parents=True, exist_ok=False)
        output_path = staging_root / filename
        moved_to_final_root = False
        try:
            async with aiofiles.open(output_path, "xb") as output:
                await output.write(content)
            try:
                artifact = await self.repo.create_for_run(
                    id=version_id,
                    session_id=session_id,
                    run_id=run_id,
                    fence=fence,
                    commit=False,
                    artifact_id=artifact_id,
                    version=version,
                    declaration_id=declaration_id,
                    type="published_file",
                    title=title,
                    summary=summary,
                    payload={"declaration_id": declaration_id},
                    file_path=f"{session_id}/{version_id}/{filename}",
                    resource_ref=resource_ref,
                )
            except IntegrityError:
                await self.repo.session.rollback()
                shutil.rmtree(staging_root, ignore_errors=True)
                if version_conflict_retries:
                    return await self._publish_declared_file(
                        payload,
                        session_id=session_id,
                        run_id=run_id,
                        fence=fence,
                        version_conflict_retries=version_conflict_retries - 1,
                    )
                raise ConflictError("Artifact version conflicts with another publication")
            if root.exists():
                raise ConflictError(
                    "Artifact storage already exists for this declaration"
                )
            staging_root.rename(root)
            moved_to_final_root = True
            await self.repo.session.commit()
        except Exception:
            await self.repo.session.rollback()
            shutil.rmtree(staging_root, ignore_errors=True)
            if moved_to_final_root:
                shutil.rmtree(root, ignore_errors=True)
            raise
        try:
            await self.repo.session.refresh(artifact)
        except Exception:
            # The database row and file are already durable; keep both for retry.
            raise
        return _artifact_reference(artifact)


def artifact_reference_part(output: Any) -> dict[str, Any] | None:
    """Return the public transcript reference only for canonical publications."""

    if not isinstance(output, dict):
        return None
    candidate = output.get("artifact")
    if not isinstance(candidate, dict):
        return None
    raw_id = candidate.get("artifact_id")
    try:
        artifact_id = str(UUID(str(raw_id)))
    except (TypeError, ValueError, AttributeError):
        return None
    title = candidate.get("title")
    media_type = candidate.get("media_type")
    if not isinstance(title, str) or not title.strip():
        return None
    if not isinstance(media_type, str) or not media_type.strip():
        return None
    return {
        "id": f"artifact:{artifact_id}",
        "type": "artifact_ref",
        "artifact_id": artifact_id,
        "title": title,
        "media_type": media_type,
    }


def _artifact_reference(artifact: AgentHarnessArtifact) -> dict[str, Any]:
    resource = artifact.resource_ref or {}
    return {
        "artifact_id": str(artifact.artifact_id or artifact.id),
        "version_id": str(artifact.id),
        "version": artifact.version or 1,
        "title": artifact.title,
        "media_type": resource.get("mime_type"),
    }


def _optional_artifact_id(value: Any) -> str | None:
    if value is None:
        return None
    try:
        return str(UUID(str(value)))
    except (TypeError, ValueError, AttributeError) as exc:
        raise BadRequestError("Artifact id must be a UUID") from exc


def _required_artifact_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BadRequestError(f"{field.capitalize()} must be non-empty text")
    return value.strip()


def _optional_artifact_text(value: Any, field: str) -> str | None:
    if value is None:
        return None
    return _required_artifact_text(value, field)


def _artifact_filename(value: Any) -> str:
    filename = _required_artifact_text(value, "artifact filename")
    if filename != Path(filename).name or filename in {".", ".."}:
        raise BadRequestError("Artifact filename must not include a path")
    return filename


def _require_stored_artifact_content(path: Path, digest: str) -> None:
    if not path.is_file():
        raise ConflictError("Artifact declaration has no managed file")
    if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise ConflictError("Artifact declaration conflicts with managed file content")


__all__ = ["AgentHarnessArtifactService", "artifact_reference_part"]
