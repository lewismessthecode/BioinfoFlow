from __future__ import annotations

from typing import AsyncGenerator

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import (
    require_admin as _require_admin,
    require_owner as _require_owner,
    resolve_current_user,
    resolve_optional_user,
)
from app.database import async_session_maker


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        yield session


async def get_current_user(
    request: Request, db: AsyncSession = Depends(get_db)
):
    return await resolve_current_user(request, db)


async def get_optional_user(
    request: Request, db: AsyncSession = Depends(get_db)
):
    return await resolve_optional_user(request, db)


async def require_admin(
    request: Request, db: AsyncSession = Depends(get_db)
):
    return await _require_admin(request, db)


async def require_owner(
    request: Request, db: AsyncSession = Depends(get_db)
):
    return await _require_owner(request, db)
