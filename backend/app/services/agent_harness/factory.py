from __future__ import annotations

import asyncio
import json
from pathlib import Path, PurePosixPath
import shlex
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.path_layout import agent_user_workspace_root, project_home
from app.repositories.llm_repo import (
    LlmModelProfileRepository,
    LlmModelRepository,
    LlmProviderCredentialRepository,
    LlmProviderRepository,
)
from app.repositories.project_repo import ProjectRepository
from app.repositories.remote_connection_repo import RemoteConnectionRepository
from app.repositories.agent_harness_repo import RunFence
from app.services.agent_harness.model_resolver import AgentModelResolver
from app.services.agent_harness.assets import AgentHarnessArtifactService
from app.services.agent_harness.api_endpoint import workspace_api_url
from app.services.agent_harness.context import bounded_skill_metadata_for_prompt
from app.services.agent_harness.sandbox import SandboxRunner
from app.services.agent_harness.harness import AgentHarness
from app.services.agent_harness.model_target import private_model_snapshot
from app.services.agent_harness.environment_catalog import EnvironmentCatalog
from app.services.agent_harness.environment_scope import (
    EnvironmentDescriptor,
    ResolvedEnvironmentScope,
)
from app.services.agent_harness.routed_workspace_runtime import RoutedWorkspaceRuntime
from app.services.agent_harness.workspace_router import WorkspaceRouter
from app.services.agent_harness.workspace_runtime import (
    LocalWorkspaceBackend,
    RemoteWorkspaceBackend,
    WorkspaceRuntime,
)
from app.services.authorization_service import AuthorizationService
from app.services.remote_connection_service import RemoteConnectionService
from app.services.remote_execution import (
    RemoteConnectionConfig,
    RemoteExecutor,
    SshRemoteExecutor,
)
from app.utils.authorization import can_access_project
from app.utils.exceptions import AgentModelRequiredError, NotFoundError


_MAX_REMOTE_SKILLS = 200
_MAX_REMOTE_SKILL_METADATA_BYTES = 16 * 1024
_MAX_REMOTE_SKILL_SCAN_ENTRIES = _MAX_REMOTE_SKILLS * 16
_MAX_REMOTE_SKILL_SCAN_DIRECTORIES = _MAX_REMOTE_SKILLS * 4
_MAX_REMOTE_SKILL_SCAN_DEPTH = 32


async def open_session_request_workspace(
    db: AsyncSession,
    *,
    project_id: str | None,
    workspace_id: str,
    user_id: str,
    remote_executor: RemoteExecutor | None = None,
) -> dict[str, Any]:
    if project_id is None:
        root = agent_user_workspace_root(workspace_id, user_id).resolve()
        root.mkdir(parents=True, exist_ok=True)
        return {
            "api_url": _workspace_api_url("local"),
            "root": str(root),
            "runtime": "local",
        }
    project = await ProjectRepository(db).get(project_id)
    if (
        project is None
        or str(project.workspace_id) != workspace_id
        or not can_access_project(
            project,
            user_id=user_id,
            workspace_id=workspace_id,
        )
    ):
        raise NotFoundError(f"Project not found: {project_id}")
    if project.storage_mode != "remote":
        return {
            "api_url": _workspace_api_url("local"),
            "root": str(project_home(project)),
            "runtime": "local",
        }

    connection_id = str(project.remote_connection_id or "")
    remote_root = str(project.remote_root_path or "")
    if not connection_id or not remote_root:
        raise ValueError("remote project is missing its connection or root path")
    connection = await RemoteConnectionRepository(db).get_for_workspace(
        connection_id,
        workspace_id=workspace_id,
    )
    if connection is None:
        raise NotFoundError(f"Remote connection not found: {connection_id}")
    api_url = _workspace_api_url("remote_ssh")
    resolved_connection = await RemoteConnectionService(db).resolve_connection_config(
        connection
    )
    project_instructions, remote_skills = await _remote_project_context(
        resolved_connection,
        remote_root,
        executor=remote_executor or SshRemoteExecutor(),
    )
    snapshot = {
        "api_url": api_url,
        "runtime": "remote_ssh",
        "root": remote_root,
        "remote_connection": {
            "id": str(connection.id),
            "name": connection.name,
            "host": connection.host,
            "port": connection.port,
            "username": connection.username,
        },
    }
    if project_instructions:
        snapshot["project_instructions"] = list(project_instructions)
    if remote_skills:
        snapshot["skills"] = list(remote_skills)
    return snapshot


