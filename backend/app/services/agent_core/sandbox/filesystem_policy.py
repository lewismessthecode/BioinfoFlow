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
        candidate = _normalize_path(Path(path).expanduser())
        if candidate.is_absolute():
            for root in self.allowed_roots:
                if _is_relative_to(candidate, root):
                    return root / candidate.relative_to(root)
            raise PermissionDeniedError(f"Path is outside allowed roots: {candidate}")

        if ".." in candidate.parts:
            raise PermissionDeniedError(f"Path is outside allowed roots: {candidate}")
        return self.allowed_roots[0] / candidate

    def _require_allowed_path(self, target: Path) -> None:
        if not any(_is_relative_to(target, root) for root in self.allowed_roots):
            raise PermissionDeniedError(
                f"Path is outside allowed roots: {target}"
            )


def _normalize_path(path: Path) -> Path:
    return Path(os.path.normpath(os.fspath(path)))


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False
