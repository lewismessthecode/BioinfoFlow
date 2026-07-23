from __future__ import annotations

from datetime import datetime

from sqlalchemy import exists, select

from app.models.remote_connection import RemoteConnection
from app.repositories.base import BaseRepository
from app.schemas.common import Pagination


class RemoteConnectionRepository(BaseRepository[RemoteConnection]):
    model = RemoteConnection

    async def list_for_workspace(
        self,
        *,
        workspace_id: str,
        limit: int = 20,
        cursor: str | None = None,
    ) -> tuple[list[RemoteConnection], Pagination]:
        stmt = select(self.model).where(self.model.workspace_id == workspace_id)
        return await super().list(limit=limit, cursor=cursor, stmt=stmt)

    async def get_for_workspace(
        self,
        connection_id: str,
        *,
        workspace_id: str,
    ) -> RemoteConnection | None:
        stmt = select(self.model).where(
            self.model.id == connection_id,
            self.model.workspace_id == workspace_id,
        ).execution_options(populate_existing=True)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_jump_for_workspace(
        self,
        connection_id: str,
        *,
        workspace_id: str,
    ) -> RemoteConnection | None:
        return await self.get_for_workspace(
            connection_id,
            workspace_id=workspace_id,
        )

    async def has_jump_dependents(
        self,
        connection_id: str,
        *,
        workspace_id: str,
    ) -> bool:
        stmt = select(
            exists().where(
                self.model.jump_connection_id == connection_id,
                self.model.workspace_id == workspace_id,
            )
        )
        return bool(await self.session.scalar(stmt))

    async def record_test_result(
        self,
        connection: RemoteConnection,
        *,
        status: str,
        error: str | None,
        checked_at: datetime,
    ) -> RemoteConnection:
        return await self.update_all(
            connection,
            last_status=status,
            last_error=error,
            last_checked_at=checked_at,
        )
