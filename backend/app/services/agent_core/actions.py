from __future__ import annotations

import json

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_core import AgentActionStatus
from app.repositories.agent_core_repo import AgentActionRepository, AgentTurnRepository
from app.services.agent_core.events import AgentEventType
from app.services.agent_core.ledger import AgentEventLedger
from app.services.agent_core.ownership import TurnOwnershipLostError
from app.services.agent_core.permissions import PermissionPolicy, RiskEngine
from app.services.agent_core.permissions.policy import PermissionDecision
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
        normalized_input: dict | None = None,
        requested_risk: RiskLevel | None = None,
        permission_mode: str = "guarded_auto",
        automation_mode: str = "assisted",
        input_preview: str | None = None,
        read_scope: list | None = None,
        write_scope: list | None = None,
        rollback_hint: str | None = None,
        artifact_policy: dict | None = None,
        tool_call_id: str | None = None,
        exposure_policy: dict | None = None,
        force_ask: bool = False,
        interaction: str | None = None,
        expected_owner_token: str | None = None,
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
        action_data = {
            "session_id": str(turn.session_id),
            "kind": kind,
            "name": name,
            "tool_call_id": tool_call_id,
            "input": action_input,
            "normalized_input": normalized_input,
            "input_preview": input_preview,
            "redacted_input": action_input,
            "exposure_policy": exposure_policy,
            "risk_level": risk.level,
            "risk_reasons": risk.reasons,
            "read_scope": read_scope,
            "write_scope": write_scope,
            "affected_resources": risk.affected_resources,
            "permission_decision": decision.as_dict(),
            "status": status,
            "rollback_hint": rollback_hint,
            "artifact_policy": artifact_policy,
        }
        if expected_owner_token is None:
            action = await self.action_repo.create(
                turn_id=str(turn.id),
                **action_data,
            )
        else:
            action, owned = await self.action_repo.create_for_owned_turn(
                turn_id=str(turn.id),
                expected_owner_token=expected_owner_token,
                **action_data,
            )
            if not owned or action is None:
                raise TurnOwnershipLostError("Agent turn ownership was replaced")
        await self.ledger.append(
            session_id=str(turn.session_id),
            turn_id=str(turn.id),
            type=AgentEventType.ACTION_REQUESTED,
            payload={"action_id": str(action.id), "kind": kind, "name": name},
            expected_owner_token=expected_owner_token,
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
            expected_owner_token=expected_owner_token,
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
            }
            block = _interaction_block(interaction, action_input)
            if block is not None:
                payload["interaction"] = block
            await self.ledger.append(
                session_id=str(turn.session_id),
                turn_id=str(turn.id),
                type=AgentEventType.ACTION_WAITING_DECISION,
                payload=payload,
                expected_owner_token=expected_owner_token,
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
