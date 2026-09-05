from __future__ import annotations

import hashlib
import json
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
        return await self.repo.list_for_session(session_id)

    async def get(
        self,
        *,
        artifact_id: str,
        workspace_id: str,
        user_id: str,
    ) -> AgentHarnessArtifact:
        artifact = await self.repo.get_owned(
            artifact_id,
            workspace_id=workspace_id,
            user_id=user_id,
        )
        if artifact is None:
            raise NotFoundError(f"Agent artifact not found: {artifact_id}")
        return artifact

    def delete_session_files(self, session_id: str) -> None:
        shutil.rmtree(agent_session_artifacts_root(session_id), ignore_errors=True)

    async def download_path(
        self,
        *,
        artifact_id: str,
        workspace_id: str,
        user_id: str,
    ) -> tuple[Path, str, str]:
        artifact = await self.get(
            artifact_id=artifact_id,
            workspace_id=workspace_id,
            user_id=user_id,
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
            return await self._store_command_output(
                payload,
                session_id=session_id,
                run_id=run_id,
                fence=fence,
            )

        return write

    async def _store_command_output(
        self,
        payload: dict[str, Any],
        *,
        session_id: str,
        run_id: str,
        fence: RunFence,
    ) -> dict[str, Any]:
        command = str(payload.get("command") or "Shell command")
        artifact_id = str(uuid4())
        root = agent_artifact_root(session_id, artifact_id)
        staging_root = root.with_name(f".{artifact_id}.staging")
        staging_root.mkdir(parents=True, exist_ok=False)
        filename = "command-output.json"
        output_path = staging_root / filename
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        digest = hashlib.sha256(encoded).hexdigest()
        try:
            async with aiofiles.open(output_path, "xb") as output:
                await output.write(encoded)
            artifact = await self.repo.create_for_run(
                id=artifact_id,
                session_id=session_id,
                run_id=run_id,
                fence=fence,
                commit=False,
                type=str(payload.get("type") or "command_output"),
                title=command[:200],
                summary=(
                    "Full output preserved because the inline result was truncated."
                ),
                payload={
                    "command": command,
                    "cwd": payload.get("cwd"),
                    "stdout_bytes": len(
                        str(payload.get("stdout") or "").encode("utf-8")
                    ),
                    "stderr_bytes": len(
                        str(payload.get("stderr") or "").encode("utf-8")
                    ),
                },
                file_path=f"{session_id}/{artifact_id}/{filename}",
                resource_ref={
                    "kind": "stored_file",
                    "filename": filename,
                    "mime_type": "application/json",
                    "size_bytes": len(encoded),
                    "sha256": digest,
                },
            )
            staging_root.rename(root)
            await self.repo.session.commit()
        except Exception:
            await self.repo.session.rollback()
            shutil.rmtree(staging_root, ignore_errors=True)
            shutil.rmtree(root, ignore_errors=True)
            raise
        try:
            await self.repo.session.refresh(artifact)
        except Exception:
            # The database row and file are already durable; keep both for retry.
            raise
        return {"artifact_id": str(artifact.id)}

    async def _publish_declared_file(
        self,
        payload: dict[str, Any],
        *,
        session_id: str,
        run_id: str,
        fence: RunFence,
    ) -> dict[str, Any]:
        """Copy an explicitly declared workspace result into managed storage.

        A Run plus declaration id is the idempotency key. This makes recovery
        safe: retrying the same durable tool call returns the original Artifact,
        while a conflicting retry is rejected instead of silently replacing it.
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
        artifact_id = str(
            uuid5(
                NAMESPACE_URL,
                f"bioinfoflow:agent-artifact:{session_id}:{run_id}:{declaration_id}",
            )
        )
        digest = hashlib.sha256(content).hexdigest()
        resource_ref = {
            "kind": "stored_file",
            "filename": filename,
            "mime_type": mime_type,
            "size_bytes": len(content),
            "sha256": digest,
        }
        root = agent_artifact_root(session_id, artifact_id)
        staging_root = root.with_name(f".{artifact_id}.{uuid4()}.staging")
        staging_root.mkdir(parents=True, exist_ok=False)
        output_path = staging_root / filename
        moved_to_final_root = False
        try:
            async with aiofiles.open(output_path, "xb") as output:
                await output.write(content)
            try:
                artifact = await self.repo.create_for_run(
                    id=artifact_id,
                    session_id=session_id,
                    run_id=run_id,
                    fence=fence,
                    commit=False,
                    type="published_file",
                    title=title,
                    summary=summary,
                    payload={"declaration_id": declaration_id},
                    file_path=f"{session_id}/{artifact_id}/{filename}",
                    resource_ref=resource_ref,
                )
            except IntegrityError:
                await self.repo.session.rollback()
                existing = await self.repo.get(artifact_id)
                if existing is None:
                    raise
                _require_matching_artifact_declaration(
                    existing,
                    session_id=session_id,
                    run_id=run_id,
                    title=title,
                    summary=summary,
                    declaration_id=declaration_id,
                    resource_ref=resource_ref,
                )
                _require_stored_artifact_content(root / filename, digest)
                shutil.rmtree(staging_root, ignore_errors=True)
                return _artifact_reference(existing)
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
        "artifact_id": str(artifact.id),
        "title": artifact.title,
        "media_type": resource.get("mime_type"),
    }


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


def _require_matching_artifact_declaration(
    artifact: AgentHarnessArtifact,
    *,
    session_id: str,
    run_id: str,
    title: str,
    summary: str | None,
    declaration_id: str,
    resource_ref: dict[str, Any],
) -> None:
    if (
        str(artifact.session_id) != session_id
        or str(artifact.run_id) != run_id
        or artifact.type != "published_file"
        or artifact.title != title
        or artifact.summary != summary
        or artifact.payload != {"declaration_id": declaration_id}
        or artifact.resource_ref != resource_ref
    ):
        raise ConflictError(
            "Artifact declaration conflicts with an existing publication"
        )


def _require_stored_artifact_content(path: Path, digest: str) -> None:
    if not path.is_file():
        raise ConflictError("Artifact declaration has no managed file")
    if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise ConflictError("Artifact declaration conflicts with managed file content")


__all__ = ["AgentHarnessArtifactService", "artifact_reference_part"]
