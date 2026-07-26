from __future__ import annotations

import os
from pathlib import Path

from app.config import BACKEND_ROOT, settings
from app.utils.exceptions import PermissionDeniedError


class FilesystemPolicy:
    def __init__(
        self,
        *,
        allowed_roots: list[Path] | None = None,
        read_roots: list[Path] | None = None,
        write_roots: list[Path] | None = None,
        protected_roots: list[Path] | None = None,
        default_root: Path | None = None,
    ) -> None:
        if allowed_roots is not None and (read_roots is not None or write_roots is not None):
            raise ValueError("allowed_roots cannot be combined with read_roots/write_roots")
        if allowed_roots is not None:
            read_roots = allowed_roots
            write_roots = allowed_roots
        if read_roots is None:
            read_roots = [Path(settings.bioinfoflow_home)]
        if write_roots is None:
            write_roots = list(read_roots)
        self.read_roots = _resolved_unique(read_roots)
        self.write_roots = _resolved_unique(write_roots)
        self.allowed_roots = _resolved_unique([*self.read_roots, *self.write_roots])
        self.protected_roots = _resolved_unique(protected_roots or [], allow_empty=True)
        self.default_root = (
            Path(default_root).expanduser().resolve()
            if default_root is not None
            else self.write_roots[0]
        )

    def require_allowed_dir(self, cwd: str | None) -> Path:
        target = self._resolve_allowed_candidate(
            cwd,
            default=self.default_root,
            must_exist=True,
            roots=self.read_roots,
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
        target = self._resolve_allowed_candidate(
            path,
            must_exist=must_exist,
            roots=self.read_roots,
        )
        if must_exist and not target.exists():
            raise PermissionDeniedError(f"Path is not available: {target}")
        if target.exists() and not allow_directory and target.is_dir():
            raise PermissionDeniedError(f"Expected a file path, got directory: {target}")
        return target

    def require_parent_dir(self, path: str | Path) -> Path:
        target = self._resolve_allowed_candidate(
            path,
            must_exist=False,
            roots=self.write_roots,
        )
        parent = target.parent
        if not parent.exists() or not parent.is_dir():
            raise PermissionDeniedError(f"Parent directory is not available: {parent}")
        self._require_allowed_path(parent, roots=self.write_roots, write=True)
        return target

    def _resolve_allowed_candidate(
        self,
        path: str | Path | None,
        *,
        default: str | Path | None = None,
        must_exist: bool,
        roots: list[Path],
    ) -> Path:
        selected = default if path is None or (isinstance(path, str) and not path.strip()) else path
        raw_selected = _path_text(selected) if selected is not None else ""
        if os.path.isabs(os.path.normpath(raw_selected)):
            preflight = Path(os.path.normpath(raw_selected)).expanduser().resolve(strict=False)
            self._require_not_protected(preflight)
            if roots is self.write_roots and not any(
                _is_relative_to(preflight, root) for root in self.write_roots
            ) and any(_is_relative_to(preflight, root) for root in self.read_roots):
                raise PermissionDeniedError(f"Path is readable but not writable: {preflight}")
        candidate = self._lexically_allowed_candidate(
            selected,
            roots=roots,
        )
        try:
            resolved = candidate.resolve(strict=must_exist)
        except (OSError, RuntimeError, ValueError) as exc:
            raise PermissionDeniedError(f"Path is not available: {candidate}") from exc
        self._require_allowed_path(resolved, roots=roots, write=roots is self.write_roots)
        return resolved

    def _lexically_allowed_candidate(
        self,
        path: str | Path | None,
        *,
        roots: list[Path],
    ) -> Path:
        if path is None:
            raise PermissionDeniedError("Path is required")
        raw_path = _path_text(path)
        if raw_path.startswith("~"):
            raise PermissionDeniedError(f"Home paths are outside allowed roots: {raw_path}")

        normalized = os.path.normpath(raw_path)
        if os.path.isabs(normalized):
            for root in roots:
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
        return self.default_root if normalized == "." else self.default_root / normalized

    def _require_allowed_path(
        self,
        target: Path,
        *,
        roots: list[Path],
        write: bool = False,
    ) -> None:
        self._require_not_protected(target)
        if not any(_is_relative_to(target, root) for root in roots):
            if write and any(_is_relative_to(target, root) for root in self.read_roots):
                raise PermissionDeniedError(f"Path is readable but not writable: {target}")
            raise PermissionDeniedError(
                f"Path is outside allowed roots: {target}"
            )

    def _require_not_protected(self, target: Path) -> None:
        if any(_is_relative_to(target, root) for root in self.protected_roots):
            raise PermissionDeniedError(f"Path is protected: {target}")

        state_root = Path(settings.state_root).expanduser().resolve()
        if _is_relative_to(target, state_root):
            raise PermissionDeniedError(f"Path is protected: {target}")

        docker_socket = _docker_socket_path()
        if docker_socket is not None and target == docker_socket:
            raise PermissionDeniedError(f"Path is protected: {target}")

        repo_root = Path(settings.repo_root).expanduser().resolve()
        data_root = Path(settings.bioinfoflow_home).expanduser().resolve()
        if repo_root == Path("/"):
            backend_root = Path(BACKEND_ROOT).resolve()
            protected_backend_roots = [
                (backend_root / name).resolve()
                for name in ("app", "alembic", "scripts", "tests")
            ]
            if target.parent == backend_root or any(
                _is_relative_to(target, root) for root in protected_backend_roots
            ):
                raise PermissionDeniedError(f"Path is protected: {target}")
        elif _is_relative_to(target, repo_root) and not _is_relative_to(target, data_root):
            raise PermissionDeniedError(f"Path is protected: {target}")


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


def _resolved_unique(roots: list[Path], *, allow_empty: bool = False) -> list[Path]:
    result: list[Path] = []
    for root in roots:
        resolved = Path(root).expanduser().resolve()
        if resolved not in result:
            result.append(resolved)
    if not result and not allow_empty:
        raise ValueError("filesystem policy requires at least one root")
    return result


def _docker_socket_path() -> Path | None:
    value = str(getattr(settings, "docker_socket", "") or "")
    if not value.startswith("unix://"):
        return None
    return Path(value.removeprefix("unix://")).expanduser().resolve()
