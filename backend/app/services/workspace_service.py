from __future__ import annotations

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.session import AuthUser
from app.repositories.workspace_repo import (
    WorkspaceMembershipRepository,
    WorkspaceRepository,
)
from app.workspace import (
    DEFAULT_WORKSPACE_ID,
    DEFAULT_WORKSPACE_NAME,
    DEFAULT_WORKSPACE_SLUG,
)


class WorkspaceService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.workspace_repo = WorkspaceRepository(session)
        self.membership_repo = WorkspaceMembershipRepository(session)

    async def ensure_default_workspace(self) -> None:
        workspace = await self.workspace_repo.get_default(DEFAULT_WORKSPACE_ID)
        if workspace is not None:
            return
        await self.workspace_repo.create(
            id=DEFAULT_WORKSPACE_ID,
            name=DEFAULT_WORKSPACE_NAME,
            slug=DEFAULT_WORKSPACE_SLUG,
            is_default=True,
        )

    async def ensure_membership(self, user: AuthUser) -> None:
        await self.ensure_default_workspace()
        membership = await self.membership_repo.get_for_user(
            workspace_id=user.workspace_id,
            user_id=user.id,
        )
        if membership is None:
            try:
                await self.membership_repo.create(
                    workspace_id=user.workspace_id,
                    user_id=user.id,
                    role=user.role,
                )
                return
            except IntegrityError:
                await self.session.rollback()
                membership = await self.membership_repo.get_for_user(
                    workspace_id=user.workspace_id,
                    user_id=user.id,
                )
                if membership is None:
                    raise
        if membership.role != user.role:
            await self.membership_repo.update(membership, role=user.role)
