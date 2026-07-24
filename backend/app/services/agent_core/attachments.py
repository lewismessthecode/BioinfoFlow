from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
import shutil
from typing import Any
from uuid import uuid4

import aiofiles
from fastapi import UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError
from pypdf import PdfReader

from app.config import settings
from app.models.agent_core import (
    AgentAttachment,
    AgentAttachmentStatus,
    AgentSession,
)
from app.path_layout import (
    agent_attachment_root,
    agent_attachments_root,
    agent_session_attachments_root,
    safe_join,
)
from app.repositories.agent_core_repo import AgentAttachmentRepository
from app.utils.exceptions import BadRequestError, NotFoundError


_IMAGE_SIGNATURES = (
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"\xff\xd8\xff", "image/jpeg"),
)
_IGNORED_DIRECTORY_NAMES = {
    ".git",
    ".hg",
    ".svn",
    ".next",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "target",
    ".venv",
    "venv",
}
_IGNORED_FILENAMES = {
    ".env",
    ".env.local",
    ".npmrc",
    ".pypirc",
    "credentials",
    "credentials.json",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    "id_rsa",
}
_IGNORED_SUFFIXES = {".key", ".pem", ".p12", ".pfx", ".pyc"}


class AgentAttachmentService:
    def __init__(self, db) -> None:
        self.db = db
        self.repo = AgentAttachmentRepository(db)

    async def cleanup_orphans(self, *, cutoff: datetime | None = None) -> int:
        effective_cutoff = cutoff or (
            datetime.now(timezone.utc)
            - timedelta(seconds=settings.agent_attachment_orphan_ttl_seconds)
        )
        storage_paths = await self.repo.delete_orphans_before(effective_cutoff)
        attachments_root = agent_attachments_root()
        for storage_path in storage_paths:
            try:
                attachment_root = safe_join(
                    attachments_root,
                    storage_path,
                    escape_message="Attachment cleanup path escapes its root",
                )
            except PermissionError:
                continue
            shutil.rmtree(attachment_root, ignore_errors=True)
            try:
                attachment_root.parent.rmdir()
            except OSError:
                pass
        return len(storage_paths)

    def delete_session_files(self, session_id: str) -> None:
        shutil.rmtree(agent_session_attachments_root(session_id), ignore_errors=True)

    async def ingest_files(
        self,
        *,
        agent_session: AgentSession,
        files: list[UploadFile],
    ) -> list[AgentAttachment]:
        if not files:
            raise BadRequestError("At least one file is required")
        attachments: list[AgentAttachment] = []
        for file in files:
            attachments.append(
                await self._ingest_single(
                    agent_session=agent_session,
                    file=file,
                    requested_kind="file",
                    source="upload",
                )
            )
        return attachments

    async def ingest_image(
        self,
        *,
        agent_session: AgentSession,
        file: UploadFile,
        source: str = "clipboard",
    ) -> AgentAttachment:
        return await self._ingest_single(
            agent_session=agent_session,
            file=file,
            requested_kind="image",
            source=source,
        )

    async def ingest_folder(
        self,
        *,
        agent_session: AgentSession,
        files: list[UploadFile],
        relative_paths: list[str],
    ) -> AgentAttachment:
        if not files or len(files) != len(relative_paths):
            raise BadRequestError("Folder files and relative paths must match")
        normalized_paths = [_normalize_relative_path(path) for path in relative_paths]
        if len(set(normalized_paths)) != len(normalized_paths):
            raise BadRequestError("Folder contains duplicate paths")

        accepted = [
            (file, relative_path)
            for file, relative_path in zip(files, normalized_paths)
            if not _ignored_folder_path(relative_path)
        ]
        if not accepted:
            raise BadRequestError("Folder does not contain supported files")
        if len(accepted) > settings.agent_attachment_folder_max_files:
            raise BadRequestError("Folder contains too many files")

        attachment_id = str(uuid4())
        session_id = str(agent_session.id)
        session_root = agent_session_attachments_root(session_id)
        staging_root = session_root / f".{attachment_id}.staging"
        final_root = agent_attachment_root(session_id, attachment_id)
        total_bytes = 0
        manifest: list[str] = []
        try:
            staging_root.mkdir(parents=True, exist_ok=False)
            files_root = staging_root / "files"
            files_root.mkdir()
            for file, relative_path in accepted:
                target = safe_join(
                    files_root,
                    relative_path,
                    escape_message="Folder path escapes attachment root",
                )
                target.parent.mkdir(parents=True, exist_ok=True)
                size_bytes, _ = await _stream_upload(
                    file,
                    target,
                    max_bytes=settings.agent_attachment_file_max_bytes,
                )
                total_bytes += size_bytes
                if total_bytes > settings.agent_attachment_folder_max_bytes:
                    raise BadRequestError("Folder exceeds the upload size limit")
                _detect_supported_type(target)
                manifest.append(relative_path)
            manifest.sort()
            (staging_root / "manifest.json").write_text(
                json.dumps(manifest, ensure_ascii=False, separators=(",", ":")),
                encoding="utf-8",
            )
            staging_root.rename(final_root)
            folder_name = PurePosixPath(normalized_paths[0]).parts[0]
            return await self._commit_attachment(
                attachment_id=attachment_id,
                agent_session=agent_session,
                kind="folder",
                source="upload",
                filename=folder_name,
                mime_type="application/x-directory",
                size_bytes=total_bytes,
                file_count=len(manifest),
                metadata={
                    "manifest": manifest,
                    "manifest_relpath": "manifest.json",
                    "files_relpath": "files",
                    "ignored_count": len(files) - len(accepted),
                },
                final_root=final_root,
            )
        except Exception:
            shutil.rmtree(staging_root, ignore_errors=True)
            shutil.rmtree(final_root, ignore_errors=True)
            raise

    async def preview_path(
        self,
        *,
        attachment_id: str,
        workspace_id: str,
        user_id: str,
    ) -> tuple[Path, str]:
        attachment = await self.repo.get_owned_for_user(
            attachment_id,
            workspace_id=workspace_id,
            user_id=user_id,
        )
        if attachment is None or attachment.status != AgentAttachmentStatus.READY:
            raise NotFoundError("Attachment not found")
        metadata = attachment.attachment_metadata or {}
        preview_relpath = metadata.get("preview_relpath")
        if not isinstance(preview_relpath, str):
            raise NotFoundError("Attachment preview is not available")
        root = self.validated_root(attachment)
        path = safe_join(
            root,
            preview_relpath,
            escape_message="Attachment preview escapes its storage root",
        )
        if not path.is_file() or path.is_symlink():
            raise NotFoundError("Attachment preview is not available")
        return path, attachment.mime_type or "application/octet-stream"

    async def delete_pending(
        self,
        *,
        attachment_id: str,
        workspace_id: str,
        user_id: str,
    ) -> None:
        attachment = await self.repo.get_owned_for_user(
            attachment_id,
            workspace_id=workspace_id,
            user_id=user_id,
        )
        if attachment is None:
            raise NotFoundError("Attachment not found")
        root = self.validated_root(attachment)
        await self.repo.mark_pending_delete(
            attachment_id,
            session_id=str(attachment.session_id),
            workspace_id=workspace_id,
            user_id=user_id,
        )
        shutil.rmtree(root, ignore_errors=True)
        deleted = await self.repo.delete_owned(
            attachment_id,
            workspace_id=workspace_id,
            user_id=user_id,
        )
        if not deleted:
            raise NotFoundError("Attachment not found")

    async def _ingest_single(
        self,
        *,
        agent_session: AgentSession,
        file: UploadFile,
        requested_kind: str,
        source: str,
    ) -> AgentAttachment:
        attachment_id = str(uuid4())
        session_id = str(agent_session.id)
        session_root = agent_session_attachments_root(session_id)
        staging_root = session_root / f".{attachment_id}.staging"
        final_root = agent_attachment_root(session_id, attachment_id)
        try:
            staging_root.mkdir(parents=True, exist_ok=False)
            original_path = staging_root / "original"
            max_bytes = (
                settings.agent_attachment_image_max_bytes
                if requested_kind == "image"
                else settings.agent_attachment_file_max_bytes
            )
            size_bytes, sha256 = await _stream_upload(
                file,
                original_path,
                max_bytes=max_bytes,
            )
            detected = _detect_supported_type(original_path)
            if requested_kind == "image" and not detected.startswith("image/"):
                raise BadRequestError("Clipboard content is not a supported image")

            kind = "image" if detected.startswith("image/") else "file"
            metadata: dict[str, Any] = {
                "sha256": sha256,
                "preview_relpath": "original",
            }
            image_width = None
            image_height = None
            if kind == "image":
                image_width, image_height, model_mime = _prepare_image(
                    original_path,
                    staging_root / "model",
                )
                metadata.update(
                    {
                        "model_relpath": "model",
                        "model_mime_type": model_mime,
                    }
                )
            staging_root.rename(final_root)
            return await self._commit_attachment(
                attachment_id=attachment_id,
                agent_session=agent_session,
                kind=kind,
                source=source,
                filename=_display_filename(file.filename),
                mime_type=detected,
                size_bytes=size_bytes,
                image_width=image_width,
                image_height=image_height,
                metadata=metadata,
                final_root=final_root,
            )
        except Exception:
            shutil.rmtree(staging_root, ignore_errors=True)
            shutil.rmtree(final_root, ignore_errors=True)
            raise

    async def _commit_attachment(
        self,
        *,
        attachment_id: str,
        agent_session: AgentSession,
        kind: str,
        source: str,
        filename: str,
        mime_type: str,
        size_bytes: int,
        metadata: dict[str, Any],
        final_root: Path,
        file_count: int | None = None,
        image_width: int | None = None,
        image_height: int | None = None,
    ) -> AgentAttachment:
        try:
            return await self.repo.create(
                id=attachment_id,
                session_id=str(agent_session.id),
                workspace_id=str(agent_session.workspace_id),
                user_id=agent_session.user_id,
                kind=kind,
                source=source,
                filename=filename,
                storage_path=f"{agent_session.id}/{attachment_id}",
                mime_type=mime_type,
                size_bytes=size_bytes,
                file_count=file_count,
                image_width=image_width,
                image_height=image_height,
                status=AgentAttachmentStatus.READY,
                attachment_metadata=metadata,
            )
        except Exception:
            shutil.rmtree(final_root, ignore_errors=True)
            raise

    def validated_root(self, attachment: AgentAttachment) -> Path:
        expected = agent_attachment_root(
            str(attachment.session_id), str(attachment.id)
        ).resolve()
        stored = safe_join(
            agent_attachments_root(),
            attachment.storage_path,
            escape_message="Attachment storage path escapes its root",
        )
        if stored != expected:
            raise NotFoundError("Attachment storage is invalid")
        return stored


