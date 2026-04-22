from __future__ import annotations

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
