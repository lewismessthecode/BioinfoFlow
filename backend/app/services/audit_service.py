from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog
from app.repositories.audit_repo import AuditRepository


class AuditService:
    def __init__(self, session: AsyncSession) -> None:
        self._repo = AuditRepository(session)

    async def log(
        self,
        *,
        action: str,
        resource_type: str,
        resource_id: str,
        project_id: str | None = None,
        actor: str = "system",
        details: dict | None = None,
    ) -> AuditLog | None:
        return await self._repo.safe_create(
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            project_id=project_id,
            actor=actor,
            details=dict(details or {}),
        )

    async def list_for_resource(
        self,
        resource_type: str,
        resource_id: str,
    ) -> list[AuditLog]:
        return await self._repo.safe_list_for_resource(resource_type, resource_id)