async def _stream_upload(
    upload: UploadFile,
    target: Path,
    *,
    max_bytes: int,
) -> tuple[int, str]:
    size_bytes = 0
    digest = hashlib.sha256()
    async with aiofiles.open(target, "xb") as output:
        while chunk := await upload.read(1024 * 1024):
            size_bytes += len(chunk)
            if size_bytes > max_bytes:
                raise BadRequestError("Attachment exceeds the upload size limit")
            digest.update(chunk)
            await output.write(chunk)
    if size_bytes == 0:
        raise BadRequestError("Attachment is empty")
    return size_bytes, digest.hexdigest()


def _detect_supported_type(path: Path) -> str:
    head = path.read_bytes()[:16]
    for signature, mime_type in _IMAGE_SIGNATURES:
        if head.startswith(signature):
            return mime_type
    if head.startswith(b"RIFF") and head[8:12] == b"WEBP":
        return "image/webp"
    if head.startswith(b"%PDF-"):
        try:
            reader = PdfReader(path)
            if reader.is_encrypted or len(reader.pages) > settings.agent_attachment_pdf_max_pages:
                raise BadRequestError("PDF is encrypted or has too many pages")
        except BadRequestError:
            raise
        except Exception as exc:
            raise BadRequestError("PDF is damaged or unsupported") from exc
        return "application/pdf"
    try:
        path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise BadRequestError("Unsupported attachment type") from exc
    return "text/plain"


