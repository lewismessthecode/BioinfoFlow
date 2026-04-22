"""Approval service for agent operations.

This module provides the ApprovalService for managing approval requests
during plan execution.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from app.enums import ApprovalStatus
from app.models.approval import ApprovalType
from app.repositories.approval_repo import ApprovalRepository
from app.utils.logging import get_logger

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.models.approval import AgentApproval

logger = get_logger(__name__)

# Default timeout for waiting on approval. None = poll until resolved or the
# surrounding task is cancelled (e.g. user hits Stop). Matching Claude Code's
# AskUserQuestion behaviour: the user decides when they decide.
DEFAULT_APPROVAL_TIMEOUT: float | None = None

# Poll interval for checking approval status
APPROVAL_POLL_INTERVAL = 1.0


class ApprovalTimeoutError(Exception):
    """Raised when approval times out (only when an explicit timeout was set)."""

    def __init__(self, approval_id: str, timeout: float) -> None:
        self.approval_id = approval_id
        self.timeout = timeout
        super().__init__(f"Approval {approval_id} timed out after {timeout}s")


class ApprovalService:
    """Service for managing agent approval requests."""

    def __init__(self, session: "AsyncSession") -> None:
        """Initialize approval service.

        Args:
            session: Database session
        """
        self.session = session
        self.repo = ApprovalRepository(session)

    async def create_approval(
        self,
        *,
        conversation_id: str,
        step_id: str,
        approval_type: str,
        payload: dict[str, Any] | None = None,
    ) -> "AgentApproval":
        """Create a new approval request.

        Args:
            conversation_id: The conversation this approval belongs to
            step_id: The plan step ID that triggered this approval
            approval_type: Type of approval (run, file_diff, code_exec)
            payload: Context data for the approval

        Returns:
            The created approval record
        """
        approval = await self.repo.create_approval(
            conversation_id=conversation_id,
            step_id=step_id,
            approval_type=approval_type,
            payload=payload,
        )

        logger.info(
            "approval.created",
            approval_id=str(approval.id),
            conversation_id=conversation_id,
            step_id=step_id,
            approval_type=approval_type,
        )

        return approval

    async def get(self, approval_id: str) -> "AgentApproval | None":
        """Get an approval by ID.

        Args:
            approval_id: The approval ID

        Returns:
            The approval record or None
        """
        return await self.repo.get(approval_id)

    async def resolve(
        self,
        approval_id: str,
        *,
        action: str,
        resolved_by: str | None = None,
    ) -> "AgentApproval | None":
        """Resolve an approval request.

        Args:
            approval_id: The approval ID to resolve
            action: "approve" or "reject"
            resolved_by: User or system that resolved this

        Returns:
            The updated approval record or None if not found
        """
        approval = await self.repo.get(approval_id)
        if approval is None:
            return None

        if approval.status != ApprovalStatus.PENDING:
            logger.warning(
                "approval.already_resolved",
                approval_id=approval_id,
                current_status=approval.status,
            )
            return approval

        new_status = (
            ApprovalStatus.APPROVED if action == "approve" else ApprovalStatus.REJECTED
        )

        approval = await self.repo.resolve(
            approval,
            status=new_status,
            resolved_by=resolved_by,
        )

        logger.info(
            "approval.resolved",
            approval_id=approval_id,
            status=new_status,
            resolved_by=resolved_by,
        )

        return approval

    async def wait_for_approval(
        self,
        approval_id: str,
        *,
        timeout: float | None = DEFAULT_APPROVAL_TIMEOUT,
        poll_interval: float = APPROVAL_POLL_INTERVAL,
    ) -> "AgentApproval":
        """Wait for an approval to be resolved.

        This method polls the database for the approval status.

        Args:
            approval_id: The approval ID to wait for
            timeout: Maximum wait time in seconds. None means poll forever
                (until the task is cancelled via asyncio.CancelledError — the
                normal path when the user presses Stop). Default None.
            poll_interval: Time between polls in seconds

        Returns:
            The resolved approval record

        Raises:
            ApprovalTimeoutError: If approval times out (only when timeout set).
        """
        deadline = (
            asyncio.get_event_loop().time() + timeout
            if timeout is not None
            else None
        )

        while deadline is None or asyncio.get_event_loop().time() < deadline:
            approval = await self.repo.get_fresh(approval_id)
            if approval is None:
                raise ValueError(f"Approval {approval_id} not found")

            if approval.status != ApprovalStatus.PENDING:
                logger.info(
                    "approval.wait_complete",
                    approval_id=approval_id,
                    status=approval.status,
                )
                return approval

            await asyncio.sleep(poll_interval)

        assert timeout is not None  # loop only exits when a deadline was set
        raise ApprovalTimeoutError(approval_id, timeout)

    async def get_pending_for_conversation(
        self,
        conversation_id: str,
    ) -> list["AgentApproval"]:
        """Get all pending approvals for a conversation.

        Args:
            conversation_id: The conversation ID

        Returns:
            List of pending approval records
        """
        return await self.repo.get_pending_for_conversation(conversation_id)

    async def list_for_conversation(
        self,
        conversation_id: str,
        *,
        limit: int = 50,
        cursor: str | None = None,
    ):
        """List all approvals for a conversation.

        Args:
            conversation_id: The conversation ID
            limit: Maximum number of records
            cursor: Pagination cursor

        Returns:
            Tuple of (approvals, pagination)
        """
        return await self.repo.list_for_conversation(
            conversation_id,
            limit=limit,
            cursor=cursor,
        )

    @staticmethod
    def get_approval_type_for_tool(tool_name: str) -> str:
        """Get the approval type for a tool.

        Args:
            tool_name: The tool name

        Returns:
            Approval type string
        """
        # Map tools to approval types
        tool_type_map = {
            "execute_code": ApprovalType.CODE_EXEC,
            "run_create": ApprovalType.RUN,
            "run_cancel": ApprovalType.RUN,
            "run_retry": ApprovalType.RUN,
            "run_resume": ApprovalType.RUN,
            "file_write": ApprovalType.FILE_DIFF,
            "file_edit": ApprovalType.FILE_DIFF,
        }
        return tool_type_map.get(tool_name, ApprovalType.RUN)
