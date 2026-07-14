from __future__ import annotations

from typing import Any, Generic, Iterable, TypeVar

from sqlalchemy import and_, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.common import Pagination
from app.utils.pagination import decode_cursor, encode_cursor, normalize_cursor_value


ModelT = TypeVar("ModelT")


class BaseRepository(Generic[ModelT]):
    model: type[ModelT]

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self, item_id: str) -> ModelT | None:
        return await self.session.get(self.model, item_id)

    async def create(self, **data: Any) -> ModelT:
        obj = self.model(**data)
        self.session.add(obj)
        await self.session.commit()
        await self.session.refresh(obj)
        return obj

    async def add(self, **data: Any) -> ModelT:
        """Add and flush an object without committing the surrounding transaction."""
        obj = self.model(**data)
        self.session.add(obj)
        await self.session.flush()
        return obj

    async def bulk_create(self, items: list[dict[str, Any]]) -> list[ModelT]:
        if not items:
            return []

        try:
            objects = [self.model(**data) for data in items]
            self.session.add_all(objects)
            await self.session.commit()
            return objects
        except Exception:
            await self.session.rollback()
            raise

    async def update(self, obj: ModelT, **data: Any) -> ModelT:
        for key, value in data.items():
            if value is not None:
                setattr(obj, key, value)
        await self.session.commit()
        await self.session.refresh(obj)
        return obj

    async def update_all(self, obj: ModelT, **data: Any) -> ModelT:
        """Update *obj* setting ALL keyword values, including ``None``.

        Unlike :meth:`update` (which skips ``None`` values), this method
        applies every supplied key-value pair.  Use it when you need to
        explicitly clear a nullable column — e.g. ``error_message=None``.
        """
        for key, value in data.items():
            setattr(obj, key, value)
        await self.session.commit()
        await self.session.refresh(obj)
        return obj

    async def update_all_pending(self, obj: ModelT, **data: Any) -> ModelT:
        for key, value in data.items():
            setattr(obj, key, value)
        await self.session.flush()
        return obj

    async def delete(self, obj: ModelT) -> None:
        await self.session.delete(obj)
        await self.session.commit()

    def _apply_filters(self, stmt, filters: dict[str, Any] | None):
        if not filters:
            return stmt
        clauses = []
        for key, value in filters.items():
            if value is None:
                continue
            column = getattr(self.model, key)
            if isinstance(value, (list, tuple, set)):
                clauses.append(column.in_(list(value)))
            else:
                clauses.append(column == value)
        if clauses:
            stmt = stmt.where(and_(*clauses))
        return stmt

    async def list(
        self,
        *,
        limit: int = 20,
        cursor: str | None = None,
        filters: dict[str, Any] | None = None,
        stmt=None,
    ) -> tuple[list[ModelT], Pagination]:
        base_stmt = stmt if stmt is not None else select(self.model)
        base_stmt = self._apply_filters(base_stmt, filters)

        count_stmt = select(func.count()).select_from(
            base_stmt.order_by(None).subquery()
        )
        total_count = await self.session.scalar(count_stmt)

        order_by = [desc(self.model.created_at), desc(self.model.id)]
        stmt = base_stmt.order_by(*order_by)

        if cursor:
            cursor_data = decode_cursor(cursor)
            cursor_created_at = normalize_cursor_value(cursor_data.get("created_at"))
            cursor_id = cursor_data.get("id")
            if cursor_created_at is not None and cursor_id is not None:
                stmt = stmt.where(
                    or_(
                        self.model.created_at < cursor_created_at,
                        and_(
                            self.model.created_at == cursor_created_at,
                            self.model.id < cursor_id,
                        ),
                    )
                )

        result = await self.session.execute(stmt.limit(limit + 1))
        items = list(result.scalars().all())
        has_more = len(items) > limit
        items = items[:limit]

        next_cursor = None
        if has_more and items:
            last = items[-1]
            next_cursor = encode_cursor(
                {"created_at": last.created_at.isoformat(), "id": str(last.id)}
            )

        pagination = Pagination(
            limit=limit,
            has_more=has_more,
            next_cursor=next_cursor,
            total_count=total_count or 0,
        )
        return items, pagination

    def _apply_search(self, stmt, columns: Iterable, search: str | None):
        if not search:
            return stmt
        # Escape LIKE-special characters to prevent wildcard injection
        escaped = search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        terms = [column.ilike(f"%{escaped}%", escape="\\") for column in columns]
        return stmt.where(or_(*terms))
