from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.remote_connection import RemoteConnection, RemoteConnectionStatus
from app.repositories.remote_connection_repo import RemoteConnectionRepository
from app.utils.exceptions import ConflictError, ValidationError


@dataclass(frozen=True)
class RemoteConnectionTestResult:
    status: str
    error: str | None = None


class RemoteConnectionTester(Protocol):
    async def test(
        self,
        connection: RemoteConnection,
    ) -> RemoteConnectionTestResult: ...


class UnavailableRemoteConnectionTester:
    async def test(self, connection: RemoteConnection) -> RemoteConnectionTestResult:
        del connection
        return RemoteConnectionTestResult(
            status=RemoteConnectionStatus.ERROR,
            error="SSH connection testing is not configured",
        )


class RemoteConnectionService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        tester: RemoteConnectionTester | None = None,
    ) -> None:
        self.repo = RemoteConnectionRepository(session)
        self.tester = tester or UnavailableRemoteConnectionTester()

    async def list_connections(
        self,
        *,
        workspace_id: str,
        limit: int = 20,
        cursor: str | None = None,
    ):
        return await self.repo.list_for_workspace(
            workspace_id=workspace_id,
            limit=limit,
            cursor=cursor,
        )

    async def get_connection(
        self,
        connection_id: str,
        *,
        workspace_id: str,
    ) -> RemoteConnection | None:
        return await self.repo.get_for_workspace(
            connection_id,
            workspace_id=workspace_id,
        )

    async def create_connection(
        self,
        data: dict,
        *,
        workspace_id: str,
    ) -> RemoteConnection:
        try:
            return await self.repo.create(
                **data,
                workspace_id=workspace_id,
                last_status=RemoteConnectionStatus.UNKNOWN,
            )
        except IntegrityError as exc:
            await self.repo.session.rollback()
            raise ConflictError(
                "A remote connection with this name already exists in the workspace"
            ) from exc

    async def update_connection(
        self,
        connection: RemoteConnection,
        data: dict,
    ) -> RemoteConnection:
        try:
            return await self.repo.update_all(connection, **data)
        except IntegrityError as exc:
            await self.repo.session.rollback()
            raise ConflictError(
                "A remote connection with this name already exists in the workspace"
            ) from exc

    async def delete_connection(self, connection: RemoteConnection) -> None:
        await self.repo.delete(connection)

    async def test_connection(
        self,
        connection: RemoteConnection,
    ) -> tuple[RemoteConnection, datetime]:
        result = await self.tester.test(connection)
        if result.status not in RemoteConnectionStatus.VALUES:
            raise ValidationError(
                "Remote connection tester returned an unsupported status",
                details={"status": result.status},
            )
        checked_at = datetime.now(timezone.utc)
        updated = await self.repo.record_test_result(
            connection,
            status=result.status,
            error=result.error,
            checked_at=checked_at,
        )
        return updated, updated.last_checked_at or checked_at
