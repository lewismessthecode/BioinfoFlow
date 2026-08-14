from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal

from app.services.model_runtime.contracts import (
    InputPart,
    ModelTarget,
    ResponsesContinuation,
)


RecoverySource = Literal["checkpoint", "history"]
RecoveryAction = Literal["retry", "verify", "ask_user"]


@dataclass(frozen=True)
class ToolRecovery:
    call_id: str
    name: str
    action: RecoveryAction


@dataclass(frozen=True)
class RecoveryInteraction:
    interaction_id: str
    request: dict[str, Any]


@dataclass(frozen=True)
class RecoveryPlan:
    source: RecoverySource
    resume_phase: str
    history_revision: int
    tools: tuple[ToolRecovery, ...] = ()
    requires_user: bool = False
    notice: str | None = None
    interaction: RecoveryInteraction | None = None
    private_state: Mapping[str, Any] | None = None


class RecoveryPlanner:
    """Use private state only when its version and history fence are trustworthy."""

    def __init__(self, *, harness_version: str):
        self.harness_version = harness_version

    def plan(
        self,
        *,
        checkpoint: Mapping[str, Any] | None,
        history_revision: int,
    ) -> RecoveryPlan:
        fallback_notice = self._invalid_reason(checkpoint, history_revision)
        if fallback_notice is not None:
            return RecoveryPlan(
                source="history",
                resume_phase="model",
                history_revision=history_revision,
                notice=fallback_notice,
            )
        assert checkpoint is not None
        tools = tuple(
            self._tool_recovery(item) for item in checkpoint.get("in_flight_tools", ())
        )
        requires_user = any(item.action == "ask_user" for item in tools)
        interaction = _bash_recovery_interaction(tools) if requires_user else None
        return RecoveryPlan(
            source="checkpoint",
            resume_phase=str(checkpoint["phase"]),
            history_revision=history_revision,
            tools=tools,
            requires_user=requires_user,
            notice=(
                "The previous process stopped after bash may have started but before "
                "its result was saved. It will not be run again automatically."
                if requires_user
                else None
            ),
            interaction=interaction,
            private_state=checkpoint,
        )

    def _invalid_reason(
        self,
        checkpoint: Mapping[str, Any] | None,
        history_revision: int,
    ) -> str | None:
        if not isinstance(checkpoint, Mapping):
            return "Recovery state was unavailable; continuing from saved history."
        if checkpoint.get("harness_version") != self.harness_version:
            return (
                "Recovery state belongs to a different harness version; continuing "
                "from saved history."
            )
        if checkpoint.get("schema_version") != 1:
            return "Recovery state was invalid; continuing from saved history."
        checkpoint_revision = checkpoint.get("history_revision")
        phase = checkpoint.get("phase")
        tools = checkpoint.get("in_flight_tools", [])
        if (
            not isinstance(checkpoint_revision, int)
            or isinstance(checkpoint_revision, bool)
            or checkpoint_revision != history_revision
            or phase not in {"model", "tools", "interaction", "compression", "terminal"}
            or not isinstance(tools, list)
            or any(not self._valid_tool(item) for item in tools)
        ):
            return "Recovery state was invalid; continuing from saved history."
        return None

    def _valid_tool(self, value: Any) -> bool:
        if not isinstance(value, Mapping):
            return False
        call_id = value.get("call_id")
        name = value.get("name")
        policy = value.get("replay_policy")
        arguments = value.get("arguments")
        if not (
            isinstance(call_id, str)
            and call_id
            and isinstance(name, str)
            and name
            and isinstance(arguments, Mapping)
        ):
            return False
        allowed_policies = {
            "read": {"safe"},
            "edit": {"verify"},
            "write": {"verify"},
            "bash": {"never"},
            "ask_user": {"safe"},
        }
        return policy in allowed_policies.get(name, set())

    def _tool_recovery(self, value: Mapping[str, Any]) -> ToolRecovery:
        action: RecoveryAction = {
            "safe": "retry",
            "verify": "verify",
            "never": "ask_user",
        }[str(value["replay_policy"])]
        return ToolRecovery(
            call_id=str(value["call_id"]),
            name=str(value["name"]),
            action=action,
        )


def create_checkpoint(
    *,
    harness_version: str,
    phase: str,
    history_revision: int,
    input_queue: tuple[Mapping[str, Any], ...] = (),
    continuation: Mapping[str, Any] | None = None,
    draft: Mapping[str, Any] | None = None,
    in_flight_tools: tuple[Mapping[str, Any], ...] = (),
    interaction: Mapping[str, Any] | None = None,
    compaction_through: int | None = None,
    budget: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if phase not in {"model", "tools", "interaction", "compression", "terminal"}:
        raise ValueError(f"invalid recovery phase: {phase}")
    if history_revision < 0:
        raise ValueError("history_revision must be non-negative")
    return {
        "schema_version": 1,
        "harness_version": harness_version,
        "phase": phase,
        "history_revision": history_revision,
        "input_queue": [dict(item) for item in input_queue],
        "continuation": dict(continuation) if continuation is not None else None,
        "draft": dict(draft) if draft is not None else None,
        "in_flight_tools": [dict(item) for item in in_flight_tools],
        "interaction": dict(interaction) if interaction is not None else None,
        "compaction_through": compaction_through,
        "budget": dict(budget) if budget is not None else None,
    }


def responses_continuation_from_checkpoint(
    checkpoint: Mapping[str, Any] | None,
    *,
    target: ModelTarget,
    input_items: tuple[InputPart, ...],
) -> ResponsesContinuation | None:
    """Restore only a continuation fenced to this exact target and input prefix."""

    if target.wire_protocol != "responses" or not isinstance(checkpoint, Mapping):
        return None
    continuation = ResponsesContinuation.from_private_dict(
        checkpoint.get("continuation")
    )
    if continuation is None:
        return None
    if not continuation.matches_target(target):
        return None
    if not continuation.matches_canonical_input(input_items):
        return None
    return continuation


def _bash_recovery_interaction(
    tools: tuple[ToolRecovery, ...],
) -> RecoveryInteraction | None:
    bash = next(
        (item for item in tools if item.name == "bash" and item.action == "ask_user"),
        None,
    )
    if bash is None:
        return None
    return RecoveryInteraction(
        interaction_id=f"recovery:{bash.call_id}",
        request={
            "kind": "recovery",
            "call_id": bash.call_id,
            "tool_name": "bash",
            "message": (
                "The previous process stopped after this Bash command may have started "
                "but before its result was saved. Choose how to continue."
            ),
            "options": [
                {
                    "id": "inspect",
                    "label": "Inspect state",
                    "description": "Check the workspace state before continuing.",
                },
                {
                    "id": "retry",
                    "label": "Retry command",
                    "description": "Explicitly allow this Bash command to run again.",
                },
                {
                    "id": "cancel",
                    "label": "Cancel run",
                    "description": "Stop this run without replaying the command.",
                },
            ],
        },
    )
