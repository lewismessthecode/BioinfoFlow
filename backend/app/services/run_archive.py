"""Archive-related operations for pipeline runs.

Handles persisting run artifacts, listing/downloading output files,
and building downloadable archives (tar.gz / zip).
"""

from __future__ import annotations

import io
import json
import re
import shutil
import tarfile
import zipfile
from pathlib import Path

from app.models.run import Run
from app.path_layout import (
    project_home,
    run_results_root,
)
from app.repositories.project_repo import ProjectRepository
from app.services.run_helpers import config_helper, safe_workspace


_SECRET_KEY_RE = re.compile(
    r"(api[_-]?key|token|secret|password|passwd|authorization|bearer|private[_-]?key|access[_-]?key)",
    re.IGNORECASE,
)


def _redact_secrets(value):
    if isinstance(value, dict):
        redacted: dict = {}
        for k, v in value.items():
            if isinstance(k, str) and _SECRET_KEY_RE.search(k):
                redacted[k] = "[REDACTED]"
            else:
                redacted[k] = _redact_secrets(v)
        return redacted
    if isinstance(value, list):
        return [_redact_secrets(v) for v in value]
    return value


def _iter_safe_archive_paths(*, target: Path, root: Path) -> list[Path]:
    """
    Enumerate archive paths without following symlinks or escaping root.

    NOTE: This is critical for ZIP generation, since ZipFile.write() follows symlinks.
    """
    root_resolved = root.resolve()

    if target.is_symlink():
        raise PermissionError("refusing to archive symlink")

    target_resolved = target.resolve()
    if not target_resolved.is_relative_to(root_resolved):
        raise PermissionError("refusing to archive path outside root")

    if target.is_file():
        return [target]

    paths: list[Path] = [target]
    for item in target.rglob("*"):
        if item.is_symlink():
            continue
        resolved = item.resolve()
        if not resolved.is_relative_to(root_resolved):
            continue
        paths.append(item)
    return paths


def _tar_bytes(target: Path, root: Path) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        for path in _iter_safe_archive_paths(target=target, root=root):
            arcname = str(path.relative_to(root))
            tar.add(path, arcname=arcname, recursive=False)
    buffer.seek(0)
    return buffer.read()


def _zip_bytes(target: Path, root: Path) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in _iter_safe_archive_paths(target=target, root=root):
            arcname = str(path.relative_to(root))
            if path.is_dir():
                if not arcname.endswith("/"):
                    arcname = f"{arcname}/"
                archive.writestr(zipfile.ZipInfo(arcname), b"")
            else:
                archive.write(path, arcname=arcname)
    buffer.seek(0)
    return buffer.read()