def _prepare_image(original: Path, derivative: Path) -> tuple[int, int, str]:
    try:
        with Image.open(original) as opened:
            source_format = opened.format
            image = ImageOps.exif_transpose(opened)
            image.load()
            if source_format not in {"PNG", "JPEG", "WEBP"}:
                raise BadRequestError("Unsupported image type")
            image.thumbnail((2048, 2048), Image.Resampling.LANCZOS)
            width, height = image.size
            if image.mode not in {"RGB", "RGBA"}:
                image = image.convert("RGBA" if "A" in image.getbands() else "RGB")
            if image.mode == "RGBA":
                image.save(derivative, format="PNG", optimize=True)
                mime_type = "image/png"
            else:
                image.save(derivative, format="JPEG", quality=90, optimize=True)
                mime_type = "image/jpeg"
            return width, height, mime_type
    except BadRequestError:
        raise
    except (UnidentifiedImageError, OSError) as exc:
        raise BadRequestError("Image is damaged or unsupported") from exc


def _display_filename(filename: str | None) -> str:
    display = Path(filename or "attachment").name.strip()
    return display or "attachment"


def _normalize_relative_path(value: str) -> str:
    if not value or "\\" in value or "//" in value or value.startswith("/"):
        raise BadRequestError("Folder contains an invalid path")
    path = PurePosixPath(value)
    if any(part in {"", ".", ".."} for part in path.parts):
        raise BadRequestError("Folder contains an invalid path")
    normalized = path.as_posix()
    if not normalized or normalized == ".":
        raise BadRequestError("Folder contains an invalid path")
    return normalized


def _ignored_folder_path(relative_path: str) -> bool:
    parts = PurePosixPath(relative_path).parts
    lowered = [part.lower() for part in parts]
    if any(part in _IGNORED_DIRECTORY_NAMES for part in lowered[:-1]):
        return True
    filename = lowered[-1]
    return filename in _IGNORED_FILENAMES or Path(filename).suffix in _IGNORED_SUFFIXES
