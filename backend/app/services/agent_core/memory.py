from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_core import AgentMemoryStatus
from app.repositories.agent_core_repo import (
    AgentMemoryRepository,
    AgentSessionRepository,
    AgentTurnRepository,
)
from app.repositories.project_repo import ProjectRepository
from app.services.agent_core.events import AgentEventType
from app.services.agent_core.ledger import AgentEventLedger
from app.utils.exceptions import BadRequestError, NotFoundError, PermissionDeniedError


class AgentMemoryService:
    def __init__(self, session: AsyncSession):
        self.memory_repo = AgentMemoryRepository(session)
        self.project_repo = ProjectRepository(session)
        self.session_repo = AgentSessionRepository(session)
        self.turn_repo = AgentTurnRepository(session)
        self.ledger = AgentEventLedger(session)

    async def list_memories(
        self,
        *,
        workspace_id: str,
        project_id: str | None = None,
        status: str | None = None,
        scope: str | None = None,
        type: str | None = None,
        session_id: str | None = None,
        turn_id: str | None = None,
    ):
        if project_id:
            await self._require_project(project_id, workspace_id)
        memories = await self.memory_repo.list_for_workspace(
            workspace_id=workspace_id,
            project_id=project_id,
            status=status,
            scope=scope,
            type=type,
        )
        if session_id and turn_id:
            await self.ledger.append(
                session_id=session_id,
                turn_id=turn_id,
                type=AgentEventType.MEMORY_READ,
                payload={
                    "project_id": project_id,
                    "status": status,
                    "scope": scope,
                    "type": type,
                    "count": len(memories),
                },
            )
        return memories

    async def propose_memory(
        self,
        *,
        workspace_id: str,
        project_id: str | None,
        scope: str,
        type: str,
        content: dict,
        session_id: str | None = None,
        turn_id: str | None = None,
        source: dict | None = None,
        confidence: int | None = None,
    ):
        if project_id:
            await self._require_project(project_id, workspace_id)
        if session_id:
            await self._require_session(session_id, workspace_id)
        if turn_id:
            await self._require_turn(turn_id, workspace_id)
        if confidence is not None and not 0 <= confidence <= 100:
            raise BadRequestError("confidence must be between 0 and 100")
        memory = await self.memory_repo.create(
            workspace_id=workspace_id,
            project_id=project_id,
            session_id=session_id,
            scope=scope,
            type=type,
            content=content,
            source=source,
            confidence=confidence,
            status=AgentMemoryStatus.PROPOSED,
        )
        if session_id and turn_id:
            await self.ledger.append(
                session_id=session_id,
                turn_id=turn_id,
                type=AgentEventType.MEMORY_PROPOSED,
                payload={
                    "memory_id": str(memory.id),
                    "scope": memory.scope,
                    "type": memory.type,
                    "confidence": memory.confidence,
                },
            )
        return memory

    async def update_memory_status(
        self,
        *,
        memory_id: str,
        workspace_id: str,
        user_id: str,
        status: str,
        note: str | None = None,
    ):
        del user_id
        if status not in {
            AgentMemoryStatus.ACCEPTED,
            AgentMemoryStatus.REJECTED,
            AgentMemoryStatus.DISABLED,
        }:
            raise BadRequestError(f"Unsupported memory status: {status}")
        memory = await self.memory_repo.get(memory_id)
        if memory is None:
            raise NotFoundError(f"Agent memory not found: {memory_id}")
        if str(memory.workspace_id) != str(workspace_id):
            raise PermissionDeniedError("Agent memory is not accessible")

        source = dict(memory.source or {})
        if note:
            source["decision_note"] = note
        updated = await self.memory_repo.update_all(memory, status=status, source=source or None)
        if updated.session_id:
            turn_id = await self._latest_turn_id_for_session(str(updated.session_id))
            if turn_id:
                await self.ledger.append(
                    session_id=str(updated.session_id),
                    turn_id=turn_id,
                    type=_event_type_for_status(status),
                    payload={
                        "memory_id": str(updated.id),
                        "status": status,
                        "note": note,
                    },
                )
        return updated

    async def _require_project(self, project_id: str, workspace_id: str):
        project = await self.project_repo.get(project_id)
        if project is None:
            raise NotFoundError(f"Project not found: {project_id}")
        if str(project.workspace_id) != str(workspace_id):
            raise PermissionDeniedError("Project is not in the current workspace")
        return project

    async def _require_session(self, session_id: str, workspace_id: str):
        session = await self.session_repo.get(session_id)
        if session is None:
            raise NotFoundError(f"Agent session not found: {session_id}")
        if str(session.workspace_id) != str(workspace_id):
            raise PermissionDeniedError("Agent session is not accessible")
        return session

    async def _require_turn(self, turn_id: str, workspace_id: str):
        turn = await self.turn_repo.get(turn_id)
        if turn is None:
            raise NotFoundError(f"Agent turn not found: {turn_id}")
        if str(turn.workspace_id) != str(workspace_id):
            raise PermissionDeniedError("Agent turn is not accessible")
        return turn

    async def _latest_turn_id_for_session(self, session_id: str) -> str | None:
        turns = await self.turn_repo.list_for_session(session_id)
        if not turns:
            return None
        return str(turns[-1].id)


def _event_type_for_status(status: str) -> str:
    if status == AgentMemoryStatus.ACCEPTED:
        return AgentEventType.MEMORY_WRITTEN
    return AgentEventType.MEMORY_REJECTED
