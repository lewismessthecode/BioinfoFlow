from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_core import AgentActionStatus, AgentSessionStatus, AgentTurnStatus
from app.repositories.agent_core_repo import (
    AgentActionRepository,
    AgentArtifactRepository,
    AgentEventRepository,
    AgentSessionRepository,
    AgentTurnRepository,
)
from app.repositories.project_repo import ProjectRepository
from app.services.agent_core.events import AgentEventType
from app.services.agent_core.ledger import AgentEventLedger
from app.services.agent_core.model_selection import session_metadata_with_model_selection
from app.services.agent_core.runtime import AgentCoreRuntime
from app.services.agent_core.tools import (
    AgentToolContext,
    AgentToolDispatcher,
    build_default_tool_registry,
)
from app.utils.exceptions import BadRequestError, ConflictError, NotFoundError, PermissionDeniedError


class AgentCoreService:
    def __init__(self, session: AsyncSession):
        self.db = session
        self.session_repo = AgentSessionRepository(session)
        self.turn_repo = AgentTurnRepository(session)
        self.event_repo = AgentEventRepository(session)
        self.action_repo = AgentActionRepository(session)
        self.artifact_repo = AgentArtifactRepository(session)
        self.project_repo = ProjectRepository(session)
        self.ledger = AgentEventLedger(session)
        self.runtime = AgentCoreRuntime(session)

    async def create_session(
        self,
        *,
        project_id: str,
        workspace_id: str,
        user_id: str,
        title: str | None = None,
        role_profile: str = "bioinformatician",
        permission_mode: str = "guarded_auto",
        automation_mode: str = "assisted",
        default_model_profile_id: str | None = None,
        model_selection: dict | None = None,
        metadata: dict | None = None,
    ):
        project = await self.project_repo.get(project_id)
        if project is None:
            raise NotFoundError(f"Project not found: {project_id}")
        if str(project.workspace_id) != str(workspace_id):
            raise PermissionDeniedError("Project is not in the current workspace")

        return await self.session_repo.create(
            project_id=str(project.id),
            workspace_id=workspace_id,
            user_id=user_id,
            title=title,
            role_profile=role_profile,
            permission_mode=permission_mode,
            automation_mode=automation_mode,
            default_model_profile_id=default_model_profile_id,
            session_metadata=session_metadata_with_model_selection(
                metadata, model_selection
            ),
        )

    async def list_sessions(
        self,
        *,
        workspace_id: str,
        user_id: str,
        project_id: str | None = None,
    ):
        return await self.session_repo.list_for_user(
            workspace_id=workspace_id,
            user_id=user_id,
            project_id=project_id,
        )

    async def require_session(
        self,
        *,
        session_id: str,
        workspace_id: str,
        user_id: str,
    ):
        session = await self.session_repo.get(session_id)
        if session is None or session.status == AgentSessionStatus.DELETED:
            raise NotFoundError(f"Agent session not found: {session_id}")
        if str(session.workspace_id) != str(workspace_id) or str(session.user_id) != user_id:
            raise PermissionDeniedError("Agent session is not accessible")
        return session

    async def update_session(
        self,
        *,
        session_id: str,
        workspace_id: str,
        user_id: str,
        updates: dict[str, Any],
    ):
        session = await self.require_session(
            session_id=session_id,
            workspace_id=workspace_id,
            user_id=user_id,
        )
        update_data: dict[str, Any] = {}
        for key in (
            "title",
            "role_profile",
            "permission_mode",
            "automation_mode",
            "default_model_profile_id",
            "status",
        ):
            if key in updates:
                update_data[key] = updates[key]
        if "metadata" in updates or "model_selection" in updates:
            update_data["session_metadata"] = session_metadata_with_model_selection(
                session.session_metadata if hasattr(session, "session_metadata") else None,
                updates.get("model_selection"),
            )
            if "metadata" in updates:
                update_data["session_metadata"] = session_metadata_with_model_selection(
                    updates["metadata"], updates.get("model_selection")
                )
        return await self.session_repo.update_all(session, **update_data)

    async def delete_session(
        self,
        *,
        session_id: str,
        workspace_id: str,
        user_id: str,
    ) -> None:
        session = await self.require_session(
            session_id=session_id,
            workspace_id=workspace_id,
            user_id=user_id,
        )
        await self.session_repo.update_all(session, status=AgentSessionStatus.DELETED)

    async def create_turn(
        self,
        *,
        session_id: str,
        workspace_id: str,
        user_id: str,
        input_text: str,
        input_parts: list[dict] | None = None,
        model_profile_id: str | None = None,
        model_selection: dict | None = None,
        metadata: dict | None = None,
    ):
        session = await self.require_session(
            session_id=session_id,
            workspace_id=workspace_id,
            user_id=user_id,
        )
        turn = await self.turn_repo.create(
            session_id=str(session.id),
            project_id=str(session.project_id),
            workspace_id=str(session.workspace_id),
            user_id=user_id,
            input_text=input_text,
            input_parts=input_parts,
            status=AgentTurnStatus.QUEUED,
            model_profile_snapshot={
                "requested_model_profile_id": model_profile_id,
                "requested_model_selection": model_selection,
                "metadata": metadata or {},
            },
        )
        await self.ledger.append(
            session_id=str(session.id),
            turn_id=str(turn.id),
            type=AgentEventType.TURN_CREATED,
            payload={"input_text": input_text},
        )
        return await self.runtime.run_no_tool_turn(str(turn.id)) or turn

    async def list_turns(
        self,
        *,
        session_id: str,
        workspace_id: str,
        user_id: str,
    ):
        await self.require_session(
            session_id=session_id,
            workspace_id=workspace_id,
            user_id=user_id,
        )
        return await self.turn_repo.list_for_session(session_id)

    async def require_turn(
        self,
        *,
        turn_id: str,
        workspace_id: str,
        user_id: str,
    ):
        turn = await self.turn_repo.get(turn_id)
        if turn is None:
            raise NotFoundError(f"Agent turn not found: {turn_id}")
        await self.require_session(
            session_id=str(turn.session_id),
            workspace_id=workspace_id,
            user_id=user_id,
        )
        return turn

    async def cancel_turn(
        self,
        *,
        turn_id: str,
        workspace_id: str,
        user_id: str,
    ):
        turn = await self.require_turn(
            turn_id=turn_id,
            workspace_id=workspace_id,
            user_id=user_id,
        )
        now = datetime.now(timezone.utc)
        updated = await self.turn_repo.update_all(
            turn,
            status=AgentTurnStatus.CANCELLED,
            completed_at=now,
        )
        await self.ledger.append(
            session_id=str(turn.session_id),
            turn_id=str(turn.id),
            type=AgentEventType.TURN_CANCELLED,
            payload={},
        )
        return updated

    async def list_events_for_turn(
        self,
        *,
        turn_id: str,
        workspace_id: str,
        user_id: str,
        after_seq: int = 0,
    ):
        await self.require_turn(
            turn_id=turn_id,
            workspace_id=workspace_id,
            user_id=user_id,
        )
        return await self.event_repo.list_for_turn(turn_id=turn_id, after_seq=after_seq)

    async def list_events_for_session(
        self,
        *,
        session_id: str,
        workspace_id: str,
        user_id: str,
        after_seq: int = 0,
    ):
        await self.require_session(
            session_id=session_id,
            workspace_id=workspace_id,
            user_id=user_id,
        )
        return await self.event_repo.list_for_session(
            session_id=session_id,
            after_seq=after_seq,
        )

    async def decide_action(
        self,
        *,
        action_id: str,
        workspace_id: str,
        user_id: str,
        decision: str,
        note: str | None = None,
        modified_input: dict | None = None,
    ):
        action = await self.action_repo.get(action_id)
        if action is None:
            raise NotFoundError(f"Agent action not found: {action_id}")
        turn = await self.require_turn(
            turn_id=str(action.turn_id),
            workspace_id=workspace_id,
            user_id=user_id,
        )
        if action.status != AgentActionStatus.WAITING_DECISION:
            raise ConflictError(f"Agent action is not waiting for a decision: {action.status}")

        next_input = action.input
        if decision == "modify":
            if modified_input is None:
                raise BadRequestError("modified_input is required when decision is modify")
            next_input = modified_input

        status = (
            AgentActionStatus.REJECTED
            if decision == "reject"
            else AgentActionStatus.REQUESTED
        )
        updated = await self.action_repo.update_all(
            action,
            input=next_input,
            redacted_input=next_input,
            permission_decision={
                "decision": decision,
                "note": note,
                "modified_input": modified_input,
            },
            status=status,
        )
        await self.ledger.append(
            session_id=str(action.session_id),
            turn_id=str(action.turn_id),
            type=AgentEventType.ACTION_DECISION_RECORDED,
            payload={"action_id": str(action.id), "decision": decision, "note": note},
        )
        if decision in {"approve", "modify"} and updated.kind == "tool":
            result = await AgentToolDispatcher(
                self.db,
                build_default_tool_registry(),
            ).resume_action(
                action_id=str(updated.id),
                context=AgentToolContext(
                    db=self.db,
                    workspace_id=workspace_id,
                    user_id=user_id,
                    session_id=str(updated.session_id),
                    turn_id=str(turn.id),
                ),
            )
            resumed = await self.action_repo.get(result.action_id)
            if resumed is None:
                raise NotFoundError(f"Agent action not found after resume: {result.action_id}")
            return resumed
        return updated

    async def list_artifacts_for_session(
        self,
        *,
        session_id: str,
        workspace_id: str,
        user_id: str,
    ):
        await self.require_session(
            session_id=session_id,
            workspace_id=workspace_id,
            user_id=user_id,
        )
        return await self.artifact_repo.list_for_session(session_id)

    async def list_artifacts_for_turn(
        self,
        *,
        turn_id: str,
        workspace_id: str,
        user_id: str,
    ):
        turn = await self.require_turn(
            turn_id=turn_id,
            workspace_id=workspace_id,
            user_id=user_id,
        )
        return await self.artifact_repo.list_for_turn(str(turn.id))

    async def get_artifact(
        self,
        *,
        artifact_id: str,
        workspace_id: str,
        user_id: str,
    ):
        artifact = await self.artifact_repo.get(artifact_id)
        if artifact is None:
            raise NotFoundError(f"Agent artifact not found: {artifact_id}")
        await self.require_turn(
            turn_id=str(artifact.turn_id),
            workspace_id=workspace_id,
            user_id=user_id,
        )
        return artifact
