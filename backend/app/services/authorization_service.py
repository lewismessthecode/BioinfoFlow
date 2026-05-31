from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.workspace_repo import WorkspaceMembershipRepository
from app.utils.authorization import can_perform_destructive_business_action
from app.utils.exceptions import PermissionDeniedError


class AuthorizationService:
    def __init__(self, session: AsyncSession):
        self.membership_repo = WorkspaceMembershipRepository(session)

    async def resolve_workspace_role(
        self,
        *,
        workspace_id: str | None,
        user_id: str | None,
        fallback_role: str | None = None,
    ) -> str | None:
        if fallback_role:
            return fallback_role
        if not workspace_id or not user_id:
            return fallback_role
        membership = await self.membership_repo.get_for_user(
            workspace_id=workspace_id,
            user_id=user_id,
        )
        if membership is None:
            return fallback_role
        return str(membership.role or fallback_role or "")

    async def require_destructive_business_access(
        self,
        *,
        workspace_id: str | None,
        user_id: str | None,
        user_role: str | None = None,
    ) -> None:
        role = await self.resolve_workspace_role(
            workspace_id=workspace_id,
            user_id=user_id,
            fallback_role=user_role,
        )
        if not can_perform_destructive_business_action(role):
            raise PermissionDeniedError(
                "You do not have permission to perform this action."
            )
