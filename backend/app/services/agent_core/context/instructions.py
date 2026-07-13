from __future__ import annotations

import posixpath
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.services.agent_core.execution_target import execution_target_from_session
from app.services.agent_core.tools.remote import SessionMetadataRemoteConnectionResolver
from app.services.remote_execution import RemoteExecutor, SshRemoteExecutor


INSTRUCTION_FILENAMES: tuple[str, ...] = (
    "AGENTS.override.md",
    "AGENTS.md",
    "CLAUDE.md",
    "GEMINI.md",
)


@dataclass(frozen=True)
class ProjectInstructionFile:
    source: str
    content: str
    truncated: bool = False
    limit_bytes: int | None = None


class RemoteProjectInstructionReader(Protocol):
    async def read_first_existing(
        self,
        *,
        agent_session,
        connection_id: str,
        directory: str,
        filenames: Sequence[str],
        max_bytes: int,
        remote_root: str,
    ) -> ProjectInstructionFile | None:
        """Read the first prioritized instruction file from a remote directory."""


class SshProjectInstructionReader:
    def __init__(
        self,
        db: AsyncSession,
        *,
        executor: RemoteExecutor | None = None,
    ) -> None:
        self.db = db
        self.executor = executor or SshRemoteExecutor()

    async def read_first_existing(
        self,
        *,
        agent_session,
        connection_id: str,
        directory: str,
        filenames: Sequence[str],
        max_bytes: int,
        remote_root: str,
    ) -> ProjectInstructionFile | None:
        resolver = SessionMetadataRemoteConnectionResolver(self.db)
        connection = await resolver.get(
            connection_id,
            workspace_id=str(agent_session.workspace_id),
            user_id=str(agent_session.user_id),
            session_id=str(getattr(agent_session, "id", "")) or None,
        )
        result = await self.executor.run(
            connection,
            _remote_read_first_existing_command(
                directory=directory,
                filenames=filenames,
                max_bytes=max_bytes,
                remote_root=remote_root,
            ),
            timeout_seconds=10,
            output_limit=max_bytes + 4096,
        )
        if result.exit_code == 44:
            return None
        if result.exit_code != 0:
            raise RuntimeError("remote instruction read failed")
        source, separator, content = result.stdout.partition("\n")
        if not separator or not source:
            return None
        content_bytes = content.encode("utf-8", errors="replace")
        truncated = result.stdout_truncated or len(content_bytes) > max_bytes
        return ProjectInstructionFile(
            source=f"ssh://{connection.id}{source}",
            content=_truncate_text_to_bytes(content, max_bytes),
            truncated=truncated,
            limit_bytes=max_bytes,
        )


class ProjectInstructionResolver:
    def __init__(
        self,
        db: AsyncSession | None = None,
        *,
        max_bytes: int | None = None,
        remote_reader: RemoteProjectInstructionReader | None = None,
    ) -> None:
        self.max_bytes = int(max_bytes or settings.agent_project_instructions_max_bytes)
        self.remote_reader = remote_reader or (
            SshProjectInstructionReader(db) if db is not None else None
        )

    async def resolve(
        self,
        agent_session,
        *,
        turn=None,
        execution_target: dict[str, str] | None = None,
    ) -> str | None:
        if self.max_bytes <= 0:
            return None
        try:
            target = _target_metadata(
                agent_session,
                turn,
                execution_target=execution_target,
            )
            if _is_remote_target(target):
                return await self._resolve_remote(agent_session, target)
            return self._resolve_local(target)
        except Exception as exc:  # noqa: BLE001 - context assembly must not break a turn
            return _unavailable_marker(f"{exc.__class__.__name__}")

    def _resolve_local(self, target: dict[str, Any]) -> str | None:
        root = Path(settings.repo_root).expanduser().resolve(strict=False)
        current = _local_current(root, _first_string(target, _CWD_KEYS))
        files: list[ProjectInstructionFile] = []
        used_bytes = 0
        for directory in _local_directories(root, current):
            remaining = self.max_bytes - used_bytes
            if remaining <= 0:
                break
            instruction = _read_local_instruction(directory, remaining, root=root)
            if instruction is None:
                continue
            files.append(instruction)
            used_bytes += _content_size(instruction.content)
            if instruction.truncated:
                break
        return _render(files)

    async def _resolve_remote(self, agent_session, target: dict[str, Any]) -> str | None:
        snapshot = _first_string(
            target,
            (
                "project_instruction_snapshot",
                "project_instructions_snapshot",
                "project_instructions",
            ),
        )
        if snapshot:
            return _render(
                [
                    ProjectInstructionFile(
                        source="project instruction snapshot",
                        content=_truncate_text_to_bytes(snapshot, self.max_bytes),
                        truncated=_content_size(snapshot) > self.max_bytes,
                        limit_bytes=self.max_bytes,
                    )
                ]
            )

        remote_root = _normalize_remote_root(
            _first_string(target, ("remote_project_root", "remote_root_path"))
        )
        connection_id = _remote_connection_id(target)
        if not remote_root or not connection_id:
            return _unavailable_marker("remote target metadata is incomplete")
        if self.remote_reader is None:
            return _unavailable_marker("remote instruction reader is not configured")

        current = _remote_current(remote_root, _first_string(target, _CWD_KEYS))
        files: list[ProjectInstructionFile] = []
        diagnostics: list[str] = []
        used_bytes = 0
        for directory in _remote_directories(remote_root, current):
            remaining = self.max_bytes - used_bytes
            if remaining <= 0:
                break
            try:
                instruction = await self.remote_reader.read_first_existing(
                    agent_session=agent_session,
                    connection_id=connection_id,
                    directory=directory,
                    filenames=INSTRUCTION_FILENAMES,
                    max_bytes=remaining,
                    remote_root=remote_root,
                )
            except Exception:  # noqa: BLE001 - remote reads must never break a turn
                diagnostics.append(
                    f"Skipped {directory}: remote instruction files could not be read."
                )
                continue
            if instruction is None:
                continue
            files.append(instruction)
            used_bytes += _content_size(instruction.content)
            if instruction.truncated:
                break
        if not files and diagnostics:
            return _unavailable_marker("remote instruction files could not be read")
        return _render(files, diagnostics=diagnostics)


