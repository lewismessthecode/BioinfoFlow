from __future__ import annotations

from sqlalchemy import and_, desc, func, or_, select

from app.models.conversation import Conversation
from app.models.project import Project
from app.repositories.base import BaseRepository
from app.utils.pagination import decode_cursor, encode_cursor, normalize_cursor_value
from app.schemas.common import Pagination


class ConversationRepository(BaseRepository[Conversation]):
    model = Conversation

    async def list(
        self,
        *,
        limit: int = 20,
        cursor: str | None = None,
        project_id: str | None = None,
        workspace_id: str | None = None,
    ) -> tuple[list[Conversation], Pagination]:
        stmt = select(self.model)
        if project_id:
            stmt = stmt.where(self.model.project_id == project_id)
        elif workspace_id:
            stmt = stmt.join(Project, Project.id == self.model.project_id).where(
                Project.workspace_id == workspace_id,
                Project.user_id != "system",
            )

        order_by = [
            desc(self.model.pinned),
            desc(self.model.updated_at),
            desc(self.model.id),
        ]
        stmt = stmt.order_by(*order_by)

        if cursor:
            cursor_data = decode_cursor(cursor)
            cursor_pinned = cursor_data.get("pinned")
            cursor_updated_at = normalize_cursor_value(cursor_data.get("updated_at"))
            cursor_id = cursor_data.get("id")
            if (
                cursor_updated_at is not None
                and cursor_id is not None
                and cursor_pinned is not None
            ):
                stmt = stmt.where(
                    or_(
                        self.model.pinned < cursor_pinned,
                        and_(
                            self.model.pinned == cursor_pinned,
                            or_(
                                self.model.updated_at < cursor_updated_at,
                                and_(
                                    self.model.updated_at == cursor_updated_at,
                                    self.model.id < cursor_id,
                                ),
                            ),
                        ),
                    )
                )

        count_stmt = select(self.model.id)
        if project_id:
            count_stmt = count_stmt.where(self.model.project_id == project_id)
        elif workspace_id:
            count_stmt = count_stmt.join(
                Project, Project.id == self.model.project_id
            ).where(
                Project.workspace_id == workspace_id,
                Project.user_id != "system",
            )
        total_count = await self.session.scalar(
            select(func.count()).select_from(count_stmt.subquery())
        )

        result = await self.session.execute(stmt.limit(limit + 1))
        items = list(result.scalars().all())
        has_more = len(items) > limit
        items = items[:limit]

        next_cursor = None
        if has_more and items:
            last = items[-1]
            next_cursor = encode_cursor(
                {
                    "pinned": bool(last.pinned),
                    "updated_at": last.updated_at.isoformat(),
                    "id": str(last.id),
                }
            )

        pagination = Pagination(
            limit=limit,
            has_more=has_more,
            next_cursor=next_cursor,
            total_count=total_count or 0,
        )
        return items, pagination