async def resolve_model_snapshot(
    db: AsyncSession,
    *,
    workspace_id: str,
    user_id: str,
    selection: dict[str, str] | None,
) -> dict[str, Any]:
    resolver = _model_resolver(db)
    resolved = (
        await resolver.catalog_selection(
            selection,
            source="session",
            workspace_id=workspace_id,
            user_id=user_id,
        )
        if selection
        else await resolver.catalog_default_selection(
            workspace_id=workspace_id,
            user_id=user_id,
        )
    )
    if resolved is None:
        raise AgentModelRequiredError()
    return private_model_snapshot(resolved)


def harness_for_database(db: AsyncSession, **runtime: Any) -> AgentHarness:
    resolver = _model_resolver(db)

    async def model_runtime_resolver(session) -> dict[str, Any]:
        resolved = await resolver.resolve_snapshot(
            session.model_snapshot,
            workspace_id=str(session.workspace_id),
            user_id=session.user_id,
        )
        if resolved is None:
            raise ValueError("The Agent session model is no longer available")
        return resolved

    def workspace_factory(
        session,
        run_id: str,
        fence: RunFence | None,
    ) -> RoutedWorkspaceRuntime:
        if fence is None:
            raise ValueError("Agent workspace requires a claimed Run fence")
        write_artifact = AgentHarnessArtifactService(db).writer(
            session_id=str(session.id),
            run_id=run_id,
            fence=fence,
        )
        return routed_workspace_runtime_for_session(
            db,
            session,
            artifact_writer=write_artifact,
        )

    return AgentHarness.for_database(
        db,
        workspace_factory=workspace_factory,
        model_runtime_resolver=model_runtime_resolver,
        **runtime,
    )


def _model_resolver(db: AsyncSession) -> AgentModelResolver:
    return AgentModelResolver(
        llm_models=LlmModelRepository(db),
        llm_profiles=LlmModelProfileRepository(db),
        llm_providers=LlmProviderRepository(db),
        llm_credentials=LlmProviderCredentialRepository(db),
        authorization=AuthorizationService(db),
    )


def workspace_runtime_for_session(
    db: AsyncSession,
    session: Any,
    *,
    remote_executor: RemoteExecutor | None = None,
    artifact_writer=None,
) -> WorkspaceRuntime:
    snapshot = session.workspace_snapshot or {}
    runtime = str(snapshot.get("runtime") or "local")
    environment = {
        "BIOFLOW_API_URL": _workspace_api_url(runtime),
        "BIOFLOW_PROJECT": str(session.project_id or ""),
        "BIOFLOW_OUTPUT": "json",
    }
    if runtime == "local":
        raw_root = snapshot.get("root")
        if not isinstance(raw_root, str) or not raw_root.strip():
            raise ValueError("local project workspace is missing its root")
        root = Path(raw_root).expanduser().resolve()
        skill_read_roots = _local_skill_read_roots(session)
        backend = LocalWorkspaceBackend(
            working_directory=root,
            read_roots=(root, *skill_read_roots),
            write_roots=(root,),
            protected_roots=(),
            sandbox_runner=SandboxRunner.from_settings(),
            artifact_writer=artifact_writer,
        )
    elif runtime == "remote_ssh":
        root = str(snapshot.get("root") or "")
        connection = _remote_connection_snapshot(snapshot)
        backend = RemoteWorkspaceBackend(
            connection=connection,
            executor=_DatabaseRemoteExecutor(
                db,
                workspace_id=str(session.workspace_id),
                connection_id=connection.id,
                executor=remote_executor or SshRemoteExecutor(),
            ),
            working_directory=root,
            read_roots=(root,),
            write_roots=(root,),
            artifact_writer=artifact_writer,
        )
    else:
        raise ValueError(f"unknown workspace runtime: {runtime}")
    return WorkspaceRuntime(
        backend,
        permission_mode=session.permission_mode,
        workspace_access=session.workspace_access,
        environment=environment,
    )


