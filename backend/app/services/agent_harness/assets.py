from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import uuid4

import aiofiles
from fastapi import UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError
from pypdf import PdfReader
from app.config import settings
from app.models.agent_harness import (
    AgentHarnessAttachment,
    AgentHarnessSession,
)
from app.path_layout import (
    agent_attachment_root,
    agent_attachments_root,
    agent_harness_tombstones_root,
    agent_session_artifacts_root,
    agent_session_attachments_root,
    legacy_agent_attachments_root,
    safe_join,
    state_root,
)
from app.repositories.agent_harness_repo import (
    AgentHarnessAttachmentRepository,
)
from app.services.agent_harness.artifact_service import (
    AgentHarnessArtifactService,
    artifact_reference_part,
)
from app.services.model_runtime.contracts import ImagePart, InputPart, TextPart
from app.utils.exceptions import BadRequestError, ConflictError, NotFoundError


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
_SESSION_DELETE_TOMBSTONE_GRACE = timedelta(minutes=5)


@dataclass(frozen=True)
class AgentSessionFileTombstone:
    session_id: str
    root: Path

    def restore(self) -> None:
        for name, destination in self._resources():
            source = self.root / name
            if not source.exists():
                continue
            if destination.exists():
                raise RuntimeError(
                    f"Cannot restore Agent session {name}; destination already exists"
                )
            destination.parent.mkdir(parents=True, exist_ok=True)
            source.rename(destination)
        shutil.rmtree(self.root, ignore_errors=True)

    def purge(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)

    def purge_deleted_session_files(self) -> None:
        """Remove staged and concurrently recreated files after durable deletion."""

        for _, destination in self._resources():
            shutil.rmtree(destination, ignore_errors=True)
        self.purge()

    def _resources(self) -> tuple[tuple[str, Path], ...]:
        return (
            ("attachments", agent_session_attachments_root(self.session_id)),
            ("artifacts", agent_session_artifacts_root(self.session_id)),
        )


def stage_agent_session_files_for_delete(session_id: str) -> AgentSessionFileTombstone:
    root = agent_harness_tombstones_root() / f"{session_id}-{uuid4()}"
    tombstone = AgentSessionFileTombstone(session_id=session_id, root=root)
    root.mkdir(parents=True, exist_ok=False)
    (root / "manifest.json").write_text(
        json.dumps({"session_id": session_id}, separators=(",", ":")),
        encoding="utf-8",
    )
    try:
        for name, source in tombstone._resources():
            if source.exists():
                source.rename(root / name)
        return tombstone
    except Exception:
        tombstone.restore()
        raise


async def recover_agent_session_file_tombstones(
    db,
    *,
    before: datetime | None = None,
) -> int:
    root = agent_harness_tombstones_root()
    if not root.exists():
        return 0
    recovered = 0
    for path in sorted(root.iterdir(), key=lambda item: item.name):
        if not path.is_dir() or path.is_symlink():
            continue
        if before is not None:
            modified = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
            if modified >= before:
                continue
        try:
            manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
            session_id = str(manifest["session_id"])
            tombstone = AgentSessionFileTombstone(session_id=session_id, root=path)
            if await db.get(AgentHarnessSession, session_id) is None:
                tombstone.purge_deleted_session_files()
            else:
                tombstone.restore()
            recovered += 1
        except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
            continue
    return recovered


