from __future__ import annotations

import asyncio
import fnmatch
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from sqlalchemy.ext.asyncio import AsyncSession

from app.path_layout import project_home
from app.repositories.project_repo import ProjectRepository
from app.schemas.file import (
    DetectedSample,
    DetectedSampleFile,
    FileInfo,
    FileListResponse,
    FileReadResponse,
    FileScanResponse,
    FileType,
)


FILE_TYPE_EXTENSIONS = {
    "fastq": [".fastq", ".fq", ".fastq.gz", ".fq.gz"],
    "bam": [".bam"],
    "vcf": [".vcf", ".vcf.gz"],
    "cram": [".cram"],
}


class FileService:
    def __init__(self, session: AsyncSession):
        self.project_repo = ProjectRepository(session)

    async def _workspace_root(self, project_id: str) -> Path:
        return await self._resolve_root(project_id, data_root=None)

    async def _resolve_root(
        self, project_id: str, data_root: int | None = None
    ) -> Path:
        project = await self.project_repo.get(project_id)
        if not project:
            raise FileNotFoundError("project not found")
        return project_home(project)

    def _safe_path(self, root: Path, relative_path: str) -> Path:
        target = (root / relative_path).resolve()
        if not target.is_relative_to(root):
            raise PermissionError("path escapes workspace")
        return target

    def _file_info(
        self, path: Path, root: Path, recursive: bool, pattern: str | None
    ) -> FileInfo | None:
        if path.is_file() and pattern and not fnmatch.fnmatch(path.name, pattern):
            return None

        stat = path.stat()
        info = FileInfo(
            name=path.name,
            path=str(path.relative_to(root)),
            type=FileType.FILE if path.is_file() else FileType.DIRECTORY,
            size_bytes=stat.st_size if path.is_file() else None,
            modified_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
            children=None,
        )

        if path.is_dir() and recursive:
            children = []
            for child in sorted(path.iterdir()):
                child_info = self._file_info(child, root, recursive, pattern)
                if child_info is not None:
                    children.append(child_info)
            info.children = children
            if pattern and not children:
                return None

        return info

    async def list_files(
        self,
        *,
        project_id: str,
        path: str = ".",
        recursive: bool = False,
        pattern: str | None = None,
        data_root: int | None = None,
    ) -> FileListResponse:
        root = await self._resolve_root(project_id, data_root)
        target = self._safe_path(root, path)

        if not target.exists():
            raise FileNotFoundError("path not found")

        files: list[FileInfo] = []
        if target.is_file():
            info = self._file_info(target, root, recursive, pattern)
            if info:
                files.append(info)
        else:
            for child in sorted(target.iterdir()):
                info = self._file_info(child, root, recursive, pattern)
                if info:
                    files.append(info)

        return FileListResponse(path=str(Path(path)), files=files)

    async def resolve_path(self, *, project_id: str, path: str) -> tuple[Path, Path]:
        root = await self._workspace_root(project_id)
        target = self._safe_path(root, path)
        if not target.exists():
            raise FileNotFoundError("path not found")
        return target, root

    async def delete_path(self, *, project_id: str, path: str) -> dict:
        root = await self._workspace_root(project_id)
        target = self._safe_path(root, path)
        if target == root:
            raise PermissionError("cannot delete workspace root")
        if not target.exists():
            raise FileNotFoundError("path not found")
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
        return {"path": str(Path(path))}

    async def write_upload(
        self,
        *,
        project_id: str,
        path: str | None,
        filename: str,
        content: bytes,
        overwrite: bool = False,
    ) -> dict:
        root = await self._workspace_root(project_id)
        normalized_path = path or filename
        target = self._safe_path(root, normalized_path)
        if target.exists():
            if target.is_dir():
                target = self._safe_path(target, filename)
            elif not overwrite:
                raise FileExistsError("file already exists")

        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        return {"path": str(target.relative_to(root))}

    async def read_file(
        self, *, project_id: str, path: str, lines: int = 100, offset: int = 0
    ) -> FileReadResponse:
        root = await self._workspace_root(project_id)
        target = self._safe_path(root, path)
        if not target.exists() or not target.is_file():
            raise FileNotFoundError("file not found")

        def _read_lines() -> tuple[list[str], int]:
            result: list[str] = []
            count = 0
            with target.open("r", encoding="utf-8", errors="ignore") as handle:
                for index, line in enumerate(handle):
                    if index >= offset and len(result) < lines:
                        result.append(line)
                    count += 1
            return result, count

        content_lines, total_lines = await asyncio.to_thread(_read_lines)

        truncated = offset + lines < total_lines

        return FileReadResponse(
            path=str(Path(path)),
            content="".join(content_lines),
            total_lines=total_lines,
            truncated=truncated,
        )

    async def write_file(self, *, project_id: str, path: str, content: str) -> dict:
        root = await self._workspace_root(project_id)
        target = self._safe_path(root, path)
        target.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(target.write_text, content)
        return {"path": str(Path(path))}

    async def scan_directory(
        self, *, project_id: str, path: str = ".", file_types: list[str] | None = None,
        data_root: int | None = None,
    ) -> FileScanResponse:
        root = await self._resolve_root(project_id, data_root)
        target = self._safe_path(root, path)
        if not target.exists() or not target.is_dir():
            raise FileNotFoundError("path not found")

        types = [t.lower() for t in (file_types or FILE_TYPE_EXTENSIONS.keys())]
        extensions = {
            t: FILE_TYPE_EXTENSIONS[t] for t in types if t in FILE_TYPE_EXTENSIONS
        }

        detected: dict[str, list[DetectedSampleFile]] = {}
        compression = None
        file_format = None

        for file_path in target.rglob("*"):
            if not file_path.is_file():
                continue
            file_type = _detect_file_type(file_path, extensions)
            if not file_type:
                continue
            if file_path.name.endswith(".gz"):
                compression = "gzip"

            rel_path = str(file_path.relative_to(root))
            if file_type == "fastq":
                sample_id, read_type = _parse_fastq(file_path.name)
                if read_type in {"1", "2"}:
                    file_kind = f"fastq_{read_type}"
                    file_format = (
                        "paired-end" if file_format != "single-end" else file_format
                    )
                else:
                    file_kind = "fastq"
                    file_format = file_format or "single-end"
            else:
                sample_id = file_path.stem
                file_kind = file_type

            detected.setdefault(sample_id, []).append(
                DetectedSampleFile(type=file_kind, path=rel_path)
            )

        samples = [
            DetectedSample(sample_id=sample_id, files=files)
            for sample_id, files in detected.items()
        ]

        return FileScanResponse(
            path=str(Path(path)),
            detected_samples=samples,
            file_format=file_format,
            compression=compression,
            total_samples=len(samples),
        )


def _detect_file_type(path: Path, extensions: dict[str, Iterable[str]]) -> str | None:
    name = path.name.lower()
    for file_type, exts in extensions.items():
        for ext in exts:
            if name.endswith(ext):
                return file_type
    return None


def _parse_fastq(file_name: str) -> tuple[str, str | None]:
    name = file_name
    for ext in [".fastq.gz", ".fq.gz", ".fastq", ".fq"]:
        if name.lower().endswith(ext):
            name = name[: -len(ext)]
            break

    match = re.match(r"(.+)_R([12])(?:_\d+)?$", name)
    if not match:
        match = re.match(r"(.+)_([12])$", name)
    if match:
        return match.group(1), match.group(2)
    return name, None