def routed_workspace_runtime_for_session(
    db: AsyncSession,
    session: Any,
    *,
    remote_executor: RemoteExecutor | None = None,
    artifact_writer=None,
) -> RoutedWorkspaceRuntime:
    catalog = EnvironmentCatalog(RemoteConnectionRepository(db))
    scope_data = getattr(session, "environment_scope", None) or {"mode": "auto"}
    mode = "manual" if scope_data.get("mode") == "manual" else "auto"
    selected_ids = tuple(
        str(item)
        for item in (scope_data.get("environment_ids") or ())
        if isinstance(item, str) and item
    )
    scope_environments = {
        environment_id: EnvironmentDescriptor(
            environment_id,
            "local" if environment_id == "local" else "ssh",
            "Local" if environment_id == "local" else environment_id,
        )
        for environment_id in (selected_ids or ("local",))
    }
    resolved_scope = ResolvedEnvironmentScope(
        mode=mode,
        environments=scope_environments,
    )
    local_runtime = _local_workspace_runtime_for_session(
        session,
        artifact_writer=artifact_writer,
    )

    async def authorize(environment_id: str) -> bool:
        return await catalog.is_authorized(
            environment_id,
            workspace_id=str(session.workspace_id),
        )

    async def resolve(environment_id: str) -> WorkspaceRuntime | None:
        if environment_id == "local":
            return local_runtime
        return await _remote_environment_runtime(
            db,
            session,
            environment_id=environment_id,
            remote_executor=remote_executor,
            artifact_writer=artifact_writer,
        )

    async def visible_environments() -> tuple[EnvironmentDescriptor, ...]:
        environments = await catalog.list_authorized(
            workspace_id=str(session.workspace_id)
        )
        selected = set(selected_ids)
        if not selected:
            selected = {"local"}
        return tuple(
            environment
            for environment in environments
            if environment.environment_id in selected
        )

    return RoutedWorkspaceRuntime(
        router=WorkspaceRouter(
            scope=resolved_scope,
            authorize=authorize,
            resolve=resolve,
        ),
        control_runtime=local_runtime,
        environments=visible_environments,
    )


def _local_workspace_runtime_for_session(
    session: Any,
    *,
    artifact_writer=None,
) -> WorkspaceRuntime:
    snapshot = session.workspace_snapshot or {}
    raw_root = snapshot.get("root") if snapshot.get("runtime") == "local" else None
    root = (
        Path(raw_root).expanduser().resolve()
        if isinstance(raw_root, str) and raw_root.strip()
        else agent_user_workspace_root(
            str(session.workspace_id),
            str(session.user_id),
        ).resolve()
    )
    root.mkdir(parents=True, exist_ok=True)
    backend = LocalWorkspaceBackend(
        working_directory=root,
        read_roots=(root, *_local_skill_read_roots(session)),
        write_roots=(root,),
        protected_roots=(),
        sandbox_runner=SandboxRunner.from_settings(),
        artifact_writer=artifact_writer,
    )
    return WorkspaceRuntime(
        backend,
        permission_mode=session.permission_mode,
        workspace_access=session.workspace_access,
        environment={
            "BIOFLOW_API_URL": _workspace_api_url("local"),
            "BIOFLOW_PROJECT": str(session.project_id or ""),
            "BIOFLOW_OUTPUT": "json",
        },
    )


async def _remote_environment_runtime(
    db: AsyncSession,
    session: Any,
    *,
    environment_id: str,
    remote_executor: RemoteExecutor | None,
    artifact_writer=None,
) -> WorkspaceRuntime | None:
    service = RemoteConnectionService(db)
    model = await service.get_connection(
        environment_id,
        workspace_id=str(session.workspace_id),
    )
    if model is None:
        return None
    connection = await service.resolve_connection_config(model)
    executor = remote_executor or SshRemoteExecutor()
    snapshot = session.workspace_snapshot or {}
    raw_connection = snapshot.get("remote_connection")
    if (
        snapshot.get("runtime") == "remote_ssh"
        and isinstance(raw_connection, dict)
        and str(raw_connection.get("id") or "") == environment_id
    ):
        root = str(snapshot.get("root") or "")
    else:
        try:
            result = await executor.run(
                connection,
                "pwd -P",
                timeout_seconds=10,
                output_limit=4096,
            )
        except Exception:  # noqa: BLE001 - unavailable is normalized by the router
            return None
        root = result.stdout.strip() if result.exit_code == 0 else ""
    if not root.startswith("/") or "\n" in root:
        return None
    backend = RemoteWorkspaceBackend(
        connection=connection,
        executor=_DatabaseRemoteExecutor(
            db,
            workspace_id=str(session.workspace_id),
            connection_id=environment_id,
            executor=executor,
        ),
        working_directory=root,
        read_roots=(root,),
        write_roots=(root,),
        artifact_writer=artifact_writer,
    )
    return WorkspaceRuntime(
        backend,
        permission_mode=session.permission_mode,
        workspace_access=session.workspace_access,
        environment={
            "BIOFLOW_API_URL": _workspace_api_url("remote_ssh"),
            "BIOFLOW_PROJECT": str(session.project_id or ""),
            "BIOFLOW_OUTPUT": "json",
        },
    )


