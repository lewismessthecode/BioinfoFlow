"""migrate agent harness public state to schema v2

Revision ID: 0060_agent_harness_public_revisions
Revises: 0059_complete_agent_harness
Create Date: 2026-08-15
"""

from __future__ import annotations

import json
from typing import Any

import sqlalchemy as sa
from alembic import op


revision = "0060_agent_harness_public_revisions"
down_revision = "0059_complete_agent_harness"
branch_labels = None
depends_on = None


PRIVATE_INTERACTION_KEYS = {
    "assessment_fingerprint",
    "base_assessment_fingerprint",
    "cwd_identity",
    "replay_policy",
    "checkpoint",
}


def _load_json(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return default
    return value


def _tool_category(name: str) -> str:
    return {
        "read": "read",
        "bash": "command",
        "edit": "edit",
        "write": "write",
        "ask_user": "interaction",
        "update_plan": "plan",
    }.get(name, "other")


def _tool_summary(name: str, arguments: dict[str, Any]) -> str:
    subject = arguments.get("path") or arguments.get("command")
    return f"{name}: {subject}" if isinstance(subject, str) and subject else name


def _attachment_part(
    attachment_id: Any,
    *,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    if not isinstance(attachment_id, str) or not attachment_id:
        return None
    source = metadata if isinstance(metadata, dict) else {}
    return {
        "id": f"attachment:{attachment_id}",
        "type": "attachment_ref",
        "attachment_id": attachment_id,
        "filename": str(source.get("filename") or "Attachment"),
        "kind": str(source.get("kind") or "file"),
        "mime_type": source.get("mime_type"),
        "size_bytes": int(source.get("size_bytes") or 0),
    }


def _attachment_lookup(bind: sa.Connection) -> dict[tuple[str, str], dict[str, Any]]:
    table = sa.Table(
        "agent_attachments",
        sa.MetaData(),
        autoload_with=bind,
        resolve_fks=False,
    )
    return {
        (str(row.session_id), str(row.id)): dict(row._mapping)
        for row in bind.execute(sa.select(table)).all()
    }


def _command_parts(
    command: dict[str, Any],
    *,
    session_id: str,
    attachments: dict[tuple[str, str], dict[str, Any]],
) -> list[dict[str, Any]]:
    existing = command.get("parts")
    if isinstance(existing, list):
        return [
            normalized
            for part in existing
            if isinstance(part, dict)
            and (normalized := _input_command_part(part)) is not None
        ]
    parts: list[dict[str, Any]] = []
    text = command.get("text")
    if isinstance(text, str):
        parts.append({"type": "text", "text": text})
    seen: set[str] = set()
    for raw_id in command.get("attachment_ids") or []:
        attachment_id = str(raw_id)
        if not attachment_id or attachment_id in seen:
            continue
        seen.add(attachment_id)
        if (session_id, attachment_id) in attachments:
            parts.append(
                {"type": "attachment_ref", "attachment_id": attachment_id}
            )
    return parts


def _input_command_part(part: dict[str, Any]) -> dict[str, Any] | None:
    part_type = part.get("type")
    if part_type == "text" and isinstance(part.get("text"), str):
        return {"type": "text", "text": part["text"]}
    if part_type == "attachment_ref" and part.get("attachment_id"):
        return {
            "type": "attachment_ref",
            "attachment_id": str(part["attachment_id"]),
        }
    if part_type in {"file_ref", "directory_ref"}:
        if part.get("attachment_id"):
            return {
                "type": part_type,
                "attachment_id": str(part["attachment_id"]),
            }
        if part.get("project_id") and part.get("path"):
            return {
                "type": part_type,
                "project_id": str(part["project_id"]),
                "path": str(part["path"]),
            }
    if part_type == "workflow_ref" and part.get("workflow_id"):
        project_id = part.get("project_id")
        return {
            "type": "workflow_ref",
            "workflow_id": str(part["workflow_id"]),
            "scope": "project" if project_id else "global",
            **({"project_id": str(project_id)} if project_id else {}),
        }
    if part_type == "run_ref" and part.get("run_id"):
        return {"type": "run_ref", "run_id": str(part["run_id"])}
    return None


def _normalize_command_queue(
    value: Any,
    *,
    session_id: str,
    attachments: dict[tuple[str, str], dict[str, Any]],
) -> list[dict[str, Any]]:
    commands = _load_json(value, [])
    if not isinstance(commands, list):
        return []
    normalized: list[dict[str, Any]] = []
    for raw in commands:
        if not isinstance(raw, dict):
            continue
        command = dict(raw)
        kind = command.get("type")
        if kind in {"prompt", "follow_up", "message", "steer"}:
            normalized.append(
                {
                    "type": "message" if kind in {"prompt", "follow_up"} else kind,
                    "command_id": str(command.get("command_id") or "migrated-command"),
                    "parts": _command_parts(
                        command,
                        session_id=session_id,
                        attachments=attachments,
                    ),
                }
            )
            continue
        if kind == "respond":
            response = command.get("response", command.get("payload"))
            normalized.append(
                {
                    "type": "respond",
                    "command_id": str(command.get("command_id") or "migrated-command"),
                    "interaction_id": str(command.get("interaction_id") or "interaction"),
                    "response": _normalize_interaction_response(response),
                }
            )
            continue
        normalized.append(command)
    return normalized


def _message_parts(
    payload: dict[str, Any],
    *,
    entry_id: str,
    session_id: str,
    attachments: dict[tuple[str, str], dict[str, Any]],
) -> list[dict[str, Any]]:
    existing = payload.get("parts")
    if isinstance(existing, list):
        return [dict(part) for part in existing if isinstance(part, dict)]

    raw_content = payload.get("content")
    content = raw_content if isinstance(raw_content, list) else []
    text_values = [
        str(part.get("text"))
        for part in content
        if isinstance(part, dict)
        and part.get("type") == "text"
        and isinstance(part.get("text"), str)
    ]
    if isinstance(raw_content, str):
        text_values.insert(0, raw_content)
    text = "\n".join(value for value in text_values if value)
    role = str(payload.get("role") or "user")
    parts: list[dict[str, Any]] = []

    if role == "tool":
        call_id = payload.get("call_id") or payload.get("tool_call_id")
        if isinstance(call_id, str) and call_id:
            parsed: Any = text or None
            if text:
                try:
                    parsed = json.loads(text)
                except (TypeError, ValueError):
                    parsed = text
            output = None
            if isinstance(parsed, str):
                output = {"type": "text", "text": parsed}
            elif parsed is not None:
                output = {"type": "json", "value": parsed}
            failed = bool(payload.get("is_error"))
            parts.append(
                {
                    "id": f"tool-result:{call_id}",
                    "type": "tool_result",
                    "call_id": call_id,
                    "status": "failed" if failed else "completed",
                    "output": output,
                    "error": text if failed else None,
                }
            )
        elif text:
            parts.append(
                {
                    "id": "unknown:legacy-tool-result",
                    "type": "unknown",
                    "original_type": "legacy_tool_result",
                    "display_text": text,
                }
            )
        return parts

    reasoning = payload.get("reasoning_summary")
    if isinstance(reasoning, str) and reasoning:
        parts.append(
            {
                "id": "reasoning:0",
                "type": "reasoning_summary",
                "text": reasoning,
            }
        )
    if text:
        parts.append({"id": "text:0", "type": "text", "text": text})

    calls = [
        call for call in payload.get("tool_calls") or [] if isinstance(call, dict)
    ]
    execution_mode = "serial"
    if calls and all(call.get("execution_mode") == "parallel" for call in calls):
        execution_mode = "parallel"
    elif calls and any(call.get("execution_mode") == "parallel" for call in calls):
        execution_mode = "mixed"
    for call in calls:
        call_id = call.get("call_id") or call.get("id")
        name = call.get("name")
        if not isinstance(call_id, str) or not isinstance(name, str):
            continue
        arguments = call.get("arguments")
        safe_arguments = arguments if isinstance(arguments, dict) else {}
        parts.append(
            {
                "id": f"tool-call:{call_id}",
                "type": "tool_call",
                "call_id": call_id,
                "group_id": entry_id,
                "execution_mode": call.get("execution_mode") or execution_mode,
                "name": name,
                "display_name": str(call.get("display_name") or name),
                "category": str(call.get("category") or _tool_category(name)),
                "summary": str(call.get("summary") or _tool_summary(name, safe_arguments)),
                "arguments": safe_arguments,
            }
        )

    seen_attachments: set[str] = set()
    for raw_part in content:
        if not isinstance(raw_part, dict) or raw_part.get("type") not in {
            "attachment",
            "attachment_ref",
        }:
            continue
        attachment_id = raw_part.get("attachment_id")
        if not isinstance(attachment_id, str) or attachment_id in seen_attachments:
            continue
        seen_attachments.add(attachment_id)
        metadata = {
            **attachments.get((session_id, attachment_id), {}),
            **raw_part,
        }
        part = _attachment_part(attachment_id, metadata=metadata)
        if part is not None:
            parts.append(part)
    for raw_id in payload.get("attachment_ids") or []:
        attachment_id = str(raw_id)
        if not attachment_id or attachment_id in seen_attachments:
            continue
        seen_attachments.add(attachment_id)
        part = _attachment_part(
            attachment_id,
            metadata=attachments.get((session_id, attachment_id)),
        )
        if part is not None:
            parts.append(part)
    for raw_id in payload.get("artifact_ids") or []:
        artifact_id = str(raw_id)
        if artifact_id:
            parts.append(
                {
                    "id": f"artifact:{artifact_id}",
                    "type": "artifact_ref",
                    "artifact_id": artifact_id,
                }
            )
    return parts


def _normalize_message_payload(
    value: Any,
    *,
    entry_id: str,
    session_id: str,
    attachments: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, Any]:
    payload = _load_json(value, {})
    if not isinstance(payload, dict):
        payload = {}
    return {
        "role": str(payload.get("role") or "user"),
        "parts": _message_parts(
            payload,
            entry_id=entry_id,
            session_id=session_id,
            attachments=attachments,
        ),
    }


def _public_risk(value: Any) -> dict[str, Any]:
    risk = value if isinstance(value, dict) else {}
    resources = risk.get("affected_resources") or risk.get("referenced_paths") or []
    return {
        "level": str(risk.get("level") or "unknown"),
        "effects": [str(item) for item in risk.get("effects") or []],
        "reasons": [str(item) for item in risk.get("reasons") or []],
        "affected_resources": [
            str(item.get("id") if isinstance(item, dict) else item)
            for item in resources
        ],
    }


def _interaction_options(values: Any) -> list[dict[str, Any]]:
    options = []
    for index, value in enumerate(values if isinstance(values, list) else []):
        if not isinstance(value, dict):
            continue
        label = str(value.get("label") or value.get("id") or f"Option {index + 1}")
        options.append(
            {
                "id": str(value.get("id") or label),
                "label": label,
                "description": str(value.get("description") or ""),
                "recommended": bool(value.get("recommended", False)),
            }
        )
    if len(options) >= 2:
        return options[:3]
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


def _normalize_interaction_request(value: Any) -> dict[str, Any]:
    request = _load_json(value, {})
    if not isinstance(request, dict):
        request = {}
    kind = request.get("type") or request.get("kind")
    call_id = str(request.get("call_id") or "interaction")
    if kind in {"approval", "confirmation", "legacy_permission"}:
        action = request.get("action") if isinstance(request.get("action"), dict) else {}
        risk = request.get("risk")
        if not isinstance(risk, dict):
            risk = {
                "level": action.get("risk_level") or request.get("risk_level"),
                "reasons": [],
                "effects": [],
                "affected_resources": [],
            }
        return {
            "type": "approval",
            "call_id": call_id,
            "tool_name": str(request.get("tool_name") or action.get("name") or "tool"),
            "summary": str(request.get("summary") or "Allow this tool to run?"),
            "input_preview": request.get("input_preview") or action.get("input_preview"),
            "allowed_responses": ["approve", "reject"],
            "risk": _public_risk(risk),
        }
    if kind in {"ask_user", "question"}:
        questions = []
        for index, raw in enumerate(request.get("questions") or []):
            question = {"question": raw} if isinstance(raw, str) else raw
            if not isinstance(question, dict):
                continue
            header = str(question.get("header") or f"Question {index + 1}")
            questions.append(
                {
                    "id": str(question.get("id") or header),
                    "header": header,
                    "question": str(question.get("question") or ""),
                    "multi_select": bool(
                        question.get("multi_select", question.get("multiSelect", False))
                    ),
                    "options": _interaction_options(question.get("options")),
                }
            )
        if questions:
            return {"type": "ask_user", "call_id": call_id, "questions": questions}
    return {
        "type": "recovery",
        "call_id": call_id,
        "tool_name": str(request.get("tool_name") or "tool"),
        "message": str(request.get("message") or "Recovery requires a decision."),
        "options": _interaction_options(request.get("options")),
    }


def _normalize_interaction_response(value: Any) -> dict[str, Any]:
    response = _load_json(value, {})
    if not isinstance(response, dict):
        response = {}
    if response.get("type") in {"ask_user", "approval", "recovery"}:
        return {
            key: nested
            for key, nested in response.items()
            if key not in PRIVATE_INTERACTION_KEYS
        }
    decision = response.get("permission_decision")
    if isinstance(decision, dict):
        normalized = str(decision.get("decision") or "").lower()
        return {"type": "approval", "approved": normalized in {"approve", "approved"}}
    if "approved" in response:
        return {"type": "approval", "approved": bool(response.get("approved"))}
    if "answers" in response:
        answers = response.get("answers")
        return {"type": "ask_user", "answers": answers if isinstance(answers, dict) else {}}
    choice = response.get("choice")
    if choice in {"inspect", "retry", "cancel"}:
        return {"type": "recovery", "choice": choice}
    return {"type": "recovery", "choice": "inspect"}


def _normalize_entry_payload(
    entry: sa.Row[Any],
    *,
    attachments: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, Any]:
    payload = _load_json(entry.payload, {})
    if not isinstance(payload, dict):
        payload = {}
    if entry.type == "message":
        return _normalize_message_payload(
            payload,
            entry_id=str(entry.id),
            session_id=str(entry.session_id),
            attachments=attachments,
        )
    if entry.type == "interaction_request":
        return {
            "interaction_id": str(payload.get("interaction_id") or "interaction"),
            "request": _normalize_interaction_request(payload.get("request")),
        }
    if entry.type == "interaction_response":
        return {
            "interaction_id": str(payload.get("interaction_id") or "interaction"),
            "response": _normalize_interaction_response(payload.get("response")),
        }
    return payload


def _normalize_draft(value: Any, *, run_id: str) -> dict[str, Any] | None:
    draft = _load_json(value, None)
    if not isinstance(draft, dict):
        return None
    if isinstance(draft.get("parts"), list):
        parts = []
        for part in draft["parts"]:
            if not isinstance(part, dict):
                continue
            normalized = dict(part)
            text = str(normalized.get("text") or "")
            normalized["end_offset"] = int(normalized.get("end_offset") or len(text))
            parts.append(normalized)
        return {
            "id": str(draft.get("id") or f"draft:{run_id}"),
            "run_id": str(draft.get("run_id") or run_id),
            "parts": parts,
        }
    parts = []
    reasoning = draft.get("reasoning_summary", draft.get("reasoning"))
    if isinstance(reasoning, str) and reasoning:
        parts.append(
            {
                "id": f"draft:{run_id}:reasoning",
                "type": "reasoning_summary",
                "text": reasoning,
                "end_offset": len(reasoning),
            }
        )
    text = draft.get("text")
    if isinstance(text, str) and text:
        parts.append(
            {
                "id": f"draft:{run_id}:text",
                "type": "text",
                "text": text,
                "end_offset": len(text),
            }
        )
    return {"id": f"draft:{run_id}", "run_id": run_id, "parts": parts}


def _normalize_tool_progress(value: Any) -> list[dict[str, Any]] | None:
    progress = _load_json(value, None)
    if progress is None:
        return None
    if not isinstance(progress, list):
        return []
    result = []
    for raw in progress:
        if not isinstance(raw, dict):
            continue
        call_id = str(raw.get("call_id") or "tool")
        name = str(raw.get("name") or "tool")
        arguments = raw.get("arguments")
        safe_arguments = arguments if isinstance(arguments, dict) else {}
        item = {
            "call_id": call_id,
            "group_id": str(raw.get("group_id") or f"tool-group:{call_id}"),
            "execution_mode": str(raw.get("execution_mode") or "serial"),
            "name": name,
            "display_name": str(raw.get("display_name") or name),
            "category": str(raw.get("category") or _tool_category(name)),
            "summary": str(raw.get("summary") or _tool_summary(name, safe_arguments)),
            "arguments": safe_arguments,
            "status": str(raw.get("status") or "pending"),
            "revision": max(1, int(raw.get("revision") or 0)),
        }
        for key in (
            "started_at",
            "completed_at",
            "input_summary",
            "output_summary",
            "error",
        ):
            if raw.get(key) is not None:
                item[key] = raw[key]
        result.append(item)
    return result


def upgrade() -> None:
    op.add_column(
        "agent_sessions",
        sa.Column(
            "workspace_access",
            sa.String(20),
            nullable=False,
            server_default="read_write",
        ),
    )
    op.add_column(
        "agent_runs",
        sa.Column("revision", sa.Integer(), nullable=False, server_default="0"),
    )

    bind = op.get_bind()
    attachments = _attachment_lookup(bind)
    metadata = sa.MetaData()
    sessions = sa.Table(
        "agent_sessions", metadata, autoload_with=bind, resolve_fks=False
    )
    runs = sa.Table("agent_runs", metadata, autoload_with=bind, resolve_fks=False)
    entries = sa.Table(
        "agent_entries", metadata, autoload_with=bind, resolve_fks=False
    )

    for row in bind.execute(sa.select(sessions)).all():
        permission_mode = str(row.permission_mode or "ask_dangerous")
        workspace_access = "read_write"
        if permission_mode == "read_only":
            permission_mode = "ask_changes"
            workspace_access = "read_only"
        elif permission_mode not in {"ask_changes", "ask_dangerous", "full_access"}:
            permission_mode = "ask_dangerous"
        bind.execute(
            sessions.update()
            .where(sessions.c.id == row.id)
            .values(
                permission_mode=permission_mode,
                workspace_access=workspace_access,
                command_queue=_normalize_command_queue(
                    row.command_queue,
                    session_id=str(row.id),
                    attachments=attachments,
                ),
            )
        )

    for row in bind.execute(
        sa.select(runs).order_by(runs.c.created_at, runs.c.id)
    ).all():
        normalized_commands = _normalize_command_queue(
            row.command_queue,
            session_id=str(row.session_id),
            attachments=attachments,
        )
        deferred_messages = [
            command for command in normalized_commands if command.get("type") == "message"
        ]
        run_commands = [
            command for command in normalized_commands if command.get("type") != "message"
        ]
        if deferred_messages:
            session_queue = _load_json(
                bind.execute(
                    sa.select(sessions.c.command_queue).where(
                        sessions.c.id == row.session_id
                    )
                ).scalar_one_or_none(),
                [],
            )
            bind.execute(
                sessions.update()
                .where(sessions.c.id == row.session_id)
                .values(
                    command_queue=(
                        list(session_queue) if isinstance(session_queue, list) else []
                    )
                    + deferred_messages
                )
            )
        bind.execute(
            runs.update()
            .where(runs.c.id == row.id)
            .values(
                command_queue=run_commands,
                draft=_normalize_draft(row.draft, run_id=str(row.id)),
                tool_progress=_normalize_tool_progress(row.tool_progress),
            )
        )

    for row in bind.execute(sa.select(entries)).all():
        bind.execute(
            entries.update()
            .where(entries.c.id == row.id)
            .values(
                schema_version=2,
                payload=_normalize_entry_payload(row, attachments=attachments),
            )
        )


def downgrade() -> None:
    raise RuntimeError(
        "0059_complete_agent_harness is an intentional one-way data migration"
    )
