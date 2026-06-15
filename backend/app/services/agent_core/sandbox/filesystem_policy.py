from __future__ import annotations

import os
from pathlib import Path

from app.config import settings
from app.utils.exceptions import PermissionDeniedError


class FilesystemPolicy:
    def __init__(self, *, allowed_roots: list[Path] | None = None) -> None:
        roots = allowed_roots or [
            Path(settings.bioinfoflow_home),
            Path(settings.repo_root),
        ]
        self.allowed_roots = [root.expanduser().resolve() for root in roots]

    def require_allowed_dir(self, cwd: str | None) -> Path:
        target = self._resolve_allowed_candidate(
            cwd,
            default=settings.bioinfoflow_home,
            must_exist=True,
        )
        if not target.exists() or not target.is_dir():
            raise PermissionDeniedError(f"Working directory is not available: {target}")
        return target

    def require_allowed_path(
        self,
        path: str | Path,
        *,
        must_exist: bool = True,
        allow_directory: bool = True,
    ) -> Path:
        target = self._resolve_allowed_candidate(path, must_exist=must_exist)
        if must_exist and not target.exists():
            raise PermissionDeniedError(f"Path is not available: {target}")
        if target.exists() and not allow_directory and target.is_dir():
            raise PermissionDeniedError(f"Expected a file path, got directory: {target}")
        return target

    def require_parent_dir(self, path: str | Path) -> Path:
        target = self._resolve_allowed_candidate(path, must_exist=False)
        parent = target.parent
        if not parent.exists() or not parent.is_dir():
            raise PermissionDeniedError(f"Parent directory is not available: {parent}")
        self._require_allowed_path(parent)
        return target

    def _resolve_allowed_candidate(
        self,
        path: str | Path | None,
        *,
        default: str | Path | None = None,
        must_exist: bool,
    ) -> Path:
        candidate = self._lexically_allowed_candidate(
            default if path is None or (isinstance(path, str) and not path.strip()) else path
        )
        try:
            resolved = candidate.resolve(strict=must_exist)
        except (OSError, RuntimeError, ValueError) as exc:
            raise PermissionDeniedError(f"Path is not available: {candidate}") from exc
        self._require_allowed_path(resolved)
        return resolved

    def _lexically_allowed_candidate(self, path: str | Path | None) -> Path:
        if path is None:
            raise PermissionDeniedError("Path is required")
        raw_path = _path_text(path)
        if raw_path.startswith("~"):
            raise PermissionDeniedError(f"Home paths are outside allowed roots: {raw_path}")

        normalized = os.path.normpath(raw_path)
        if os.path.isabs(normalized):
            for root in self.allowed_roots:
                root_text = os.fspath(root)
                try:
                    if os.path.commonpath([normalized, root_text]) != root_text:
                        continue
                except ValueError:
                    continue
                relative = os.path.relpath(normalized, root_text)
                return root if relative == "." else root / relative
            raise PermissionDeniedError(f"Path is outside allowed roots: {normalized}")

        if os.pardir in normalized.split(os.sep):
            raise PermissionDeniedError(f"Path is outside allowed roots: {normalized}")
        return self.allowed_roots[0] if normalized == "." else self.allowed_roots[0] / normalized

    def _require_allowed_path(self, target: Path) -> None:
        if not any(_is_relative_to(target, root) for root in self.allowed_roots):
            raise PermissionDeniedError(
                f"Path is outside allowed roots: {target}"
            )


def _path_text(path: str | Path) -> str:
    raw_path = os.fspath(path)
    if not isinstance(raw_path, str):
        raise PermissionDeniedError("Path must be text")
    return raw_path


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False