def _workspace_api_url(runtime: str) -> str:
    return workspace_api_url(
        runtime,
        configured_url=settings.bioinfoflow_public_api_base_url,
    )


async def _remote_project_context(
    connection: RemoteConnectionConfig,
    remote_root: str,
    *,
    executor: RemoteExecutor,
) -> tuple[tuple[str, ...], tuple[dict[str, str], ...]]:
    command = shlex.join(
        (
            "python3",
            "-c",
            _REMOTE_PROJECT_CONTEXT_SCRIPT,
            remote_root,
            str(settings.agent_project_instructions_max_bytes),
            str(_MAX_REMOTE_SKILLS),
            str(_MAX_REMOTE_SKILL_METADATA_BYTES),
            str(_MAX_REMOTE_SKILL_SCAN_ENTRIES),
            str(_MAX_REMOTE_SKILL_SCAN_DIRECTORIES),
            str(_MAX_REMOTE_SKILL_SCAN_DEPTH),
        )
    )
    result = await executor.run(
        connection,
        command,
        timeout_seconds=30,
        output_limit=(
            settings.agent_project_instructions_max_bytes
            + (_MAX_REMOTE_SKILLS * _MAX_REMOTE_SKILL_METADATA_BYTES)
            + (64 * 1024)
        ),
    )
    if result.exit_code != 0 or result.timed_out or result.truncated:
        raise ValueError(
            result.stderr.strip()
            or "could not freeze remote project context for the Agent session"
        )
    try:
        payload = json.loads(result.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise ValueError("remote project context returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError("remote project context returned invalid output")
    path = payload.get("path")
    content = payload.get("content")
    instructions: tuple[str, ...] = ()
    if isinstance(path, str) and path and isinstance(content, str):
        content = content.strip()
        if content:
            instructions = (f"Instructions from {path}:\n\n{content}",)
    skills = _validated_remote_skills(payload.get("skills", []), remote_root)
    return instructions, skills


def _validated_remote_skills(
    value: Any, remote_root: str
) -> tuple[dict[str, str], ...]:
    if not isinstance(value, list):
        raise ValueError("remote project skills returned invalid output")
    if len(value) > _MAX_REMOTE_SKILLS:
        raise ValueError("remote project skills exceeded the configured limit")
    root = PurePosixPath(remote_root)
    if not root.is_absolute() or ".." in root.parts:
        raise ValueError("remote project root is invalid")
    discovered: dict[str, dict[str, str]] = {}
    for raw in value:
        if not isinstance(raw, dict):
            raise ValueError("remote project skills returned invalid output")
        name = raw.get("name")
        description = raw.get("description")
        raw_path = raw.get("path")
        if not all(
            isinstance(item, str) and item.strip()
            for item in (name, description, raw_path)
        ):
            raise ValueError("remote project skills returned invalid output")
        assert isinstance(name, str)
        assert isinstance(description, str)
        assert isinstance(raw_path, str)
        if (
            len(name.encode("utf-8"))
            + len(description.encode("utf-8"))
            + len(raw_path.encode("utf-8"))
            > _MAX_REMOTE_SKILL_METADATA_BYTES
        ):
            raise ValueError("remote project skill metadata exceeded the limit")
        path = PurePosixPath(raw_path)
        try:
            relative = path.relative_to(root)
        except ValueError as exc:
            raise ValueError("remote project skill escaped the project root") from exc
        if (
            not path.is_absolute()
            or ".." in path.parts
            or path.name != "SKILL.md"
            or relative.parts[:2] not in {(".agents", "skills"), (".codex", "skills")}
        ):
            raise ValueError("remote project skill path is invalid")
        discovered.setdefault(
            name.strip(),
            {
                "name": name.strip(),
                "description": description.strip(),
                "path": str(path),
            },
        )
    return tuple(
        dict(skill) for skill in bounded_skill_metadata_for_prompt(discovered.values())
    )


_REMOTE_PROJECT_CONTEXT_SCRIPT = r"""
import json, os, pathlib, stat, sys

DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW
FILE_FLAGS = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW

def open_directory(path):
    if not path.is_absolute() or ".." in path.parts:
        raise OSError("directory path is not absolute and normalized")
    descriptor = os.open("/", DIRECTORY_FLAGS)
    try:
        for part in path.parts[1:]:
            next_descriptor = os.open(
                part,
                DIRECTORY_FLAGS,
                dir_fd=descriptor,
            )
            os.close(descriptor)
            descriptor = next_descriptor
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise

def read_bounded_file(path, max_bytes):
    directory_descriptor = None
    descriptor = None
    try:
        directory_descriptor = open_directory(path.parent)
        descriptor = os.open(
            path.name,
            FILE_FLAGS,
            dir_fd=directory_descriptor,
        )
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            return None
        chunks = []
        remaining = max_bytes + 1
        while remaining > 0:
            chunk = os.read(descriptor, min(remaining, 64 * 1024))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)
    except OSError:
        return None
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if directory_descriptor is not None:
            os.close(directory_descriptor)

def iter_skill_files(root, scan_budget, max_depth):
    pending = [(root, 0)]
    while (
        pending
        and scan_budget["entries"] > 0
        and scan_budget["directories"] > 0
    ):
        directory, depth = pending.pop()
        directory_descriptor = None
        entries = []
        scan_budget["directories"] -= 1
        try:
            directory_descriptor = open_directory(directory)
            with os.scandir(directory_descriptor) as stream:
                while scan_budget["entries"] > 0:
                    try:
                        entry = next(stream)
                    except StopIteration:
                        break
                    scan_budget["entries"] -= 1
                    try:
                        if entry.is_symlink():
                            continue
                        entries.append(
                            (
                                entry.name,
                                entry.is_dir(follow_symlinks=False),
                                entry.is_file(follow_symlinks=False),
                            )
                        )
                    except OSError:
                        continue
        except OSError:
            continue
        finally:
            if directory_descriptor is not None:
                os.close(directory_descriptor)
        child_directories = []
        for name, is_directory, is_file in sorted(
            entries, key=lambda item: item[0]
        ):
            path = directory / name
            if is_file and name == "SKILL.md":
                yield path
                continue
            if is_directory and depth < max_depth:
                child_directories.append(path)
        for child in reversed(child_directories):
            pending.append((child, depth + 1))

root = pathlib.Path(sys.argv[1])
max_bytes = int(sys.argv[2])
max_skills = int(sys.argv[3])
max_skill_bytes = int(sys.argv[4])
max_scan_entries = int(sys.argv[5])
max_scan_directories = int(sys.argv[6])
max_scan_depth = int(sys.argv[7])
if not root.is_absolute():
    print("remote project root is invalid", file=sys.stderr)
    raise SystemExit(2)
try:
    root_descriptor = open_directory(root)
    os.close(root_descriptor)
except OSError:
    print(
        "remote project root is invalid: it must be readable and contain no symlinks",
        file=sys.stderr,
    )
    raise SystemExit(2)

payload = {"skills": []}
for directory in (root, *root.parents):
    for filename in ("AGENTS.md", "CLAUDE.md"):
        candidate = directory / filename
        data = read_bounded_file(candidate, max_bytes)
        if data is None:
            continue
        if not data:
            continue
        content = data[:max_bytes].decode("utf-8", errors="replace").strip()
        if len(data) > max_bytes:
            content += "\n\n[Project instructions truncated at the configured byte limit.]"
        if content:
            payload = {"path": str(candidate), "content": content}
            break
    if payload.get("path"):
        break

discovered = {}
scanned_candidates = 0
scan_budget = {
    "entries": max_scan_entries,
    "directories": max_scan_directories,
}
for relative_root in ((".agents", "skills"), (".codex", "skills")):
    skills_root = root.joinpath(*relative_root)
    candidates = iter_skill_files(
        skills_root,
        scan_budget,
        max_scan_depth,
    )
    try:
        while scanned_candidates < max_skills:
            try:
                candidate = next(candidates)
            except StopIteration:
                break
            scanned_candidates += 1
            data = read_bounded_file(candidate, max_skill_bytes)
            if not data or len(data) > max_skill_bytes:
                continue
            try:
                text = data.decode("utf-8", errors="strict").strip()
            except UnicodeDecodeError:
                continue
            if not text.startswith("---\n"):
                continue
            boundary = text.find("\n---", 4)
            if boundary < 0:
                continue
            fields = {}
            for line in text[4:boundary].splitlines():
                key, separator, value = line.partition(":")
                if separator and key.strip() in {"name", "description"}:
                    fields[key.strip()] = value.strip().strip("\"'")
            name = fields.get("name")
            description = fields.get("description")
            if not name or not description or name in discovered:
                continue
            discovered[name] = {
                "name": name,
                "description": description,
                "path": str(candidate),
            }
    finally:
        if candidates is not None:
            candidates.close()
    if scanned_candidates >= max_skills:
        break
    if scan_budget["entries"] <= 0:
        break
    if scan_budget["directories"] <= 0:
        break
payload["skills"] = sorted(
    discovered.values(), key=lambda item: (item["name"], item["path"])
)
print(json.dumps(payload, ensure_ascii=False))
""".strip()


class _DatabaseRemoteExecutor:
    """Resolve current SSH credentials without persisting them in history."""

    def __init__(
        self,
        db: AsyncSession,
        *,
        workspace_id: str,
        connection_id: str,
        executor: RemoteExecutor,
    ) -> None:
        self.db = db
        self.workspace_id = workspace_id
        self.connection_id = connection_id
        self.executor = executor
        self._credential_resolution_lock = asyncio.Lock()

    async def run(
        self,
        connection: RemoteConnectionConfig,
        command: str,
        *,
        timeout_seconds: int,
        output_limit: int,
    ):
        resolved = await self._resolve_current_connection(connection)
        return await self.executor.run(
            resolved,
            command,
            timeout_seconds=timeout_seconds,
            output_limit=output_limit,
        )

    async def run_with_stdin(
        self,
        connection: RemoteConnectionConfig,
        command: str,
        *,
        stdin_data: bytes,
        timeout_seconds: int,
        output_limit: int,
    ):
        resolved = await self._resolve_current_connection(connection)
        return await self.executor.run_with_stdin(
            resolved,
            command,
            stdin_data=stdin_data,
            timeout_seconds=timeout_seconds,
            output_limit=output_limit,
        )

    async def _resolve_current_connection(
        self,
        connection: RemoteConnectionConfig,
    ) -> RemoteConnectionConfig:
        if connection.id != self.connection_id:
            raise ValueError("remote connection does not match the session workspace")
        async with self._credential_resolution_lock:
            service = RemoteConnectionService(self.db)
            model = await service.get_connection(
                self.connection_id,
                workspace_id=self.workspace_id,
            )
            if model is None:
                raise NotFoundError(
                    f"Remote connection not found: {self.connection_id}"
                )
            resolved = await service.resolve_connection_config(model)
            if (
                resolved.host != connection.host
                or resolved.port != connection.port
                or resolved.username != connection.username
            ):
                raise ValueError(
                    "remote connection target changed after the Agent session "
                    "was created"
                )
            return resolved


def _remote_connection_snapshot(snapshot: dict[str, Any]) -> RemoteConnectionConfig:
    raw = snapshot.get("remote_connection")
    if not isinstance(raw, dict):
        raise ValueError("remote workspace is missing its connection snapshot")
    required = ("id", "name", "host", "username")
    if any(
        not isinstance(raw.get(key), str) or not raw[key].strip() for key in required
    ):
        raise ValueError("remote workspace connection snapshot is invalid")
    port = raw.get("port")
    if not isinstance(port, int) or not 1 <= port <= 65535:
        raise ValueError("remote workspace connection port is invalid")
    return RemoteConnectionConfig(
        id=raw["id"],
        name=raw["name"],
        host=raw["host"],
        username=raw["username"],
        port=port,
    )


def _local_skill_read_roots(session: Any) -> tuple[Path, ...]:
    prompt_snapshot = getattr(session, "prompt_snapshot", None)
    if not isinstance(prompt_snapshot, dict):
        return ()
    raw_roots = prompt_snapshot.get("skill_read_roots")
    if not isinstance(raw_roots, list):
        return ()
    roots: list[Path] = []
    for raw_root in raw_roots[:200]:
        if not isinstance(raw_root, str) or not raw_root.strip():
            continue
        candidate = Path(raw_root).expanduser()
        if not candidate.is_absolute():
            continue
        try:
            resolved = candidate.resolve(strict=True)
        except OSError:
            continue
        if resolved.is_dir() and resolved not in roots:
            roots.append(resolved)
    return tuple(roots)


__all__ = [
    "harness_for_database",
    "open_session_request_workspace",
    "resolve_model_snapshot",
    "workspace_runtime_for_session",
]