_CWD_KEYS = (
    "cwd",
    "working_directory",
    "current_directory",
    "project_cwd",
    "remote_cwd",
)


def _target_metadata(
    agent_session,
    turn=None,
    *,
    execution_target: dict[str, str] | None = None,
) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for policy in _policy_sources(agent_session, turn):
        merged.update(policy)
        policy_target = policy.get("execution_target")
        if isinstance(policy_target, dict):
            merged.update(policy_target)
    current_target = execution_target or execution_target_from_session(agent_session)
    project_connection_id = _first_string(merged, ("remote_connection_id",))
    target_connection_id = _first_string(current_target, ("connection_id",))
    if (
        current_target.get("type") == "remote_ssh"
        and project_connection_id
        and target_connection_id
        and project_connection_id != target_connection_id
    ):
        for key in ("remote_project_id", "remote_project_root", "remote_root_path"):
            merged.pop(key, None)
    merged["execution_target"] = dict(current_target)
    merged.update(current_target)
    return merged


def _policy_sources(agent_session, turn=None):
    snapshot = getattr(turn, "model_profile_snapshot", None) if turn is not None else None
    metadata = snapshot.get("metadata") if isinstance(snapshot, dict) else None
    if isinstance(metadata, dict):
        yield metadata
    for policy in (
        getattr(agent_session, "toolset_policy", None),
        getattr(agent_session, "context_policy", None),
        getattr(agent_session, "session_metadata", None),
    ):
        if isinstance(policy, dict):
            yield policy


def _is_remote_target(target: dict[str, Any]) -> bool:
    kind = _first_string(target, ("kind", "type", "target_type", "mode")).casefold()
    return kind in {"remote", "remote_ssh", "ssh"}


def _first_string(source: dict[str, Any], keys: Sequence[str]) -> str:
    for key in keys:
        value = source.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _remote_connection_id(target: dict[str, Any]) -> str:
    direct = _first_string(
        target,
        (
            "connection_id",
            "remote_connection_id",
            "selected_remote_connection_id",
            "current_remote_connection_id",
        ),
    )
    if direct:
        return direct
    for key in ("remote_connection", "selected_remote_connection", "remote"):
        value = target.get(key)
        if isinstance(value, dict):
            nested = value.get("id") or value.get("connection_id")
            if isinstance(nested, str) and nested.strip():
                return nested.strip()
    return ""


def _local_current(root: Path, raw_current: str) -> Path:
    if raw_current:
        candidate = Path(raw_current).expanduser()
        if not candidate.is_absolute():
            candidate = root / candidate
        candidate = candidate.resolve(strict=False)
        if _is_relative_to(candidate, root):
            return candidate.parent if candidate.exists() and candidate.is_file() else candidate
    return root


