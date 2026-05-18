from __future__ import annotations

import os
import tempfile
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


def allowed_local_path_roots() -> tuple[Path, ...]:
    raw_roots = [
        repo_root(),
        Path(settings.bioinfoflow_home).expanduser().resolve(),
        Path.home().resolve(),
        Path(tempfile.gettempdir()).resolve(),
    ]
    if settings.bioinfoflow_home_host:
        raw_roots.append(Path(settings.bioinfoflow_home_host).expanduser().resolve())
    roots: list[Path] = []
    for root in raw_roots:
        if root not in roots:
            roots.append(root)
    return tuple(roots)


def resolve_allowed_local_path(path: str | Path) -> Path:
    try:
        resolved = resolve_repo_path(path)
    except PermissionError as exc:
        raise ValueError("local path is not allowed") from exc

    for root in allowed_local_path_roots():
        try:
            common = os.path.commonpath([str(root), str(resolved)])
        except ValueError:
            continue
        if common == str(root):
            return resolved
    raise ValueError("local path is not allowed")
