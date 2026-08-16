from __future__ import annotations

from typing import Any, Protocol

from app.services.agent_harness.environment_scope import EnvironmentDescriptor


class EnvironmentRepository(Protocol):
    async def list_for_workspace(
        self,
        *,
        workspace_id: str,
        limit: int,
        cursor: str | None,
    ) -> tuple[list[Any], Any]: ...

    async def get_for_workspace(
        self,
        connection_id: str,
        *,
        workspace_id: str,
    ) -> Any | None: ...


class EnvironmentCatalog:
    def __init__(self, repository: EnvironmentRepository) -> None:
        self.repository = repository

    async def list_authorized(
        self,
        *,
        workspace_id: str,
    ) -> tuple[EnvironmentDescriptor, ...]:
        environments = [
            EnvironmentDescriptor(
                environment_id="local",
                kind="local",
                display_name="Local",
                description="This machine",
                status="online",
            )
        ]
        cursor: str | None = None
        while True:
            connections, pagination = await self.repository.list_for_workspace(
                workspace_id=workspace_id,
                limit=100,
                cursor=cursor,
            )
            environments.extend(
                EnvironmentDescriptor(
                    environment_id=str(connection.id),
                    kind="ssh",
                    display_name=str(connection.name),
                    description=(
                        f"{connection.username}@{connection.host}:{connection.port}"
                    ),
                    status=str(connection.last_status),
                )
                for connection in connections
            )
            if not pagination.has_more or not pagination.next_cursor:
                break
            cursor = pagination.next_cursor
        return tuple(environments)

    async def is_authorized(
        self,
        environment_id: str,
        *,
        workspace_id: str,
    ) -> bool:
        if environment_id == "local":
            return True
        connection = await self.repository.get_for_workspace(
            environment_id,
            workspace_id=workspace_id,
        )
        return connection is not None