def _local_directories(root: Path, current: Path) -> list[Path]:
    if not _is_relative_to(current, root):
        return [root]
    relative = current.relative_to(root)
    directories = [root]
    cursor = root
    for part in relative.parts:
        cursor = cursor / part
        directories.append(cursor)
    return directories


def _read_local_instruction(
    directory: Path,
    max_bytes: int,
    *,
    root: Path,
) -> ProjectInstructionFile | None:
    for filename in INSTRUCTION_FILENAMES:
        path = directory / filename
        try:
            resolved = path.resolve(strict=True)
        except OSError:
            continue
        if not resolved.is_file() or not _is_relative_to(resolved, root):
            continue
        data = resolved.read_bytes()[: max_bytes + 1]
        truncated = len(data) > max_bytes
        content = data[:max_bytes].decode("utf-8", errors="replace")
        return ProjectInstructionFile(
            source=str(path),
            content=content,
            truncated=truncated,
            limit_bytes=max_bytes,
        )
    return None


def _normalize_remote_root(raw_root: str) -> str:
    if not raw_root:
        return ""
    normalized = posixpath.normpath(raw_root.replace("\\", "/"))
    if not normalized.startswith("/"):
        return ""
    return normalized


def _remote_current(remote_root: str, raw_current: str) -> str:
    if not raw_current:
        return remote_root
    normalized = raw_current.replace("\\", "/")
    if normalized.startswith("/"):
        candidate = posixpath.normpath(normalized)
    else:
        candidate = posixpath.normpath(posixpath.join(remote_root, normalized))
    root_prefix = remote_root.rstrip("/")
    if candidate == remote_root or candidate.startswith(f"{root_prefix}/"):
        return candidate
    return remote_root


def _remote_directories(remote_root: str, current: str) -> list[str]:
    if current == remote_root:
        return [remote_root]
    root_prefix = remote_root.rstrip("/")
    if not current.startswith(f"{root_prefix}/"):
        return [remote_root]
    relative = posixpath.relpath(current, remote_root)
    directories = [remote_root]
    cursor = remote_root
    for part in relative.split("/"):
        if part in {"", "."}:
            continue
        cursor = posixpath.join(cursor, part)
        directories.append(cursor)
    return directories


def _remote_read_first_existing_command(
    *,
    directory: str,
    filenames: Sequence[str],
    max_bytes: int,
    remote_root: str,
) -> str:
    quoted_root = shlex.quote(remote_root)
    quoted_directory = shlex.quote(directory)
    quoted_names = " ".join(shlex.quote(filename) for filename in filenames)
    read_bytes = max_bytes + 1
    return (
        f"root={quoted_root}; dir={quoted_directory}; "
        'root_real=$(realpath -- "$root") || exit 23; '
        'dir_real=$(realpath -- "$dir") || exit 23; '
        'case "$dir_real" in "$root_real"|"$root_real"/*) ;; '
        "*) printf '%s\\n' 'remote path is outside the remote project' >&2; exit 23;; "
        "esac; "
        f"for name in {quoted_names}; do "
        'path="$dir/$name"; '
        'if [ -f "$path" ]; then '
        'file_real=$(realpath -- "$path") || continue; '
        'case "$file_real" in "$root_real"|"$root_real"/*) ;; *) continue;; esac; '
        'printf "%s\\n" "$path"; '
        f'head -c {read_bytes} -- "$path"; '
        "exit 0; "
        "fi; "
        "done; "
        "exit 44"
    )


def _render(
    files: list[ProjectInstructionFile],
    *,
    diagnostics: list[str] | None = None,
) -> str | None:
    if not files:
        return None
    lines = ["## Project instructions"]
    for file in files:
        lines.append("")
        lines.append(f"### {file.source}")
        lines.append(file.content)
        if file.truncated:
            limit = file.limit_bytes or settings.agent_project_instructions_max_bytes
            lines.append(f"[Truncated to {limit} bytes.]")
    if diagnostics:
        lines.append("")
        lines.append("## Project instruction diagnostics")
        lines.extend(f"- {diagnostic}" for diagnostic in diagnostics)
    return "\n".join(lines)


def _unavailable_marker(reason: str) -> str:
    return f"## Project instructions\nProject instructions unavailable: {reason}."


def _truncate_text_to_bytes(value: str, max_bytes: int) -> str:
    data = value.encode("utf-8", errors="replace")
    if len(data) <= max_bytes:
        return value
    return data[:max_bytes].decode("utf-8", errors="replace")


def _content_size(value: str) -> int:
    return len(value.encode("utf-8", errors="replace"))


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True
