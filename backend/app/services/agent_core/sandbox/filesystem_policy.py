from __future__ import annotations

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
        target = Path(cwd or settings.bioinfoflow_home).expanduser().resolve()
        if not target.exists() or not target.is_dir():
            raise PermissionDeniedError(f"Working directory is not available: {target}")
        self._require_allowed_path(target)
        return target

    def require_allowed_path(
        self,
        path: str | Path,
        *,
        must_exist: bool = True,
        allow_directory: bool = True,
    ) -> Path:
        target = Path(path).expanduser().resolve()
        if must_exist and not target.exists():
            raise PermissionDeniedError(f"Path is not available: {target}")
        if target.exists() and not allow_directory and target.is_dir():
            raise PermissionDeniedError(f"Expected a file path, got directory: {target}")
        self._require_allowed_path(target)
        return target

    def require_parent_dir(self, path: str | Path) -> Path:
        target = Path(path).expanduser().resolve()
        parent = target.parent
        if not parent.exists() or not parent.is_dir():
            raise PermissionDeniedError(f"Parent directory is not available: {parent}")
        self._require_allowed_path(parent)
        return target

    def _require_allowed_path(self, target: Path) -> None:
        if not any(_is_relative_to(target, root) for root in self.allowed_roots):
            raise PermissionDeniedError(
                f"Path is outside allowed roots: {target}"
            )


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False
