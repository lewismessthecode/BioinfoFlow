from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.session import validate_user
from app.config import settings
from app.path_layout import agent_user_workspace_root
from app.repositories.remote_connection_repo import RemoteConnectionRepository
from app.services.agent_harness.api_endpoint import workspace_api_url
from app.services.agent_harness.environment_catalog import EnvironmentCatalog
from app.services.agent_harness.environment_scope import (
    EnvironmentDescriptor,
    ResolvedEnvironmentScope,
)
from app.services.agent_harness.environment_target import (
    remote_environment_target_snapshot,
)
from app.services.agent_harness.routed_workspace_runtime import RoutedWorkspaceRuntime
from app.services.agent_harness.sandbox import SandboxRunner
from app.services.agent_harness.workspace_router import WorkspaceRouter
from app.services.agent_harness.workspace_runtime import (
    LocalWorkspaceBackend,
    RemoteWorkspaceBackend,
    WorkspaceRuntime,
)
from app.services.remote_connection_service import RemoteConnectionService
from app.services.remote_execution import (
    RemoteConnectionConfig,
    RemoteExecutor,
    SshRemoteExecutor,
)
from app.utils.authorization import can_manage_external_roots
from app.utils.exceptions import NotFoundError


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
        backend = LocalWorkspaceBackend(
            working_directory=root,
            read_roots=(root, *_local_skill_read_roots(session)),
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
    connection_repository = RemoteConnectionRepository(db)
    catalog = EnvironmentCatalog(connection_repository)
    scope_data = getattr(session, "environment_scope", None) or {"mode": "auto"}
    mode = "manual" if scope_data.get("mode") == "manual" else "auto"
    selected_ids = tuple(
        str(item)
        for item in (scope_data.get("environment_ids") or ())
        if isinstance(item, str) and item
    )
    environment_targets = getattr(session, "environment_targets", None) or {}
    scope_environments = {
        environment_id: EnvironmentDescriptor(
            environment_id,
            "local" if environment_id == "local" else "ssh",
            (
                "Local"
                if environment_id == "local"
                else str(
                    environment_targets.get(environment_id, {}).get("display_name")
                    or environment_id
                )
            ),
            (
                None
                if environment_id == "local"
                else _environment_target_description(
                    environment_targets.get(environment_id)
                )
            ),
            host=(
                None
                if environment_id == "local"
                else str(environment_targets.get(environment_id, {}).get("host") or "")
                or None
            ),
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
    allow_remote = _remote_environment_access_is_current(session)

    async def authorize(environment_id: str) -> bool:
        return await catalog.is_authorized(
            environment_id,
            workspace_id=str(session.workspace_id),
            allow_remote=allow_remote,
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
            workspace_id=str(session.workspace_id),
            allow_remote=allow_remote,
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


def _remote_environment_access_is_current(session: Any) -> bool:
    if not settings.auth_is_team:
        return True
    metadata = getattr(session, "session_metadata", None) or {}
    if metadata.get("_allow_remote_environments") is not True:
        return False
    user = validate_user(str(session.user_id))
    return user is not None and can_manage_external_roots(user.role)


def _environment_target_description(target: Any) -> str | None:
    if not isinstance(target, dict):
        return None
    host = target.get("host")
    port = target.get("port")
    username = target.get("username")
    if not isinstance(host, str) or not isinstance(username, str):
        return None
    if not isinstance(port, int):
        return None
    return f"{username}@{host}:{port}"


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
    connection_repository = RemoteConnectionRepository(db)
    service = RemoteConnectionService(db)
    model = await service.get_connection(
        environment_id,
        workspace_id=str(session.workspace_id),
    )
    if model is None:
        return None
    expected_targets = getattr(session, "environment_targets", None)
    if expected_targets is not None:
        expected_target = expected_targets.get(environment_id)
        if expected_target is None:
            return None
        current_target = await remote_environment_target_snapshot(
            connection_repository,
            model,
        )
        if current_target != expected_target:
            return None
        expected_revision = str(expected_target["configuration_revision"])
    else:
        expected_revision = None
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
            expected_configuration_revision=expected_revision,
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


class _DatabaseRemoteExecutor:
    """Resolve current SSH credentials without persisting them in history."""

    def __init__(
        self,
        db: AsyncSession,
        *,
        workspace_id: str,
        connection_id: str,
        executor: RemoteExecutor,
        expected_configuration_revision: str | None = None,
    ) -> None:
        self.db = db
        self.workspace_id = workspace_id
        self.connection_id = connection_id
        self.executor = executor
        self.expected_configuration_revision = expected_configuration_revision
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
            if self.expected_configuration_revision is not None:
                current_target = await remote_environment_target_snapshot(
                    service.repo,
                    model,
                )
                if (
                    current_target["configuration_revision"]
                    != self.expected_configuration_revision
                ):
                    raise ValueError(
                        "remote connection configuration changed after the Run "
                        "was created"
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


def _workspace_api_url(runtime: str) -> str:
    return workspace_api_url(
        runtime,
        configured_url=settings.bioinfoflow_public_api_base_url,
    )


__all__ = [
    "routed_workspace_runtime_for_session",
    "workspace_runtime_for_session",
]
