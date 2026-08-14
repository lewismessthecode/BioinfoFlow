"""replace Agent Core with complete Agent Harness persistence

Revision ID: 0059_complete_agent_harness
Revises: 0058_remove_container_registry_default
Create Date: 2026-08-13
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from uuid import uuid4

import sqlalchemy as sa
from alembic import op


revision = "0059_complete_agent_harness"
down_revision = "0058_remove_container_registry_default"
branch_labels = None
depends_on = None

PREFIX = "_new_agent_"
ACTIVE_OLD = {"queued", "running", "waiting_user", "waiting_approval"}
PERMISSIONS = {
    "ask_each_action": "ask_dangerous",
    "guarded_auto": "ask_dangerous",
    "bypass": "full_access",
    "read_only": "read_only",
    "ask_dangerous": "ask_dangerous",
    "full_access": "full_access",
}


def _timestamps() -> tuple[sa.Column, sa.Column]:
    return (
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def _load_json(value, default):
    if value is None:
        return default
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return default
    return value


def _dump_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _legacy_tool_call(value) -> dict | None:
    if not isinstance(value, dict):
        return None
    function = value.get("function")
    if isinstance(function, dict):
        name = function.get("name")
        arguments = function.get("arguments")
    else:
        name = value.get("name")
        arguments = value.get("arguments")
    call_id = value.get("call_id") or value.get("id")
    if not isinstance(call_id, str) or not call_id:
        return None
    if not isinstance(name, str) or not name:
        return None
    arguments = _load_json(arguments, {})
    if not isinstance(arguments, dict):
        arguments = {}
    return {"call_id": call_id, "name": name, "arguments": arguments}


def _normalized_legacy_message(row: dict) -> dict:
    metadata = _load_json(row.get("metadata"), {}) or {}
    raw_parts = _load_json(row.get("content_parts"), [])
    if not isinstance(raw_parts, list):
        raw_parts = []
    content = []
    tool_calls = []
    attachment_ids = []
    for part in raw_parts:
        if not isinstance(part, dict):
            continue
        if part.get("type") == "tool_calls":
            tool_calls.extend(
                normalized
                for raw_call in part.get("tool_calls") or []
                if (normalized := _legacy_tool_call(raw_call)) is not None
            )
            continue
        if part.get("type") == "image_ref":
            attachment_id = part.get("attachment_id")
            if isinstance(attachment_id, str) and attachment_id:
                attachment_ids.append(attachment_id)
                content.append({**part, "type": "attachment"})
            continue
        content.append(part)
    for raw_call in metadata.get("tool_calls") or []:
        normalized = _legacy_tool_call(raw_call)
        if normalized is not None:
            tool_calls.append(normalized)
    attachment_ids.extend(
        str(value) for value in metadata.get("attachment_ids") or [] if value
    )
    payload = {
        "role": row["role"],
        "content": content,
        "tool_calls": list({item["call_id"]: item for item in tool_calls}.values()),
        "attachment_ids": list(dict.fromkeys(attachment_ids)),
        "artifact_ids": metadata.get("artifact_ids", []),
    }
    call_id = metadata.get("call_id") or metadata.get("tool_call_id")
    if call_id is not None:
        payload["call_id"] = str(call_id)
    if "is_error" in metadata:
        payload["is_error"] = bool(metadata.get("is_error"))
    if metadata.get("reasoning_summary") is not None:
        payload["reasoning_summary"] = metadata["reasoning_summary"]
    return payload


def _normalized_prompt_snapshot(value) -> dict:
    snapshot = _load_json(value, {})
    if not isinstance(snapshot, dict):
        snapshot = {}
    content = snapshot.get("content")
    if not isinstance(content, str) or not content.strip():
        for legacy_key in ("system", "text", "prompt"):
            candidate = snapshot.get(legacy_key)
            if isinstance(candidate, str) and candidate.strip():
                content = candidate
                break
    if not isinstance(content, str) or not content.strip():
        content = (
            "You are the BioinfoFlow Agent. Continue this migrated conversation "
            "using the current Agent Harness and its available tools."
        )
    normalized = {"schema_version": 1, "content": content.strip()}
    snapshot_id = snapshot.get("id")
    if isinstance(snapshot_id, str) and snapshot_id:
        normalized["id"] = snapshot_id
    return normalized


def _bioinfoflow_home() -> Path:
    raw = str(os.getenv("BIOINFOFLOW_HOME") or "data").strip()
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = Path(__file__).resolve().parents[3] / path
    return path.resolve()


def _workspace_snapshots(
    sessions: list[dict],
    projects: list[dict],
    connections: list[dict],
) -> dict[str, dict]:
    project_by_id = {str(row["id"]): row for row in projects}
    connection_by_id = {str(row["id"]): row for row in connections}
    home = _bioinfoflow_home()
    snapshots: dict[str, dict] = {}
    for session in sessions:
        project_id = session.get("project_id")
        project = project_by_id.get(str(project_id)) if project_id else None
        if project is None:
            snapshots[str(session["id"])] = {
                "runtime": "local",
                "root": str((home / "sources" / "deliveries").resolve()),
            }
            continue
        mode = str(project.get("storage_mode") or "managed")
        if mode == "remote":
            connection_id = project.get("remote_connection_id")
            connection = (
                connection_by_id.get(str(connection_id)) if connection_id else None
            )
            remote_root = str(project.get("remote_root_path") or "").strip()
            if connection is not None and remote_root:
                snapshots[str(session["id"])] = {
                    "runtime": "remote_ssh",
                    "root": remote_root,
                    "remote_connection": {
                        "id": str(connection["id"]),
                        "name": connection["name"],
                        "host": connection["host"],
                        "port": int(connection.get("port") or 22),
                        "username": connection["username"],
                    },
                }
                continue
        if mode == "external" and project.get("external_root_path"):
            root = Path(str(project["external_root_path"])).expanduser().resolve()
        else:
            directory = str(project.get("directory_name") or project["id"])
            root = (home / "projects" / directory).resolve()
        snapshots[str(session["id"])] = {"runtime": "local", "root": str(root)}
    return snapshots


def _rows(table: str) -> list[dict]:
    bind = op.get_bind()
    if not sa.inspect(bind).has_table(table):
        return []
    result = bind.execute(sa.text(f"SELECT * FROM {table}"))
    return [dict(row) for row in result.mappings()]


def _create_replacement_tables() -> None:
    op.create_table(
        f"{PREFIX}sessions",
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("workspace_id", sa.String(36), nullable=False),
        sa.Column("project_id", sa.String(36), nullable=True),
        sa.Column("title", sa.String(200), nullable=True),
        sa.Column("model_snapshot", sa.JSON(), nullable=True),
        sa.Column("workspace_snapshot", sa.JSON(), nullable=True),
        sa.Column("permission_mode", sa.String(30), nullable=False),
        sa.Column("prompt_snapshot", sa.JSON(), nullable=False),
        sa.Column("history_revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("command_queue", sa.JSON(), nullable=False),
        sa.Column("command_ids", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("closing_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closing_reason", sa.String(100), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("id", sa.String(36), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        f"{PREFIX}runs",
        sa.Column("session_id", sa.String(36), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("phase", sa.String(30), nullable=True),
        sa.Column("model_snapshot", sa.JSON(), nullable=True),
        sa.Column("lease_owner", sa.String(100), nullable=True),
        sa.Column("lease_generation", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("command_queue", sa.JSON(), nullable=False),
        sa.Column("command_ids", sa.JSON(), nullable=False),
        sa.Column("draft", sa.JSON(), nullable=True),
        sa.Column("tool_progress", sa.JSON(), nullable=True),
        sa.Column("checkpoint", sa.JSON(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("token_usage", sa.JSON(), nullable=True),
        sa.Column("termination_reason", sa.String(100), nullable=True),
        sa.Column("error", sa.JSON(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_reason", sa.String(100), nullable=True),
        sa.Column("id", sa.String(36), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["session_id"], [f"{PREFIX}sessions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        f"{PREFIX}entries",
        sa.Column("session_id", sa.String(36), nullable=False),
        sa.Column("run_id", sa.String(36), nullable=True),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(40), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("id", sa.String(36), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["session_id"], [f"{PREFIX}sessions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["run_id"], [f"{PREFIX}runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "sequence"),
    )
    op.create_table(
        f"{PREFIX}attachments",
        sa.Column("session_id", sa.String(36), nullable=False),
        sa.Column("workspace_id", sa.String(36), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("source", sa.String(30), nullable=False),
        sa.Column("filename", sa.String(500), nullable=False),
        sa.Column("storage_path", sa.String(1000), nullable=False),
        sa.Column("mime_type", sa.String(200), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("file_count", sa.Integer(), nullable=True),
        sa.Column("image_width", sa.Integer(), nullable=True),
        sa.Column("image_height", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("id", sa.String(36), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["session_id"], [f"{PREFIX}sessions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        f"{PREFIX}artifacts",
        sa.Column("session_id", sa.String(36), nullable=False),
        sa.Column("run_id", sa.String(36), nullable=True),
        sa.Column("type", sa.String(60), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("file_path", sa.String(1000), nullable=True),
        sa.Column("resource_ref", sa.JSON(), nullable=True),
        sa.Column("id", sa.String(36), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["session_id"], [f"{PREFIX}sessions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["run_id"], [f"{PREFIX}runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )


def _copy_sessions(
    bind,
    sessions: list[dict],
    *,
    workspace_snapshots: dict[str, dict],
) -> dict[str, int]:
    revisions = {str(row["id"]): 0 for row in sessions}
    statement = sa.text(
        f"INSERT INTO {PREFIX}sessions "
        "(id,user_id,workspace_id,project_id,title,model_snapshot,workspace_snapshot,"
        "permission_mode,prompt_snapshot,history_revision,command_queue,command_ids,"
        "status,metadata,created_at,updated_at) VALUES "
        "(:id,:user_id,:workspace_id,:project_id,:title,:model_snapshot,:workspace_snapshot,"
        ":permission_mode,:prompt_snapshot,0,:command_queue,:command_ids,:status,"
        ":metadata,:created_at,:updated_at)"
    )
    for row in sessions:
        profile_id = row.get("default_model_profile_id")
        metadata = row.get("metadata")
        bind.execute(
            statement,
            {
                "id": str(row["id"]),
                "user_id": row["user_id"],
                "workspace_id": str(row["workspace_id"]),
                "project_id": (
                    str(row["project_id"]) if row.get("project_id") else None
                ),
                "title": row.get("title"),
                "model_snapshot": (
                    _dump_json({"profile_id": str(profile_id)}) if profile_id else None
                ),
                "workspace_snapshot": _dump_json(workspace_snapshots[str(row["id"])]),
                "permission_mode": PERMISSIONS.get(
                    row.get("permission_mode"), "ask_dangerous"
                ),
                "prompt_snapshot": _dump_json(
                    _normalized_prompt_snapshot(row.get("prompt_snapshot"))
                ),
                "command_queue": _dump_json([]),
                "command_ids": _dump_json([]),
                "status": row.get("status") or "active",
                "metadata": (
                    _dump_json(_load_json(metadata, None))
                    if metadata is not None
                    else None
                ),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            },
        )
    return revisions


def _copy_runs(bind, turns: list[dict]) -> list[dict]:
    unfinished = []
    statement = sa.text(
        f"INSERT INTO {PREFIX}runs "
        "(id,session_id,status,phase,model_snapshot,command_queue,command_ids,"
        "retry_count,token_usage,termination_reason,error,started_at,completed_at,"
        "created_at,updated_at) VALUES "
        "(:id,:session_id,:status,NULL,:model_snapshot,:command_queue,:command_ids,"
        "0,:token_usage,:termination_reason,:error,:started_at,:completed_at,"
        ":created_at,:updated_at)"
    )
    for row in turns:
        interrupted = row["status"] in ACTIVE_OLD
        if interrupted:
            unfinished.append(row)
        error = None
        if interrupted:
            error = {"code": "interrupted_by_upgrade"}
        elif row.get("error_code") or row.get("error_message"):
            error = {
                "code": row.get("error_code"),
                "message": row.get("error_message"),
            }
        model_snapshot = row.get("model_profile_snapshot")
        token_usage = row.get("token_usage")
        bind.execute(
            statement,
            {
                "id": str(row["id"]),
                "session_id": str(row["session_id"]),
                "status": "failed" if interrupted else row["status"],
                "model_snapshot": (
                    _dump_json(_load_json(model_snapshot, None))
                    if model_snapshot is not None
                    else None
                ),
                "command_queue": _dump_json([]),
                "command_ids": _dump_json([]),
                "token_usage": (
                    _dump_json(_load_json(token_usage, None))
                    if token_usage is not None
                    else None
                ),
                "termination_reason": (
                    "interrupted_by_upgrade"
                    if interrupted
                    else row.get("termination_reason")
                ),
                "error": _dump_json(error) if error else None,
                "started_at": row.get("started_at"),
                "completed_at": (
                    row["updated_at"] if interrupted else row.get("completed_at")
                ),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            },
        )
    return unfinished


def _insert_entry(
    bind,
    *,
    row_id,
    session_id,
    run_id,
    sequence,
    entry_type,
    payload,
    created_at,
    updated_at,
) -> None:
    bind.execute(
        sa.text(
            f"INSERT INTO {PREFIX}entries "
            "(id,session_id,run_id,sequence,type,schema_version,payload,"
            "created_at,updated_at) VALUES "
            "(:id,:session_id,:run_id,:sequence,:type,1,:payload,"
            ":created_at,:updated_at)"
        ),
        {
            "id": row_id,
            "session_id": session_id,
            "run_id": run_id,
            "sequence": sequence,
            "type": entry_type,
            "payload": _dump_json(payload),
            "created_at": created_at,
            "updated_at": updated_at,
        },
    )


def _copy_entries(
    bind,
    messages: list[dict],
    actions: list[dict],
    unfinished: list[dict],
    revisions: dict[str, int],
) -> None:
    timeline = []
    durable = [
        row for row in messages if row.get("status") in {"committed", "superseded"}
    ]
    for row in durable:
        session_id = str(row["session_id"])
        message_payload = _normalized_legacy_message(row)
        if row.get("status") == "superseded":
            entry_type = "notice"
            payload = {
                "code": "legacy_superseded_message",
                "message": "A superseded legacy message was preserved for audit.",
                "details": {"message": message_payload},
            }
        else:
            entry_type = "message"
            payload = message_payload
        timeline.append(
            {
                "row_id": str(row["id"]),
                "session_id": session_id,
                "run_id": str(row["turn_id"]) if row.get("turn_id") else None,
                "entry_type": entry_type,
                "payload": payload,
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "source_rank": 0,
                "source_sequence": row.get("ordering_index") or 0,
                "stable_id": str(row["id"]),
            }
        )
    for row in actions:
        action_entry = _legacy_action_decision_entry(row)
        if action_entry is None:
            continue
        session_id = str(row["session_id"])
        if session_id not in revisions:
            continue
        timeline.append(
            {
                "row_id": str(uuid4()),
                "session_id": session_id,
                "run_id": str(row["turn_id"]) if row.get("turn_id") else None,
                "entry_type": action_entry[0],
                "payload": action_entry[1],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "source_rank": 1,
                "source_sequence": row.get("tool_call_ordinal") or 0,
                "stable_id": str(row["id"]),
            }
        )
    for row in unfinished:
        session_id = str(row["session_id"])
        if session_id not in revisions:
            continue
        timeline.append(
            {
                "row_id": str(uuid4()),
                "session_id": session_id,
                "run_id": str(row["id"]),
                "entry_type": "notice",
                "payload": {
                    "code": "interrupted_by_upgrade",
                    "message": (
                        "This unfinished run was interrupted by the Agent Harness "
                        "upgrade and was not replayed."
                    ),
                    "details": {"legacy_run_id": str(row["id"])},
                },
                "created_at": row["updated_at"],
                "updated_at": row["updated_at"],
                "source_rank": 2,
                "source_sequence": 0,
                "stable_id": str(row["id"]),
            }
        )
    for entry in _ordered_legacy_timeline(timeline):
        session_id = entry["session_id"]
        revisions[session_id] += 1
        _insert_entry(
            bind,
            row_id=entry["row_id"],
            session_id=session_id,
            run_id=entry["run_id"],
            sequence=revisions[session_id],
            entry_type=entry["entry_type"],
            payload=entry["payload"],
            created_at=entry["created_at"],
            updated_at=entry["updated_at"],
        )
    for session_id, value in revisions.items():
        bind.execute(
            sa.text(
                f"UPDATE {PREFIX}sessions SET history_revision=:revision WHERE id=:id"
            ),
            {"revision": value, "id": session_id},
        )


def _legacy_timeline_key(entry: dict) -> tuple:
    created_at = entry.get("created_at")
    timestamp = (
        created_at.isoformat()
        if hasattr(created_at, "isoformat")
        else str(created_at or "")
    )
    return (
        entry["session_id"],
        timestamp,
        entry["source_rank"],
        entry["source_sequence"],
        entry["stable_id"],
    )


def _ordered_legacy_timeline(timeline: list[dict]) -> list[dict]:
    """Keep legacy message ordering canonical while anchoring related facts."""

    ordered: list[dict] = []
    session_ids = sorted({entry["session_id"] for entry in timeline})
    for session_id in session_ids:
        session_entries = [
            entry for entry in timeline if entry["session_id"] == session_id
        ]
        messages = sorted(
            (entry for entry in session_entries if entry["source_rank"] == 0),
            key=lambda entry: (entry["source_sequence"], entry["stable_id"]),
        )
        facts = [entry for entry in session_entries if entry["source_rank"] != 0]
        anchors: dict[int, list[dict]] = {}
        trailing: list[dict] = []
        last_message_for_run: dict[str, int] = {}
        for index, message in enumerate(messages):
            if message.get("run_id"):
                last_message_for_run[str(message["run_id"])] = index
        for fact in facts:
            anchor = _legacy_fact_anchor(fact, messages, last_message_for_run)
            if anchor is None:
                trailing.append(fact)
            else:
                anchors.setdefault(anchor, []).append(fact)
        for index, message in enumerate(messages):
            ordered.append(message)
            ordered.extend(sorted(anchors.get(index, []), key=_legacy_timeline_key))
        ordered.extend(sorted(trailing, key=_legacy_timeline_key))
    return ordered


def _legacy_fact_anchor(
    fact: dict,
    messages: list[dict],
    last_message_for_run: dict[str, int],
) -> int | None:
    run_id = str(fact.get("run_id") or "")
    if not run_id:
        return None
    if fact.get("source_rank") == 1:
        tool_name = _legacy_fact_tool_name(fact)
        if tool_name:
            candidates = [
                index
                for index, message in enumerate(messages)
                if str(message.get("run_id") or "") == run_id
                and _legacy_message_calls_tool(message, tool_name)
            ]
            if len(candidates) == 1:
                return candidates[0]
    return last_message_for_run.get(run_id)


def _legacy_fact_tool_name(fact: dict) -> str | None:
    payload = fact.get("payload")
    if not isinstance(payload, dict):
        return None
    for container_name in ("request", "response", "details"):
        container = payload.get(container_name)
        if not isinstance(container, dict):
            continue
        action = container.get("action")
        if isinstance(action, dict) and isinstance(action.get("name"), str):
            return action["name"]
    return None


def _legacy_message_calls_tool(message: dict, tool_name: str) -> bool:
    payload = message.get("payload")
    if not isinstance(payload, dict) or payload.get("role") != "assistant":
        return False
    calls = payload.get("tool_calls")
    return isinstance(calls, list) and any(
        isinstance(call, dict) and call.get("name") == tool_name for call in calls
    )


def _legacy_action_decision_entry(row: dict) -> tuple[str, dict] | None:
    """Preserve a legacy approval fact after the Action state machine is removed."""
    decision = _load_json(row.get("permission_decision"), None)
    if not isinstance(decision, dict) or not decision:
        return None
    interaction_id = f"legacy-action:{row['id']}"
    action = {
        "legacy_action_id": str(row["id"]),
        "kind": row.get("kind"),
        "name": row.get("name"),
        "status": row.get("status"),
        "risk_level": row.get("risk_level"),
        "input_preview": row.get("input_preview"),
    }
    normalized = str(decision.get("decision") or "").strip().lower()
    source = str(decision.get("source") or "").strip().lower()
    if normalized == "ask":
        return (
            "interaction_request",
            {
                "interaction_id": interaction_id,
                "request": {
                    "kind": "legacy_permission",
                    "action": action,
                    "permission_decision": decision,
                },
            },
        )
    if source == "user" or normalized in {
        "approve",
        "approved",
        "reject",
        "rejected",
    }:
        return (
            "interaction_response",
            {
                "interaction_id": interaction_id,
                "response": {
                    "kind": "legacy_permission",
                    "action": action,
                    "permission_decision": decision,
                },
            },
        )
    return (
        "notice",
        {
            "code": "legacy_permission_decision",
            "message": "A legacy Agent action permission decision was preserved.",
            "details": {
                "action": action,
                "permission_decision": decision,
            },
        },
    )


def _copy_attachments(bind, rows: list[dict]) -> None:
    names = (
        "id",
        "session_id",
        "workspace_id",
        "user_id",
        "kind",
        "source",
        "filename",
        "storage_path",
        "mime_type",
        "size_bytes",
        "file_count",
        "image_width",
        "image_height",
        "status",
        "metadata",
        "error_message",
        "created_at",
        "updated_at",
    )
    statement = sa.text(
        f"INSERT INTO {PREFIX}attachments ({','.join(names)}) "
        f"VALUES ({','.join(':' + name for name in names)})"
    )
    for row in rows:
        values = {name: row.get(name) for name in names}
        if values["metadata"] is not None:
            values["metadata"] = _dump_json(_load_json(values["metadata"], None))
        bind.execute(statement, values)


def _copy_artifacts(bind, rows: list[dict]) -> None:
    statement = sa.text(
        f"INSERT INTO {PREFIX}artifacts "
        "(id,session_id,run_id,type,title,summary,payload,file_path,resource_ref,"
        "created_at,updated_at) VALUES "
        "(:id,:session_id,:run_id,:type,:title,:summary,:payload,:file_path,"
        ":resource_ref,:created_at,:updated_at)"
    )
    for row in rows:
        payload = row.get("payload")
        resource_ref = row.get("resource_ref")
        bind.execute(
            statement,
            {
                "id": str(row["id"]),
                "session_id": str(row["session_id"]),
                "run_id": (str(row["turn_id"]) if row.get("turn_id") else None),
                "type": row["type"],
                "title": row["title"],
                "summary": row.get("summary"),
                "payload": (
                    _dump_json(_load_json(payload, None))
                    if payload is not None
                    else None
                ),
                "file_path": row.get("file_path"),
                "resource_ref": (
                    _dump_json(_load_json(resource_ref, None))
                    if resource_ref is not None
                    else None
                ),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            },
        )


def _copy_committed_state() -> None:
    bind = op.get_bind()
    sessions = _rows("agent_sessions")
    snapshots = _workspace_snapshots(
        sessions,
        _rows("projects"),
        _rows("remote_connections"),
    )
    revisions = _copy_sessions(
        bind,
        sessions,
        workspace_snapshots=snapshots,
    )
    unfinished = _copy_runs(bind, _rows("agent_turns"))
    _copy_entries(
        bind,
        _rows("agent_messages"),
        _rows("agent_actions"),
        unfinished,
        revisions,
    )
    _copy_attachments(bind, _rows("agent_attachments"))
    _copy_artifacts(bind, _rows("agent_artifacts"))


def _drop_old_tables() -> None:
    for table in (
        "agent_artifacts",
        "agent_attachments",
        "agent_actions",
        "agent_tool_call_batches",
        "agent_events",
        "agent_messages",
        "agent_memories",
        "agent_turns",
        "agent_sessions",
    ):
        if sa.inspect(op.get_bind()).has_table(table):
            op.drop_table(table)
    if sa.inspect(op.get_bind()).has_table("agent_approvals"):
        op.drop_table("agent_approvals")


def _rename_and_index() -> None:
    for source, target in (
        (f"{PREFIX}sessions", "agent_sessions"),
        (f"{PREFIX}runs", "agent_runs"),
        (f"{PREFIX}entries", "agent_entries"),
        (f"{PREFIX}attachments", "agent_attachments"),
        (f"{PREFIX}artifacts", "agent_artifacts"),
    ):
        op.rename_table(source, target)
    indexes = (
        (
            "ix_agent_sessions_user_id",
            "agent_sessions",
            ["user_id"],
            False,
            None,
        ),
        (
            "ix_agent_sessions_workspace_id",
            "agent_sessions",
            ["workspace_id"],
            False,
            None,
        ),
        (
            "ix_agent_sessions_project_id",
            "agent_sessions",
            ["project_id"],
            False,
            None,
        ),
        (
            "ix_agent_sessions_status",
            "agent_sessions",
            ["status"],
            False,
            None,
        ),
        ("ix_agent_runs_session_id", "agent_runs", ["session_id"], False, None),
        ("ix_agent_runs_status", "agent_runs", ["status"], False, None),
        (
            "uq_agent_runs_active_session",
            "agent_runs",
            ["session_id"],
            True,
            sa.text("status IN ('queued', 'running', 'waiting_user')"),
        ),
        (
            "ix_agent_entries_session_id",
            "agent_entries",
            ["session_id"],
            False,
            None,
        ),
        ("ix_agent_entries_run_id", "agent_entries", ["run_id"], False, None),
        ("ix_agent_entries_type", "agent_entries", ["type"], False, None),
        (
            "ix_agent_attachments_session_id",
            "agent_attachments",
            ["session_id"],
            False,
            None,
        ),
        (
            "ix_agent_attachments_workspace_id",
            "agent_attachments",
            ["workspace_id"],
            False,
            None,
        ),
        (
            "ix_agent_attachments_user_id",
            "agent_attachments",
            ["user_id"],
            False,
            None,
        ),
        (
            "ix_agent_artifacts_session_id",
            "agent_artifacts",
            ["session_id"],
            False,
            None,
        ),
        (
            "ix_agent_artifacts_run_id",
            "agent_artifacts",
            ["run_id"],
            False,
            None,
        ),
        (
            "ix_agent_artifacts_type",
            "agent_artifacts",
            ["type"],
            False,
            None,
        ),
    )
    for name, table, columns, unique, where in indexes:
        op.create_index(
            name,
            table,
            columns,
            unique=unique,
            sqlite_where=where,
            postgresql_where=where,
        )


def _create_agent_tokens() -> None:
    op.create_table(
        "agent_tokens",
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("workspace_id", sa.String(36), nullable=False),
        sa.Column("session_id", sa.String(36), nullable=False),
        sa.Column("run_id", sa.String(36), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["session_id"], ["agent_sessions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    for name, columns in (
        ("ix_agent_tokens_user_id", ["user_id"]),
        ("ix_agent_tokens_workspace_id", ["workspace_id"]),
        ("ix_agent_tokens_session_id", ["session_id"]),
        ("ix_agent_tokens_run_id", ["run_id"]),
        ("ix_agent_tokens_expires_at", ["expires_at"]),
    ):
        op.create_index(name, "agent_tokens", columns)
    op.create_index(
        "ix_agent_tokens_token_hash",
        "agent_tokens",
        ["token_hash"],
        unique=True,
    )
    op.create_index(
        "uq_agent_tokens_active_run",
        "agent_tokens",
        ["run_id"],
        unique=True,
        sqlite_where=sa.text("revoked_at IS NULL"),
        postgresql_where=sa.text("revoked_at IS NULL"),
    )


def upgrade() -> None:
    _create_replacement_tables()
    _copy_committed_state()
    _drop_old_tables()
    _rename_and_index()
    _create_agent_tokens()


def downgrade() -> None:
    raise RuntimeError(
        "0059_complete_agent_harness is an intentional one-way data migration"
    )
