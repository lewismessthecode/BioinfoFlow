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
        if not any(_is_relative_to(target, root) for root in self.allowed_roots):
            raise PermissionDeniedError(
                f"Working directory is outside allowed roots: {target}"
            )
        return target


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False
