from __future__ import annotations

from sqlalchemy import select

from app.models.notification import NotificationConfig
from app.repositories.base import BaseRepository


class NotificationRepository(BaseRepository[NotificationConfig]):
    model = NotificationConfig

    async def list_configs(
        self,
        *,
        project_id: str | None = None,
        trigger: str | None = None,
        enabled: bool | None = None,
    ) -> list[NotificationConfig]:
        stmt = select(self.model).order_by(
            self.model.created_at.asc(),
            self.model.id.asc(),
        )
        filters: dict[str, object] = {"project_id": project_id, "trigger": trigger}
        if enabled is not None:
            filters["enabled"] = enabled
        stmt = self._apply_filters(stmt, filters)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
