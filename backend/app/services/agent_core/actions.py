from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_core import AgentActionStatus
from app.repositories.agent_core_repo import AgentActionRepository, AgentTurnRepository
from app.services.agent_core.events import AgentEventType
from app.services.agent_core.ledger import AgentEventLedger
from app.services.agent_core.permissions import PermissionPolicy, RiskEngine
from app.services.agent_core.permissions.risk import RiskLevel
from app.utils.exceptions import NotFoundError


class AgentActionService:
    def __init__(self, session: AsyncSession):
        self.action_repo = AgentActionRepository(session)
        self.turn_repo = AgentTurnRepository(session)
        self.ledger = AgentEventLedger(session)
        self.risk_engine = RiskEngine()
        self.permission_policy = PermissionPolicy()

    async def request_action(
        self,
        *,
        turn_id: str,
        kind: str,
        name: str,
        input: dict | None = None,
        requested_risk: RiskLevel | None = None,
        permission_mode: str = "guarded_auto",
        automation_mode: str = "assisted",
        input_preview: str | None = None,
        read_scope: list | None = None,
        write_scope: list | None = None,
        rollback_hint: str | None = None,
        artifact_policy: dict | None = None,
    ):
        turn = await self.turn_repo.get(turn_id)
        if turn is None:
            raise NotFoundError(f"Agent turn not found: {turn_id}")

        action_input = input or {}
        risk = self.risk_engine.assess(
            kind=kind,
            name=name,
            requested_level=requested_risk,
            input=action_input,
        )
        decision = self.permission_policy.decide(
            risk=risk,
            permission_mode=permission_mode,  # type: ignore[arg-type]
            automation_mode=automation_mode,  # type: ignore[arg-type]
        )
        status = _status_for_decision(decision.decision)
        action = await self.action_repo.create(
            session_id=str(turn.session_id),
            turn_id=str(turn.id),
            kind=kind,
            name=name,
            input=action_input,
            input_preview=input_preview,
            redacted_input=action_input,
            risk_level=risk.level,
            risk_reasons=risk.reasons,
            read_scope=read_scope,
            write_scope=write_scope,
            affected_resources=risk.affected_resources,
            permission_decision=decision.as_dict(),
            status=status,
            rollback_hint=rollback_hint,
            artifact_policy=artifact_policy,
        )
        await self.ledger.append(
            session_id=str(turn.session_id),
            turn_id=str(turn.id),
            type=AgentEventType.ACTION_REQUESTED,
            payload={"action_id": str(action.id), "kind": kind, "name": name},
        )
        await self.ledger.append(
            session_id=str(turn.session_id),
            turn_id=str(turn.id),
            type=AgentEventType.ACTION_RISK_ASSESSED,
            payload={
                "action_id": str(action.id),
                "risk_level": risk.level,
                "reasons": risk.reasons,
            },
        )
        if decision.decision == "ask":
            await self.ledger.append(
                session_id=str(turn.session_id),
                turn_id=str(turn.id),
                type=AgentEventType.ACTION_WAITING_DECISION,
                payload={"action_id": str(action.id)},
            )
        return action


def _status_for_decision(decision: str) -> str:
    if decision == "ask":
        return AgentActionStatus.WAITING_DECISION
    if decision == "deny":
        return AgentActionStatus.REJECTED
    return AgentActionStatus.REQUESTED