class RunArchiveService:
    """Encapsulates archive/output operations extracted from RunService."""

    def __init__(self, project_repo: ProjectRepository) -> None:
        self._project_repo = project_repo

    # ------------------------------------------------------------------
    # Persist run archive on disk
    # ------------------------------------------------------------------

    async def persist_run_archive(
        self, *, run: Run, workspace_path: Path, engine: str
    ) -> None:
        run_dir = workspace_path / "runs" / run.run_id
        input_dir = run_dir / "input"
        request_dir = input_dir / "request"
        audit_dir = run_dir / "audit"
        request_dir.mkdir(parents=True, exist_ok=True)
        audit_dir.mkdir(parents=True, exist_ok=True)

        config = config_helper(run.config)
        params = _redact_secrets(config.params)
        inputs = _redact_secrets(config.inputs)
        config_overrides = _redact_secrets(config.config_overrides)
        resolved_runspec = _redact_secrets(config.resolved_runspec)
        request_config = config.to_dict().get("request", {}) or {}
        archive_documents = request_config.get("archive_documents", {}) or {}
        archived_params = _redact_secrets(archive_documents.get("params")) or params
        archived_inputs = _redact_secrets(archive_documents.get("inputs")) or inputs

        request_params_path = request_dir / "params.json"
        request_inputs_path = request_dir / "inputs.json"
        request_overrides_path = request_dir / "config_overrides.json"

        request_params_path.write_text(
            json.dumps(archived_params, indent=2), encoding="utf-8"
        )
        request_inputs_path.write_text(
            json.dumps(archived_inputs, indent=2), encoding="utf-8"
        )
        request_overrides_path.write_text(
            json.dumps(config_overrides, indent=2), encoding="utf-8"
        )

        documents = {
            "request_params": str(request_params_path.relative_to(workspace_path)),
            "request_inputs": str(request_inputs_path.relative_to(workspace_path)),
            "request_config_overrides": str(
                request_overrides_path.relative_to(workspace_path)
            ),
        }
        engine_inputs_path = run_dir / "engine" / str(engine).lower() / "inputs.json"
        if engine_inputs_path.exists():
            documents["engine_inputs"] = str(
                engine_inputs_path.relative_to(workspace_path)
            )

        manifest = {
            "run_id": run.run_id,
            "project_id": str(run.project_id),
            "workflow_id": str(run.workflow_id) if run.workflow_id else None,
            "engine": engine,
            "archive_version": 4,
            "documents": documents,
            "resolved_inputs": resolved_runspec,
        }
        (audit_dir / "run.manifest.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )

    # ------------------------------------------------------------------
    # List output files
    # ------------------------------------------------------------------

    async def list_outputs(self, run: Run) -> dict:
        output_root = await self.resolve_output_path(run)
        project = await self._project_repo.get(run.project_id)
        if not project:
            raise FileNotFoundError("project not found")
        if output_root is None or not output_root.exists():
            raise FileNotFoundError("output path not found")

        root = project_home(project)
        root_resolved = root.resolve()
        default_results_root = run_results_root(project, run.run_id).resolve()
        files = []
        for item in output_root.rglob("*"):
            if item.is_symlink():
                continue
            resolved = item.resolve()
            if not resolved.is_relative_to(root_resolved):
                continue

            rel_path = str(item.relative_to(root))
            if item.is_file():
                size = item.stat().st_size
                uri = _build_results_asset_uri(
                    run_id=run.run_id,
                    default_results_root=default_results_root,
                    path=item,
                )
                files.append(
                    {
                        "name": item.name,
                        "path": rel_path,
                        "uri": uri,
                        "size_bytes": size,
                        "type": "file",
                    }
                )
            else:
                uri = _build_results_asset_uri(
                    run_id=run.run_id,
                    default_results_root=default_results_root,
                    path=item,
                )
                files.append(
                    {
                        "name": item.name,
                        "path": rel_path,
                        "uri": uri,
                        "size_bytes": None,
                        "type": "directory",
                    }
                )

        return {"files": files}

    # ------------------------------------------------------------------
    # Build downloadable archive (tar.gz / zip)
    # ------------------------------------------------------------------

    async def build_output_archive(
        self,
        run: Run,
        *,
        file_path: str | None = None,
        archive_format: str = "tar.gz",
    ) -> tuple[bytes, str]:
        project = await self._project_repo.get(run.project_id)
        if not project:
            raise FileNotFoundError("project not found")
        root = project_home(project)

        if file_path:
            output_root = await self.resolve_output_path(run)
            if output_root is None:
                raise FileNotFoundError("output path not found")
            target = _resolve_output_file_path(
                project_root=root,
                output_root=output_root,
                file_path=file_path,
            )
        else:
            output_root = await self.resolve_output_path(run)
            if output_root is None:
                raise FileNotFoundError("output path not found")
            target = output_root

        if not target.exists():
            raise FileNotFoundError("output path not found")

        if archive_format == "zip":
            return _zip_bytes(target, root), "application/zip"
        return _tar_bytes(target, root), "application/gzip"

    # ------------------------------------------------------------------
    # Delete output files
    # ------------------------------------------------------------------

    async def delete_outputs(self, run: Run) -> None:
        output_root = await self.resolve_output_path(run)
        if output_root is None or not output_root.exists():
            return
        if output_root.is_file():
            output_root.unlink()
        else:
            shutil.rmtree(output_root)

    # ------------------------------------------------------------------
    # Resolve the output directory for a run
    # ------------------------------------------------------------------

    async def resolve_output_path(self, run: Run) -> Path | None:
        project = await self._project_repo.get(run.project_id)
        if not project:
            return None
        workspace_root = project_home(project)
        default_root = run_results_root(project, run.run_id)

        candidates: list[Path] = [default_root]
        seen = {str(default_root.resolve(strict=False))}

        if config_helper(run.config).version < 1:
            for outdir in _iter_outdir_candidates(run.config):
                try:
                    candidate = safe_workspace(workspace_root, outdir)
                except PermissionError:
                    continue
                marker = str(candidate.resolve(strict=False))
                if marker in seen:
                    continue
                seen.add(marker)
                candidates.append(candidate)

        for candidate in candidates:
            if _path_has_outputs(candidate):
                return candidate

        for candidate in candidates:
            if candidate.exists():
                return candidate

        return None


def _iter_outdir_candidates(config: dict) -> list[str]:
    candidates: list[str] = []
    sources = [
        config.get("params"),
        (config.get("request") or {}).get("params")
        if isinstance(config.get("request"), dict)
        else None,
        config_helper(config).params,
    ]
    for source in sources:
        if not isinstance(source, dict):
            continue
        outdir = source.get("outdir")
        if not isinstance(outdir, str) or not outdir.strip():
            continue
        candidates.append(outdir.strip())
    return candidates


def _resolve_output_file_path(
    *,
    project_root: Path,
    output_root: Path,
    file_path: str,
) -> Path:
    output_root_resolved = output_root.resolve()
    project_target = safe_workspace(project_root, file_path)
    if project_target.exists():
        if not project_target.resolve().is_relative_to(output_root_resolved):
            raise PermissionError("output file path escapes output root")
        return project_target

    output_target = safe_workspace(output_root, file_path)
    if not output_target.resolve(strict=False).is_relative_to(output_root_resolved):
        raise PermissionError("output file path escapes output root")
    return output_target


def _path_has_outputs(path: Path) -> bool:
    if not path.exists():
        return False
    if path.is_file():
        return True
    try:
        next(path.iterdir())
    except StopIteration:
        return False
    return True


def _build_results_asset_uri(
    *,
    run_id: str,
    default_results_root: Path,
    path: Path,
) -> str | None:
    try:
        rel_path = path.resolve().relative_to(default_results_root)
    except ValueError:
        return None
    logical = str(rel_path)
    return f"asset://results/{run_id}/{logical}" if logical else f"asset://results/{run_id}"
