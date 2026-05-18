from __future__ import annotations

import os
import tempfile
from pathlib import Path

from app.config import settings


def repo_root() -> Path:
    return Path(settings.repo_root).expanduser().resolve()


def resolve_repo_path(path: str | Path) -> Path:
    candidate = Path(path).expanduser()
    if candidate.is_absolute():
        return candidate.resolve()
    return (repo_root() / candidate).resolve()


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
    raw_path = os.path.expanduser(os.fspath(path))
    if os.path.isabs(raw_path):
        resolved = Path(os.path.realpath(raw_path))
    else:
        resolved = Path(os.path.realpath(os.path.join(str(repo_root()), raw_path)))

    for root in allowed_local_path_roots():
        try:
            common = os.path.commonpath([str(root), str(resolved)])
        except ValueError:
            continue
        if common == str(root):
            return resolved
    raise ValueError("local path is not allowed")