def migrate_legacy_agent_attachments() -> int:
    legacy_root = legacy_agent_attachments_root()
    current_root = agent_attachments_root()
    if legacy_root.is_symlink():
        raise RuntimeError("Legacy attachment root cannot be a symbolic link")
    _assert_attachment_migration_root(legacy_root, label="Legacy")
    if not legacy_root.exists():
        return 0
    if not legacy_root.is_dir():
        raise RuntimeError("Legacy attachment root is not a directory")
    if current_root.is_symlink():
        raise RuntimeError("Current attachment root cannot be a symbolic link")
    _assert_attachment_migration_root(current_root, label="Current")
    current_root.mkdir(parents=True, exist_ok=True)

    migrated = 0
    for session_source in sorted(legacy_root.iterdir(), key=lambda path: path.name):
        if session_source.is_symlink():
            raise RuntimeError("Legacy attachment session cannot be a symbolic link")
        if not session_source.is_dir():
            raise RuntimeError("Legacy attachment root contains an invalid entry")
        try:
            agent_session_attachments_root(session_source.name)
        except ValueError as exc:
            raise RuntimeError("Legacy attachment session path is invalid") from exc

        for source in sorted(session_source.iterdir(), key=lambda path: path.name):
            if source.name.startswith(".migrated-"):
                _cleanup_attachment_migration_tombstone(
                    source,
                    session_id=session_source.name,
                )
                continue
            if source.is_symlink():
                raise RuntimeError("Legacy attachment cannot be a symbolic link")
            if not source.is_dir():
                raise RuntimeError(
                    "Legacy attachment session contains an invalid entry"
                )
            source_digest = _attachment_tree_digest(source)
            try:
                target = _migration_target(
                    session_id=session_source.name,
                    attachment_id=source.name,
                )
            except (PermissionError, ValueError) as exc:
                raise RuntimeError("Legacy attachment path is invalid") from exc
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.is_symlink():
                raise RuntimeError("Current attachment cannot be a symbolic link")
            if not target.exists():
                source.rename(target)
                migrated += 1
                continue
            if not target.is_dir():
                raise RuntimeError("Legacy attachment migration conflict")
            if source_digest != _attachment_tree_digest(target):
                raise RuntimeError("Legacy attachment migration conflict")
            tombstone = session_source / f".migrated-{source.name}"
            if tombstone.exists() or tombstone.is_symlink():
                _cleanup_attachment_migration_tombstone(
                    tombstone,
                    session_id=session_source.name,
                )
            source.rename(tombstone)
            shutil.rmtree(tombstone)
            migrated += 1
        try:
            session_source.rmdir()
        except OSError:
            pass
    try:
        legacy_root.rmdir()
    except OSError:
        pass
    return migrated


def _assert_attachment_migration_root(root: Path, *, label: str) -> None:
    if not root.resolve().is_relative_to(state_root()):
        raise RuntimeError(f"{label} attachment root escapes state storage")


def _migration_target(*, session_id: str, attachment_id: str) -> Path:
    expected = agent_attachment_root(session_id, attachment_id).resolve()
    target = safe_join(
        agent_attachments_root(),
        f"{session_id}/{attachment_id}",
        escape_message="Legacy attachment migration escapes current storage",
    )
    if target != expected:
        raise ValueError("Legacy attachment migration target is invalid")
    return target


def _cleanup_attachment_migration_tombstone(
    tombstone: Path,
    *,
    session_id: str,
) -> None:
    attachment_id = tombstone.name.removeprefix(".migrated-")
    if not attachment_id or tombstone.is_symlink():
        raise RuntimeError("Legacy attachment migration tombstone is invalid")
    try:
        target = _migration_target(
            session_id=session_id,
            attachment_id=attachment_id,
        )
    except (PermissionError, ValueError) as exc:
        raise RuntimeError("Legacy attachment migration tombstone is invalid") from exc
    if not tombstone.is_dir():
        raise RuntimeError("Legacy attachment migration tombstone is invalid")
    if target.is_symlink() or not target.is_dir():
        raise RuntimeError("Legacy attachment migration conflict")
    if _attachment_tree_digest(tombstone) != _attachment_tree_digest(target):
        raise RuntimeError("Legacy attachment migration conflict")
    shutil.rmtree(tombstone)


def _attachment_tree_digest(root: Path) -> tuple[tuple[str, str, str], ...]:
    if root.is_symlink() or not root.is_dir():
        raise RuntimeError("Attachment tree is not a safe directory")
    entries: list[tuple[str, str, str]] = []
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        if path.is_symlink():
            raise RuntimeError("Attachment tree contains a symbolic link")
        relative = path.relative_to(root).as_posix()
        if path.is_dir():
            entries.append((relative, "directory", ""))
            continue
        if not path.is_file():
            raise RuntimeError("Attachment tree contains an unsupported entry")
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
        entries.append((relative, "file", digest.hexdigest()))
    return tuple(entries)


