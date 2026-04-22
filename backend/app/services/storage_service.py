from __future__ import annotations

import asyncio
import fnmatch
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.path_layout import (
    deliveries_root,
    database_root,
    project_data_root,
    project_runs_root,
    resolve_asset as resolve_asset_uri,
    run_results_root,
    safe_join,
    reference_root,
)
from app.repositories.project_repo import ProjectRepository
from app.schemas.file import FileType
from app.schemas.storage import (
    ResolvedAsset,
    ResolvedStorageSource,
    StorageBrowseResponse,
    StorageFileInfo,
    StorageReadResponse,
    StorageSample,
    StorageSampleFile,
    StorageScanResponse,
    StorageSourceKind,
    StorageSourceRead,
    StorageUploadResponse,
)
from app.services.file_service import FILE_TYPE_EXTENSIONS, _detect_file_type, _parse_fastq


class StorageService:
    def __init__(self, session: AsyncSession):
        self.project_repo = ProjectRepository(session)

    async def list_sources(self, *, project_id: str) -> list[StorageSourceRead]:
        await self._require_project(project_id)
        return [
            self._project_source(),
            self._results_source(),
            self._deliveries_source(),
            self._reference_source(),
            self._database_source(),
        ]

    async def resolve_asset(self, *, project_id: str, uri: str) -> ResolvedAsset:
        project = await self._require_project(project_id)
        resolved = resolve_asset_uri(project, uri)
        return ResolvedAsset(
            source=self._source_by_id(resolved.source_id),
            relative_path=resolved.relative_path,
            path=resolved.path,
        )

    async def browse(
        self,
        *,
        project_id: str,
        source_id: str,
        path: str = ".",
        recursive: bool = False,
        pattern: str | None = None,
    ) -> StorageBrowseResponse:
        project = await self._require_project(project_id)
        if source_id == "results":
            files = self._browse_results(project, path=path, recursive=recursive, pattern=pattern)
            return StorageBrowseResponse(
                source=self._results_source(),
                path=str(Path(path)),
                files=files,
            )

        resolved = self._resolve_standard_source(project=project, source_id=source_id)
        root = Path(resolved.root)
        target = safe_join(root, path, escape_message="path escapes source")
        if not target.exists():
            raise FileNotFoundError("path not found")

        if target.is_file():
            files = [
                self._storage_file_info(
                    source_id=source_id,
                    root=root,
                    path=target,
                    recursive=recursive,
                    pattern=pattern,
                )
            ]
        else:
            files = [
                info
                for child in sorted(target.iterdir())
                if (
                    info := self._storage_file_info(
                        source_id=source_id,
                        root=root,
                        path=child,
                        recursive=recursive,
                        pattern=pattern,
                    )
                )
                is not None
            ]

        return StorageBrowseResponse(
            source=resolved.source,
            path=str(Path(path)),
            files=files,
        )

    async def read(
        self,
        *,
        project_id: str,
        uri: str,
        lines: int = 100,
        offset: int = 0,
    ) -> StorageReadResponse:
        resolved = await self.resolve_asset(project_id=project_id, uri=uri)
        target = Path(resolved.path)
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
        return StorageReadResponse(
            uri=uri,
            content="".join(content_lines),
            total_lines=total_lines,
            truncated=offset + lines < total_lines,
        )

    async def upload(
        self,
        *,
        project_id: str,
        source_id: str,
        path: str | None,
        filename: str,
        content: bytes,
        overwrite: bool = False,
    ) -> StorageUploadResponse:
        project = await self._require_project(project_id)
        resolved = self._resolve_standard_source(project=project, source_id=source_id)
        if not resolved.source.upload_allowed:
            raise PermissionError("source is read-only")

        root = Path(resolved.root)
        relative_base = (path or ".").strip() or "."
        relative_target = filename if relative_base == "." else f"{relative_base.rstrip('/')}/{filename}"
        target = safe_join(root, relative_target, escape_message="path escapes source")
        if target.exists() and not overwrite:
            raise FileExistsError("file already exists")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        rel_path = str(target.relative_to(root))
        return StorageUploadResponse(uri=f"asset://{source_id}/{rel_path}", path=rel_path)

    async def scan(
        self,
        *,
        project_id: str,
        source_id: str,
        path: str = ".",
        file_types: list[str] | None = None,
    ) -> StorageScanResponse:
        project = await self._require_project(project_id)
        resolved = self._resolve_standard_source(project=project, source_id=source_id)
        root = Path(resolved.root)
        target = safe_join(root, path, escape_message="path escapes source")
        if not target.exists() or not target.is_dir():
            raise FileNotFoundError("path not found")

        types = [t.lower() for t in (file_types or FILE_TYPE_EXTENSIONS.keys())]
        extensions = {t: FILE_TYPE_EXTENSIONS[t] for t in types if t in FILE_TYPE_EXTENSIONS}

        detected: dict[str, list[StorageSampleFile]] = {}
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
                    file_format = "paired-end" if file_format != "single-end" else file_format
                else:
                    file_kind = "fastq"
                    file_format = file_format or "single-end"
            else:
                sample_id = file_path.stem
                file_kind = file_type

            detected.setdefault(sample_id, []).append(
                StorageSampleFile(
                    type=file_kind,
                    uri=f"asset://{source_id}/{rel_path}",
                    path=rel_path,
                )
            )

        samples = [StorageSample(sample_id=sample_id, files=files) for sample_id, files in detected.items()]
        return StorageScanResponse(
            source_id=source_id,
            path=str(Path(path)),
            detected_samples=samples,
            file_format=file_format,
            compression=compression,
            total_samples=len(samples),
        )

    async def _require_project(self, project_id: str):
        project = await self.project_repo.get(project_id)
        if not project:
            raise FileNotFoundError("project not found")
        return project

    def _resolve_standard_source(self, *, project, source_id: str) -> ResolvedStorageSource:
        if source_id == "project":
            root = project_data_root(project)
            return ResolvedStorageSource(source=self._project_source(), root=str(root))
        if source_id == "deliveries":
            return ResolvedStorageSource(
                source=self._deliveries_source(),
                root=str(deliveries_root()),
            )
        if source_id == "reference":
            return ResolvedStorageSource(
                source=self._reference_source(),
                root=str(reference_root()),
            )
        if source_id == "database":
            return ResolvedStorageSource(
                source=self._database_source(),
                root=str(database_root()),
            )
        raise FileNotFoundError("invalid source")

    def _browse_results(self, project, *, path: str, recursive: bool, pattern: str | None) -> list[StorageFileInfo]:
        runs_root = project_runs_root(project)
        normalized = str(Path(path))
        if normalized in {".", ""}:
            files: list[StorageFileInfo] = []
            for run_dir in sorted(runs_root.iterdir()) if runs_root.exists() else []:
                results_root = run_results_root(project, run_dir.name)
                if not results_root.exists():
                    continue
                stat = results_root.stat()
                files.append(
                    StorageFileInfo(
                        name=run_dir.name,
                        path=run_dir.name,
                        uri=f"asset://results/{run_dir.name}",
                        type=FileType.DIRECTORY,
                        size_bytes=None,
                        modified_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
                    )
                )
            return files

        run_id, sep, nested = normalized.partition("/")
        if not run_id:
            raise FileNotFoundError("invalid results path")
        root = run_results_root(project, run_id)
        if not root.exists():
            raise FileNotFoundError("run results not found")
        target = safe_join(root, nested or ".", escape_message="path escapes run results")
        if not target.exists():
            raise FileNotFoundError("path not found")

        items = [target] if target.is_file() else sorted(target.iterdir())
        files: list[StorageFileInfo] = []
        for item in items:
            rel_path = str(item.relative_to(root))
            info = self._storage_file_info(
                source_id="results",
                root=root,
                path=item,
                recursive=recursive,
                pattern=pattern,
                uri_path=f"{run_id}/{rel_path}",
            )
            if info is not None:
                files.append(info)
        return files

    def _project_source(self) -> StorageSourceRead:
        return StorageSourceRead(
            id="project",
            label="Project Data",
            kind=StorageSourceKind.PROJECT,
            read_only=False,
            upload_allowed=True,
            scan_allowed=True,
        )

    def _results_source(self) -> StorageSourceRead:
        return StorageSourceRead(
            id="results",
            label="Run Results",
            kind=StorageSourceKind.RESULTS,
            read_only=True,
            upload_allowed=False,
            scan_allowed=False,
        )

    def _deliveries_source(self) -> StorageSourceRead:
        return StorageSourceRead(
            id="deliveries",
            label="Deliveries",
            kind=StorageSourceKind.DELIVERIES,
            read_only=True,
            upload_allowed=False,
            scan_allowed=True,
        )

    def _reference_source(self) -> StorageSourceRead:
        return StorageSourceRead(
            id="reference",
            label="Reference",
            kind=StorageSourceKind.REFERENCE,
            read_only=True,
            upload_allowed=False,
            scan_allowed=True,
        )

    def _database_source(self) -> StorageSourceRead:
        return StorageSourceRead(
            id="database",
            label="Database",
            kind=StorageSourceKind.DATABASE,
            read_only=True,
            upload_allowed=False,
            scan_allowed=True,
        )

    def _source_by_id(self, source_id: str) -> StorageSourceRead:
        mapping = {
            "project": self._project_source(),
            "results": self._results_source(),
            "deliveries": self._deliveries_source(),
            "reference": self._reference_source(),
            "database": self._database_source(),
        }
        return mapping[source_id]

    def _storage_file_info(
        self,
        *,
        source_id: str,
        root: Path,
        path: Path,
        recursive: bool,
        pattern: str | None,
        uri_path: str | None = None,
    ) -> StorageFileInfo | None:
        if path.is_file() and pattern and not fnmatch.fnmatch(path.name, pattern):
            return None

        stat = path.stat()
        rel_path = str(path.relative_to(root))
        logical_path = uri_path or rel_path
        return StorageFileInfo(
            name=path.name,
            path=rel_path,
            uri=f"asset://{source_id}/{logical_path}" if logical_path else f"asset://{source_id}",
            type=FileType.FILE if path.is_file() else FileType.DIRECTORY,
            size_bytes=stat.st_size if path.is_file() else None,
            modified_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
        )
