from __future__ import annotations

from typing import Any

from pydantic import TypeAdapter

from app.models.agent_harness import AgentHarnessEntry, AgentHarnessRun
from app.services.agent_harness.contracts import (
    HistoryEntry,
    PendingInteractionView,
    RunView,
)
from app.services.agent_harness.tool_projection import (
    public_error_message,
    public_result_details,
    public_tool_details,
)


_PUBLIC_RUN_ERROR_MESSAGES = {
    "agent_failed": "The Agent run failed.",
    "invalid_plan": "The Agent produced an invalid plan.",
    "iteration_limit": "The Agent reached its iteration limit.",
    "model_attempt_timeout": "The model did not respond before the attempt timed out.",
    "model_vision_unsupported": "The selected model does not support image input.",
    "no_progress": "The Agent stopped after repeating the same tool calls.",
    "run_timeout_exceeded": "The Agent run reached its time limit.",
    "runtime_failed": "The Agent runtime stopped unexpectedly.",
    "token_budget_exceeded": "The Agent run reached its token limit.",
}
_history_entry_adapter = TypeAdapter(HistoryEntry)


def _public_interaction_options(values: Any) -> list[dict[str, Any]]:
    options: list[dict[str, Any]] = []
    for index, raw in enumerate(values if isinstance(values, list) else []):
        if not isinstance(raw, dict):
            continue
        label = str(raw.get("label") or raw.get("id") or f"Option {index + 1}")
        options.append(
            {
                "id": str(raw.get("id") or label),
                "label": label,
                "description": str(raw.get("description") or ""),
                "recommended": bool(raw.get("recommended", False)),
            }
        )
    if len(options) >= 2:
        return options
    return [
        {
            "id": "continue",
            "label": "Continue",
            "description": "Continue working",
            "recommended": True,
        },
        {
            "id": "cancel",
            "label": "Cancel",
            "description": "Stop here",
            "recommended": False,
        },
    ]


def public_interaction_request(value: dict[str, Any]) -> dict[str, Any]:
    kind = value.get("kind")
    call_id = str(value.get("call_id") or "interaction")
    if kind == "question":
        questions: list[dict[str, Any]] = []
        for index, raw in enumerate(value.get("questions") or []):
            question = raw if isinstance(raw, dict) else {"question": str(raw)}
            header = str(question.get("header") or f"Question {index + 1}")
            questions.append(
                {
                    "id": str(question.get("id") or header),
                    "header": header,
                    "question": str(question.get("question") or ""),
                    "multi_select": bool(
                        question.get("multi_select", question.get("multiSelect", False))
                    ),
                    "options": _public_interaction_options(question.get("options")),
                }
            )
        return {"type": "ask_user", "call_id": call_id, "questions": questions}
    if kind == "confirmation":
        risk = value.get("risk") if isinstance(value.get("risk"), dict) else {}
        resources = risk.get("affected_resources") or risk.get("referenced_paths") or []
        allowed_responses = value.get("allowed_responses")
        if allowed_responses is None:
            allowed_responses = ["approve", "reject"]
        return {
            "type": "approval",
            "call_id": call_id,
            "tool_name": str(value.get("tool_name") or "tool"),
            "summary": str(value.get("summary") or "Allow this tool to run?"),
            "input_preview": value.get("input_preview"),
            "allowed_responses": allowed_responses,
            "risk": {
                "level": str(risk.get("level") or "unknown"),
                "effects": [str(item) for item in risk.get("effects") or []],
                "reasons": [str(item) for item in risk.get("reasons") or []],
                "affected_resources": [
                    str(item.get("id") if isinstance(item, dict) else item)
                    for item in resources
                ],
            },
        }
    if kind == "recovery":
        return {
            "type": "recovery",
            "call_id": call_id,
            "tool_name": str(value.get("tool_name") or "tool"),
            "message": str(value.get("message") or "Recovery requires a decision."),
            "options": _public_interaction_options(value.get("options")),
        }
    raise ValueError(f"unsupported interaction kind: {kind}")


def public_interaction_response(value: dict[str, Any]) -> dict[str, Any]:
    response_type = value.get("type")
    if response_type == "ask_user" or "answers" in value:
        return {"type": "ask_user", "answers": value.get("answers") or {}}
    if response_type == "approval" or "approved" in value:
        return {"type": "approval", "approved": value.get("approved") is True}
    if response_type == "recovery" or value.get("choice") in {
        "inspect",
        "retry",
        "cancel",
    }:
        return {"type": "recovery", "choice": value.get("choice")}
    raise ValueError("unsupported interaction response")


