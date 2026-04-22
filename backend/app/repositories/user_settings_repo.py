from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_settings import UserSettings


class UserSettingsRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_user_id(self, user_id: str) -> UserSettings | None:
        stmt = select(UserSettings).where(UserSettings.user_id == user_id)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def upsert(self, user_id: str, **data) -> UserSettings:
        existing = await self.get_by_user_id(user_id)
        if existing:
            for key, value in data.items():
                if value is not None:
                    setattr(existing, key, value)
            await self.session.commit()
            await self.session.refresh(existing)
            return existing

        obj = UserSettings(user_id=user_id, **{k: v for k, v in data.items() if v is not None})
        self.session.add(obj)
        await self.session.commit()
        await self.session.refresh(obj)
        return obj
