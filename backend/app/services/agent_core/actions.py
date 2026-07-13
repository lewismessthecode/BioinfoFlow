from __future__ import annotations

import json

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_core import AgentActionStatus
from app.repositories.agent_core_repo import AgentActionRepository, AgentTurnRepository
from app.services.agent_core.events import AgentEventType
from app.services.agent_core.ledger import AgentEventLedger
from app.services.agent_core.permissions import PermissionPolicy, RiskEngine
from app.services.agent_core.permissions.policy import PermissionDecision
from app.services.agent_core.permissions.risk import RiskAssessment, RiskLevel
from app.services.agent_core.permissions.command_risk import CommandRiskAssessment
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
        normalized_input: dict | None = None,
        requested_risk: RiskLevel | RiskAssessment | None = None,
        permission_mode: str = "guarded_auto",
        automation_mode: str = "assisted",
        input_preview: str | None = None,
        read_scope: list | None = None,
        write_scope: list | None = None,
        rollback_hint: str | None = None,
        artifact_policy: dict | None = None,
        tool_call_id: str | None = None,
        tool_batch_id: str | None = None,
        tool_call_ordinal: int | None = None,
        exposure_policy: dict | None = None,
        force_ask: bool = False,
        interaction: str | None = None,
        evaluated_policy_version: int | None = None,
        permission_context_snapshot: dict | None = None,
        commit: bool = True,
    ):
        turn = await self.turn_repo.get(turn_id)
        if turn is None:
            raise NotFoundError(f"Agent turn not found: {turn_id}")

        action_input = input or {}
        risk = (
            requested_risk
            if isinstance(requested_risk, RiskAssessment)
            else self.risk_engine.assess(
                kind=kind,
                name=name,
                requested_level=requested_risk,
                input=action_input,
            )
        )
        if force_ask:
            # Interaction tools (ask_user, exit_plan_mode) pause for the user
            # regardless of permission_mode — bypassing the risk-based policy.
            decision = PermissionDecision(
                decision="ask",
                reasons=[f"{interaction or 'interaction'} requires the user's input"],
                risk_level=risk.level,
            )
        else:
            decision = self.permission_policy.decide(
                risk=risk,
                permission_mode=permission_mode,  # type: ignore[arg-type]
                automation_mode=automation_mode,  # type: ignore[arg-type]
            )
        status = _status_for_decision(decision.decision)
        if input_preview is None:
            input_preview = _input_preview(name=name, action_input=action_input)
        create = self.action_repo.create if commit else self.action_repo.add
        decision_payload = {
            **decision.as_dict(),
            "source": "policy",
            "requires_explicit_approval": risk.requires_explicit_approval,
        }
        action = await create(
            session_id=str(turn.session_id),
            turn_id=str(turn.id),
            kind=kind,
            name=name,
            tool_call_id=tool_call_id,
            tool_batch_id=tool_batch_id,
            tool_call_ordinal=tool_call_ordinal,
            input=action_input,
            normalized_input=normalized_input,
            input_preview=input_preview,
            redacted_input=action_input,
            exposure_policy=exposure_policy,
            risk_level=risk.level,
            risk_reasons=risk.reasons,
            read_scope=read_scope,
            write_scope=write_scope,
            affected_resources=risk.affected_resources,
            permission_decision=decision_payload,
            evaluated_policy_version=evaluated_policy_version,
            permission_context_snapshot=permission_context_snapshot,
            status=status,
            rollback_hint=rollback_hint,
            artifact_policy=artifact_policy,
        )
        await self.ledger.append(
            session_id=str(turn.session_id),
            turn_id=str(turn.id),
            type=AgentEventType.ACTION_REQUESTED,
            payload={
                "action_id": str(action.id),
                "kind": kind,
                "name": name,
                "evaluated_policy_version": evaluated_policy_version,
            },
            commit=commit,
        )
        risk_event_payload: dict = {
            "action_id": str(action.id),
            "risk_level": risk.level,
            "reasons": risk.reasons,
            "evaluated_policy_version": evaluated_policy_version,
        }
        if isinstance(risk, CommandRiskAssessment):
            risk_event_payload.update(
                {
                    "target": risk.target,
                    "effects": risk.effects,
                    "confidence": risk.confidence,
                    "protected_resources": risk.protected_resources,
                    "hard_blocked": risk.hard_blocked,
                    "assessment_fingerprint": risk.assessment_fingerprint(),
                }
            )
        await self.ledger.append(
            session_id=str(turn.session_id),
            turn_id=str(turn.id),
            type=AgentEventType.ACTION_RISK_ASSESSED,
            payload=risk_event_payload,
            commit=commit,
        )
        if decision.decision == "ask":
            # Enrich the waiting-decision event so the frontend renders the
            # approval / question / plan card without a second fetch.
            payload: dict = {
                "action_id": str(action.id),
                "name": name,
                "kind": kind,
                "risk_level": risk.level,
                "tool_call_id": tool_call_id,
                "input_preview": input_preview,
                "evaluated_policy_version": evaluated_policy_version,
            }
            block = _interaction_block(interaction, action_input)
            if block is not None:
                payload["interaction"] = block
            await self.ledger.append(
                session_id=str(turn.session_id),
                turn_id=str(turn.id),
                type=AgentEventType.ACTION_WAITING_DECISION,
                payload=payload,
                commit=commit,
            )
        return action


def _interaction_block(interaction: str | None, action_input: dict) -> dict | None:
    """Shape the interaction payload the frontend renders for the card.

    ``user_input`` surfaces the ask_user questions; ``plan_approval`` surfaces
    the proposed plan text. Other (risk-gated) approvals have no interaction
    block — the generic approval card uses name + preview + risk.
    """
    if interaction == "user_input":
        questions = action_input.get("questions")
        return {
            "kind": "user_input",
            "questions": questions if isinstance(questions, list) else [],
        }
    if interaction == "plan_approval":
        return {"kind": "plan_approval", "plan": str(action_input.get("plan") or "")}
    return None


def _input_preview(*, name: str, action_input: dict) -> str | None:
    """A short, human-readable preview of a tool call's input.

    Upgrades the approval card from a bare UUID to something legible: the
    command for bash, the path for file tools, otherwise a truncated JSON dump.
    """
    if not isinstance(action_input, dict) or not action_input:
        return None
    for key in ("command", "path", "objective", "task", "plan", "query"):
        value = action_input.get(key)
        if isinstance(value, str) and value.strip():
            return _truncate(value.strip(), 200)
    try:
        return _truncate(
            json.dumps(
                action_input, ensure_ascii=False, separators=(",", ":"), default=str
            ),
            200,
        )
    except (TypeError, ValueError):
        return None


def _truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _status_for_decision(decision: str) -> str:
    if decision == "ask":
        return AgentActionStatus.WAITING_DECISION
    if decision == "deny":
        return AgentActionStatus.REJECTED
    return AgentActionStatus.REQUESTED