def public_model_summary(snapshot: dict[str, Any] | None) -> dict[str, Any]:
    private = snapshot if isinstance(snapshot, dict) else {}
    target = private.get("target")
    target = target if isinstance(target, dict) else {}
    capabilities = private.get("capabilities")
    capabilities = capabilities if isinstance(capabilities, dict) else {}
    provider = str(target.get("provider_kind") or "unknown")
    model = str(target.get("model_name") or "unknown")
    display_name = str(private.get("display_name") or model)
    return {
        "provider": provider,
        "model": model,
        "display_name": display_name,
        "supports_vision": bool(capabilities.get("supports_vision", False)),
        "supports_reasoning": bool(capabilities.get("supports_reasoning", False)),
        "supports_tools": bool(capabilities.get("supports_tools", False)),
    }


def public_run_error(run: AgentHarnessRun) -> dict[str, str] | None:
    if run.status != "failed":
        return None
    private = run.error if isinstance(run.error, dict) else {}
    candidates = (run.termination_reason, private.get("code"))
    code = next(
        (
            candidate
            for candidate in candidates
            if isinstance(candidate, str)
            and candidate in _PUBLIC_RUN_ERROR_MESSAGES
        ),
        "agent_failed",
    )
    return {"code": code, "message": _PUBLIC_RUN_ERROR_MESSAGES[code]}


def run_view(run: AgentHarnessRun) -> RunView:
    return RunView.model_validate(
        {
            "id": run.id,
            "session_id": run.session_id,
            "status": run.status,
            "phase": run.phase,
            "revision": run.revision,
            "started_at": run.started_at,
            "completed_at": run.completed_at,
            "termination_reason": run.termination_reason,
            "error": public_run_error(run),
            "created_at": run.created_at,
            "updated_at": run.updated_at,
        }
    )


def entry_contract(entry: AgentHarnessEntry) -> HistoryEntry:
    return _history_entry_adapter.validate_python(
        {
            "id": entry.id,
            "session_id": entry.session_id,
            "run_id": entry.run_id,
            "sequence": entry.sequence,
            "type": entry.type,
            "schema_version": entry.schema_version,
            "payload": _public_entry_payload(entry.type, entry.payload),
            "created_at": entry.created_at,
        }
    )


def _public_entry_payload(entry_type: str, payload: Any) -> Any:
    if entry_type != "message" or not isinstance(payload, dict):
        return payload
    return {
        **payload,
        "parts": [
            _public_message_part(part)
            for part in payload.get("parts") or []
            if isinstance(part, dict)
        ],
    }


def _public_message_part(part: dict[str, Any]) -> dict[str, Any]:
    part_type = part.get("type")
    if part_type == "tool_call":
        name = str(part.get("name") or "unknown")
        arguments = part.get("arguments")
        arguments = arguments if isinstance(arguments, dict) else {}
        summary = public_error_message(str(part.get("summary") or "Tool activity"))
        if name == "bash":
            description = arguments.get("description")
            summary = "Run command"
            if isinstance(description, str) and description.strip():
                public_description = public_error_message(description.strip())
                if public_description:
                    summary = f"{summary}: {public_description}"
        return {
            **part,
            "summary": summary or "Tool activity",
            "arguments": {},
            "public_details": [
                detail.model_dump(mode="json")
                for detail in public_tool_details(name, arguments)
            ],
        }
    if part_type == "tool_result":
        error = public_error_message(
            str(part.get("error")) if part.get("error") else None
        )
        return {
            **part,
            "summary": None,
            "output": _public_tool_output(part.get("output")),
            "error": error,
            "public_details": [
                detail.model_dump(mode="json")
                for detail in public_result_details(error=error)
            ],
        }
    return part


def _public_tool_output(output: Any) -> dict[str, Any] | None:
    if not isinstance(output, dict) or output.get("type") != "content_parts":
        return None
    safe_types = {
        "attachment_ref",
        "file_ref",
        "directory_ref",
        "workflow_ref",
        "run_ref",
        "artifact_ref",
    }
    parts = [
        part
        for part in output.get("parts") or []
        if isinstance(part, dict) and part.get("type") in safe_types
    ]
    return {"type": "content_parts", "parts": parts} if parts else None


def pending_interaction_entry_view(
    entry: AgentHarnessEntry,
) -> PendingInteractionView:
    if entry.run_id is None or entry.type != "interaction_request":
        raise ValueError("pending interaction requires a Run request entry")
    return PendingInteractionView(
        interaction_id=str(entry.payload["interaction_id"]),
        run_id=entry.run_id,
        revision=entry.sequence,
        request=dict(entry.payload.get("request") or {}),
    )


__all__ = [
    "entry_contract",
    "pending_interaction_entry_view",
    "public_interaction_request",
    "public_interaction_response",
    "public_model_summary",
    "public_run_error",
    "run_view",
]