class AgentHarnessAttachmentService:
    def __init__(self, db) -> None:
        self.repo = AgentHarnessAttachmentRepository(db)

    def delete_session_files(self, session_id: str) -> None:
        shutil.rmtree(agent_session_attachments_root(session_id), ignore_errors=True)

    async def cleanup_orphans(self, *, cutoff: datetime | None = None) -> int:
        await recover_agent_session_file_tombstones(
            self.repo.session,
            before=datetime.now(timezone.utc) - _SESSION_DELETE_TOMBSTONE_GRACE,
        )
        effective_cutoff = cutoff or (
            datetime.now(timezone.utc)
            - timedelta(seconds=settings.agent_attachment_orphan_ttl_seconds)
        )
        storage_paths = await self.repo.delete_orphans_before(effective_cutoff)
        for storage_path in storage_paths:
            try:
                root = _attachment_storage_root(storage_path)
            except (PermissionError, ValueError):
                continue
            shutil.rmtree(root, ignore_errors=True)
            try:
                root.parent.rmdir()
            except OSError:
                pass
        return len(storage_paths)

    async def ingest_files(
        self,
        *,
        agent_session: AgentHarnessSession,
        files: list[UploadFile],
    ) -> list[AgentHarnessAttachment]:
        if not files:
            raise BadRequestError("At least one file is required")
        return [
            await self._ingest_single(
                agent_session=agent_session,
                file=file,
                requested_kind="file",
                source="upload",
            )
            for file in files
        ]

    async def ingest_image(
        self,
        *,
        agent_session: AgentHarnessSession,
        file: UploadFile,
        source: str = "clipboard",
    ) -> AgentHarnessAttachment:
        return await self._ingest_single(
            agent_session=agent_session,
            file=file,
            requested_kind="image",
            source=source,
        )

    async def ingest_folder(
        self,
        *,
        agent_session: AgentHarnessSession,
        files: list[UploadFile],
        relative_paths: list[str],
    ) -> AgentHarnessAttachment:
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
        staging_root = (
            agent_session_attachments_root(session_id) / f".{attachment_id}.staging"
        )
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
            return await self._commit_attachment(
                attachment_id=attachment_id,
                agent_session=agent_session,
                kind="folder",
                source="upload",
                filename=PurePosixPath(normalized_paths[0]).parts[0],
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
        if attachment is None or attachment.status != "ready":
            raise NotFoundError("Attachment not found")
        preview_relpath = (attachment.attachment_metadata or {}).get("preview_relpath")
        if not isinstance(preview_relpath, str):
            raise NotFoundError("Attachment preview is not available")
        path = safe_join(
            self.validated_root(attachment),
            preview_relpath,
            escape_message="Attachment preview escapes its storage root",
        )
        if not path.is_file() or path.is_symlink():
            raise NotFoundError("Attachment preview is not available")
        return path, attachment.mime_type or "application/octet-stream"

    async def delete(
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
        reservation = await self.repo.mark_pending_delete_if_unreferenced(
            attachment_id,
            workspace_id=workspace_id,
            user_id=user_id,
        )
        if reservation == "missing":
            raise NotFoundError("Attachment not found")
        if reservation == "referenced":
            raise ConflictError("Attachment is referenced by permanent session history")
        shutil.rmtree(root, ignore_errors=True)
        try:
            root.parent.rmdir()
        except OSError:
            pass
        if not await self.repo.delete_owned(
            attachment_id,
            workspace_id=workspace_id,
            user_id=user_id,
        ):
            raise NotFoundError("Attachment not found")

    async def _ingest_single(
        self,
        *,
        agent_session: AgentHarnessSession,
        file: UploadFile,
        requested_kind: str,
        source: str,
    ) -> AgentHarnessAttachment:
        attachment_id = str(uuid4())
        session_id = str(agent_session.id)
        staging_root = (
            agent_session_attachments_root(session_id) / f".{attachment_id}.staging"
        )
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
            image_width = image_height = None
            if kind == "image":
                image_width, image_height, model_mime = _prepare_image(
                    original_path,
                    staging_root / "model",
                )
                metadata.update(
                    {"model_relpath": "model", "model_mime_type": model_mime}
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
        agent_session: AgentHarnessSession,
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
    ) -> AgentHarnessAttachment:
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
                status="ready",
                attachment_metadata=metadata,
            )
        except Exception:
            shutil.rmtree(final_root, ignore_errors=True)
            raise

    def validated_root(self, attachment: AgentHarnessAttachment) -> Path:
        try:
            stored = _attachment_storage_root(attachment.storage_path)
        except (PermissionError, ValueError) as exc:
            raise NotFoundError("Attachment storage is invalid") from exc
        expected = agent_attachment_root(
            str(attachment.session_id), str(attachment.id)
        ).resolve()
        if stored != expected:
            raise NotFoundError("Attachment storage is invalid")
        return stored

    async def model_parts_for_ids(
        self,
        attachment_ids: list[str],
        *,
        session_id: str,
        workspace_id: str,
        user_id: str,
    ) -> dict[str, tuple[InputPart, ...]]:
        """Resolve durable attachment references into provider-neutral model parts."""

        resolved: dict[str, tuple[InputPart, ...]] = {}
        for attachment_id in dict.fromkeys(attachment_ids):
            attachment = await self.repo.get_owned(
                attachment_id,
                session_id=session_id,
                workspace_id=workspace_id,
                user_id=user_id,
            )
            if attachment is None or attachment.status != "ready":
                resolved[attachment_id] = (
                    TextPart(f"[Attachment unavailable: {attachment_id}]"),
                )
                continue
            try:
                resolved[attachment_id] = self._model_parts(attachment)
            except (OSError, ValueError, NotFoundError):
                resolved[attachment_id] = (
                    TextPart(
                        f"[Attachment could not be loaded: {attachment.filename} "
                        f"({attachment_id})]"
                    ),
                )
        return resolved

    def _model_parts(self, attachment: AgentHarnessAttachment) -> tuple[InputPart, ...]:
        metadata = attachment.attachment_metadata or {}
        root = self.validated_root(attachment)
        label = f"User attachment: {attachment.filename}"
        if attachment.kind == "image":
            relpath = str(metadata.get("model_relpath") or "original")
            path = safe_join(
                root,
                relpath,
                escape_message="Attachment model image escapes its storage root",
            )
            data = path.read_bytes()
            mime_type = str(
                metadata.get("model_mime_type")
                or attachment.mime_type
                or "application/octet-stream"
            )
            return (
                TextPart(label),
                ImagePart(
                    mime_type=mime_type,
                    data=base64.b64encode(data).decode("ascii"),
                    sha256=hashlib.sha256(data).hexdigest(),
                ),
            )
        if attachment.kind == "folder":
            manifest = metadata.get("manifest")
            paths = manifest if isinstance(manifest, list) else []
            listing = "\n".join(f"- {path}" for path in paths)
            return (TextPart(f"{label} (folder manifest):\n{listing}"),)
        original = safe_join(
            root,
            "original",
            escape_message="Attachment content escapes its storage root",
        )
        if attachment.mime_type == "application/pdf":
            text = _pdf_text(original)
        else:
            data = original.read_bytes()
            text = _bounded_attachment_text(data)
        return (TextPart(f"{label}\n\n{text}"),)


async def _stream_upload(
    upload: UploadFile, target: Path, *, max_bytes: int
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
            if (
                reader.is_encrypted
                or len(reader.pages) > settings.agent_attachment_pdf_max_pages
            ):
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


def _bounded_attachment_text(data: bytes) -> str:
    maximum = settings.agent_attachment_text_max_bytes
    truncated = len(data) > maximum
    text = data[:maximum].decode("utf-8", errors="replace")
    if truncated:
        text += "\n\n[Attachment truncated at the configured text context limit.]"
    return text


def _pdf_text(path: Path) -> str:
    maximum = settings.agent_attachment_text_max_bytes
    chunks: list[str] = []
    consumed = 0
    reader = PdfReader(path)
    for index, page in enumerate(reader.pages, start=1):
        page_text = page.extract_text() or ""
        chunk = f"\n--- Page {index} ---\n{page_text}"
        encoded = chunk.encode("utf-8")
        if consumed + len(encoded) > maximum:
            remaining = max(maximum - consumed, 0)
            chunks.append(encoded[:remaining].decode("utf-8", errors="ignore"))
            chunks.append(
                "\n\n[Attachment truncated at the configured text context limit.]"
            )
            break
        chunks.append(chunk)
        consumed += len(encoded)
    return "".join(chunks).strip() or "[PDF contains no extractable text.]"


def _display_filename(filename: str | None) -> str:
    return Path(filename or "attachment").name.strip() or "attachment"


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


def _attachment_storage_root(storage_path: str) -> Path:
    path = PurePosixPath(storage_path)
    if (
        not storage_path
        or path.is_absolute()
        or len(path.parts) != 2
        or path.as_posix() != storage_path
    ):
        raise ValueError("Attachment storage path is invalid")
    session_id, attachment_id = path.parts
    expected = agent_attachment_root(session_id, attachment_id)
    stored = safe_join(
        agent_attachments_root(),
        storage_path,
        escape_message="Attachment storage path escapes its root",
    )
    if stored != expected.resolve():
        raise ValueError("Attachment storage path is invalid")
    return stored


__all__ = [
    "AgentHarnessArtifactService",
    "AgentHarnessAttachmentService",
    "AgentSessionFileTombstone",
    "artifact_reference_part",
    "migrate_legacy_agent_attachments",
    "recover_agent_session_file_tombstones",
    "stage_agent_session_files_for_delete",
]
