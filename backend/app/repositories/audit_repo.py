"""Repository for audit log persistence.

Wraps all database access for AuditLog, including graceful handling of a
missing ``audit_logs`` table (can happen before migrations run).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from app.models.audit_log import AuditLog
from app.repositories.base import BaseRepository
from app.utils.logging import get_logger

logger = get_logger(__name__)


def _is_missing_audit_logs_table_error(exc: OperationalError) -> bool:
    return "no such table: audit_logs" in str(exc).lower()


class AuditRepository(BaseRepository[AuditLog]):
    model = AuditLog

    async def safe_create(self, **kwargs) -> AuditLog | None:
        """Create an audit log entry, returning *None* if the table doesn't exist."""
        entry = self.model(**kwargs)
        try:
            async with self.session.begin_nested():
                self.session.add(entry)
                await self.session.flush()
        except OperationalError as exc:
            if not _is_missing_audit_logs_table_error(exc):
                raise
            logger.warning(
                "audit.log.skipped_missing_table",
                action=kwargs.get("action"),
            )
            return None
        await self.session.commit()
        await self.session.refresh(entry)
        return entry

    async def safe_list_for_resource(
        self, resource_type: str, resource_id: str
    ) -> list[AuditLog]:
        """List audit logs for a resource, returning ``[]`` if the table doesn't exist."""
        stmt = (
            select(self.model)
            .where(
                self.model.resource_type == resource_type,
                self.model.resource_id == resource_id,
            )
            .order_by(self.model.created_at.asc(), self.model.id.asc())
        )
        try:
            result = await self.session.execute(stmt)
        except OperationalError as exc:
            if not _is_missing_audit_logs_table_error(exc):
                raise
            await self.session.rollback()
            logger.warning(
                "audit.list.skipped_missing_table",
                resource_type=resource_type,
                resource_id=resource_id,
            )
            return []
        return list(result.scalars().all())
