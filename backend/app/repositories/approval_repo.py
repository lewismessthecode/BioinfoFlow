from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from app.models.approval import AgentApproval
from app.enums import ApprovalStatus
from app.repositories.base import BaseRepository


class ApprovalRepository(BaseRepository[AgentApproval]):
    model = AgentApproval

    async def get_fresh(self, approval_id: str) -> AgentApproval | None:
        """Fetch an approval bypassing the session identity map.

        Long-running pollers (wait_for_approval) share a session with the
        writer that resolves the approval but the writer commits in a
        separate session. Without populate_existing=True the poller keeps
        seeing the stale PENDING row cached from its first read.
        """
        stmt = (
            select(self.model)
            .where(self.model.id == approval_id)
            .execution_options(populate_existing=True)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create_approval(
        self,
        *,
        conversation_id: str,
        step_id: str,
        approval_type: str,
        payload: dict[str, Any] | None = None,
    ) -> AgentApproval:
        return await self.create(
            conversation_id=conversation_id,
            step_id=step_id,
            approval_type=approval_type,
            payload=payload,
            status=ApprovalStatus.PENDING,
        )

    async def resolve(
        self,
        approval: AgentApproval,
        *,
        status: str,
        resolved_by: str | None = None,
    ) -> AgentApproval:
        return await self.update(
            approval,
            status=status,
            resolved_by=resolved_by,
            resolved_at=datetime.now(timezone.utc),
        )

    async def get_pending_for_conversation(
        self,
        conversation_id: str,
    ) -> list[AgentApproval]:
        stmt = (
            select(self.model)
            .where(self.model.conversation_id == conversation_id)
            .where(self.model.status == ApprovalStatus.PENDING)
            .order_by(self.model.created_at)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_step_id(
        self,
        conversation_id: str,
        step_id: str,
    ) -> AgentApproval | None:
        stmt = (
            select(self.model)
            .where(self.model.conversation_id == conversation_id)
            .where(self.model.step_id == step_id)
            .order_by(self.model.created_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_conversation(
        self,
        conversation_id: str,
        *,
        limit: int = 50,
        cursor: str | None = None,
    ):
        return await self.list(
            limit=limit,
            cursor=cursor,
            filters={"conversation_id": conversation_id},
        )
