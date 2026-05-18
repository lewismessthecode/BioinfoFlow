from __future__ import annotations

import os
from pathlib import Path, PurePosixPath, PureWindowsPath

from app.config import settings


def repo_root() -> Path:
    return Path(settings.repo_root).expanduser().resolve()


def resolve_repo_path(path: str | Path) -> Path:
    raw = str(path or "/").strip() or "/"
    if "\x00" in raw:
        raise PermissionError("invalid path")

    expanded = os.path.normpath(os.path.expanduser(raw))
    posix_path = expanded.replace("\\", "/")
    if ".." in PurePosixPath(posix_path).parts:
        raise PermissionError("invalid path")
    if PurePosixPath(expanded).is_absolute() or PureWindowsPath(expanded).is_absolute():
        return Path(os.path.realpath(expanded))
    return (repo_root() / expanded).resolve()


def normalize_repo_path(path: str | Path) -> str:
    return str(resolve_repo_path(path))
