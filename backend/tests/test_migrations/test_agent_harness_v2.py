from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[2]
PREVIOUS_REVISION = "0059_complete_agent_harness"
TARGET_REVISION = "0060_agent_harness_public_revisions"


def _run_alembic(db_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND_DIR,
        env={"DATABASE_URL": f"sqlite+aiosqlite:///{db_path}"},
        capture_output=True,
        text=True,
        check=False,
    )


def test_agent_harness_v2_migrates_durable_public_state_and_keeps_private_recovery(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "agent-harness-v2.db"
    previous = _run_alembic(db_path, "upgrade", PREVIOUS_REVISION)
    assert previous.returncode == 0, previous.stderr

    workspace_id = "00000000-0000-0000-0000-000000000011"
    read_only_session_id = "10000000-0000-0000-0000-000000000001"
    full_access_session_id = "10000000-0000-0000-0000-000000000002"
    run_id = "20000000-0000-0000-0000-000000000001"
    attachment_id = "30000000-0000-0000-0000-000000000001"
    user_entry_id = "40000000-0000-0000-0000-000000000001"
    assistant_entry_id = "40000000-0000-0000-0000-000000000002"
    tool_entry_id = "40000000-0000-0000-0000-000000000003"
    interaction_entry_id = "40000000-0000-0000-0000-000000000004"
    private_interaction = {
        "kind": "confirmation",
        "call_id": "call-bash",
        "tool_name": "bash",
        "risk": {
            "level": "high",
            "effects": ["writes_workspace"],
            "reasons": ["modifies files"],
            "affected_resources": ["results/report.txt"],
            "assessment_fingerprint": "secret-assessment",
            "base_assessment_fingerprint": "secret-base",
            "cwd_identity": {"path": "/private/workspace"},
        },
        "replay_policy": "never",
    }
    session_queue = [
        {
            "type": "prompt",
            "command_id": "session-prompt",
            "text": "analyse reads",
            "attachment_ids": [attachment_id],
        },
        {
            "type": "follow_up",
            "command_id": "session-follow-up",
            "text": "then summarize",
            "attachment_ids": [],
        },
    ]
    run_queue = [
        {
            "type": "follow_up",
            "command_id": "run-follow-up",
            "text": "continue after approval",
            "attachment_ids": [],
        }
    ]
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "INSERT INTO workspaces (id, name, slug, created_at, updated_at) "
            "VALUES (?, 'Harness v2', 'harness-v2', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            (workspace_id,),
        )
        for session_id, permission_mode, command_queue in (
            (read_only_session_id, "read_only", session_queue),
            (full_access_session_id, "full_access", []),
        ):
            connection.execute(
                "INSERT INTO agent_sessions "
                "(id, user_id, workspace_id, title, permission_mode, prompt_snapshot, "
                "history_revision, command_queue, command_ids, status, created_at, updated_at) "
                "VALUES (?, 'user-1', ?, 'Migrated', ?, ?, 4, ?, '[]', 'active', "
                "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
                (
                    session_id,
                    workspace_id,
                    permission_mode,
                    json.dumps({"schema_version": 1, "content": "stable prompt"}),
                    json.dumps(command_queue),
                ),
            )
        connection.execute(
            "INSERT INTO agent_attachments "
            "(id, session_id, workspace_id, user_id, kind, source, filename, "
            "storage_path, mime_type, size_bytes, status, created_at, updated_at) "
            "VALUES (?, ?, ?, 'user-1', 'file', 'upload', 'reads.fastq.gz', "
            "'/private/reads.fastq.gz', 'application/gzip', 42, 'ready', "
            "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            (attachment_id, read_only_session_id, workspace_id),
        )
        connection.execute(
            "INSERT INTO agent_runs "
            "(id, session_id, status, phase, lease_generation, command_queue, command_ids, "
            "draft, tool_progress, checkpoint, retry_count, created_at, updated_at) "
            "VALUES (?, ?, 'waiting_user', 'interaction', 0, ?, '[]', ?, ?, ?, 0, "
            "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            (
                run_id,
                read_only_session_id,
                json.dumps(run_queue),
                json.dumps({"text": "partial answer", "reasoning": "checking inputs"}),
                json.dumps(
                    [
                        {
                            "call_id": "call-bash",
                            "name": "bash",
                            "status": "interaction_required",
                            "arguments": {"command": "touch results/report.txt"},
                        }
                    ]
                ),
                json.dumps(
                    {
                        "schema_version": 1,
                        "harness_version": "1",
                        "history_revision": 4,
                        "phase": "interaction",
                        "interaction": private_interaction,
                        "in_flight_tools": [
                            {
                                "call_id": "call-bash",
                                "name": "bash",
                                "arguments": {"command": "touch results/report.txt"},
                                "replay_policy": "never",
                            }
                        ],
                    }
                ),
            ),
        )
        entries = (
            (
                user_entry_id,
                1,
                "message",
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "analyse reads"},
                        {
                            "type": "attachment",
                            "attachment_id": attachment_id,
                            "filename": "reads.fastq.gz",
                            "kind": "file",
                            "mime_type": "application/gzip",
                            "size_bytes": 42,
                        },
                    ],
                    "attachment_ids": [attachment_id],
                    "artifact_ids": [],
                    "tool_calls": [],
                },
            ),
            (
                assistant_entry_id,
                2,
                "message",
                {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "I will inspect it."}],
                    "reasoning_summary": "Need file metadata first.",
                    "tool_calls": [
                        {
                            "call_id": "call-bash",
                            "name": "bash",
                            "arguments": {"command": "touch results/report.txt"},
                        }
                    ],
                    "attachment_ids": [],
                    "artifact_ids": ["50000000-0000-0000-0000-000000000001"],
                },
            ),
            (
                tool_entry_id,
                3,
                "message",
                {
                    "role": "tool",
                    "content": [{"type": "text", "text": '{"ok": true}'}],
                    "call_id": "call-bash",
                    "is_error": False,
                    "tool_calls": [],
                    "attachment_ids": [],
                    "artifact_ids": [],
                },
            ),
            (
                interaction_entry_id,
                4,
                "interaction_request",
                {
                    "interaction_id": "interaction-1",
                    "request": private_interaction,
                },
            ),
        )
        for entry_id, sequence, entry_type, payload in entries:
            connection.execute(
                "INSERT INTO agent_entries "
                "(id, session_id, run_id, sequence, type, schema_version, payload, "
                "created_at, updated_at) VALUES (?, ?, ?, ?, ?, 1, ?, "
                "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
                (
                    entry_id,
                    read_only_session_id,
                    run_id,
                    sequence,
                    entry_type,
                    json.dumps(payload),
                ),
            )
        connection.commit()

    upgraded = _run_alembic(db_path, "upgrade", TARGET_REVISION)
    assert upgraded.returncode == 0, upgraded.stderr

    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        sessions = connection.execute(
            "SELECT id, permission_mode, workspace_access, command_queue "
            "FROM agent_sessions ORDER BY id"
        ).fetchall()
        run = connection.execute(
            "SELECT revision, command_queue, draft, tool_progress, checkpoint "
            "FROM agent_runs WHERE id = ?",
            (run_id,),
        ).fetchone()
        migrated_entries = connection.execute(
            "SELECT id, sequence, schema_version, payload FROM agent_entries "
            "ORDER BY sequence"
        ).fetchall()

    assert [tuple(row[:3]) for row in sessions] == [
        (read_only_session_id, "ask_changes", "read_only"),
        (full_access_session_id, "full_access", "read_write"),
    ]
    session_commands = json.loads(sessions[0]["command_queue"])
    assert [command["type"] for command in session_commands] == [
        "message",
        "message",
        "message",
    ]
    assert session_commands[0] == {
        "type": "message",
        "command_id": "session-prompt",
        "parts": [
            {"type": "text", "text": "analyse reads"},
            {
                "type": "attachment_ref",
                "attachment_id": attachment_id,
            },
        ],
    }
    assert session_commands[2] == {
        "type": "message",
        "command_id": "run-follow-up",
        "parts": [
            {
                "type": "text",
                "text": "continue after approval",
            }
        ],
    }
    assert json.loads(run["command_queue"]) == []

    assert run["revision"] == 0
    draft = json.loads(run["draft"])
    assert draft == {
        "id": f"draft:{run_id}",
        "run_id": run_id,
        "parts": [
            {
                "id": f"draft:{run_id}:reasoning",
                "type": "reasoning_summary",
                "text": "checking inputs",
                "end_offset": len("checking inputs"),
            },
            {
                "id": f"draft:{run_id}:text",
                "type": "text",
                "text": "partial answer",
                "end_offset": len("partial answer"),
            },
        ],
    }
    progress = json.loads(run["tool_progress"])
    assert progress == [
        {
            "call_id": "call-bash",
            "group_id": "tool-group:call-bash",
            "execution_mode": "serial",
            "name": "bash",
            "display_name": "bash",
            "category": "command",
            "summary": "bash: touch results/report.txt",
            "arguments": {"command": "touch results/report.txt"},
            "status": "interaction_required",
            "revision": 1,
        }
    ]
    checkpoint = json.loads(run["checkpoint"])
    assert checkpoint["interaction"]["risk"]["assessment_fingerprint"] == (
        "secret-assessment"
    )
    assert checkpoint["interaction"]["risk"]["cwd_identity"] == {
        "path": "/private/workspace"
    }
    assert checkpoint["interaction"]["replay_policy"] == "never"

    assert {row["schema_version"] for row in migrated_entries} == {2}
    user_payload = json.loads(migrated_entries[0]["payload"])
    assert user_payload == {
        "role": "user",
        "parts": [
            {"id": "text:0", "type": "text", "text": "analyse reads"},
            {
                "id": f"attachment:{attachment_id}",
                "type": "attachment_ref",
                "attachment_id": attachment_id,
                "filename": "reads.fastq.gz",
                "kind": "file",
                "mime_type": "application/gzip",
                "size_bytes": 42,
            },
        ],
    }
    assistant_payload = json.loads(migrated_entries[1]["payload"])
    assert assistant_payload["role"] == "assistant"
    assert assistant_payload["parts"] == [
        {
            "id": "reasoning:0",
            "type": "reasoning_summary",
            "text": "Need file metadata first.",
        },
        {"id": "text:0", "type": "text", "text": "I will inspect it."},
        {
            "id": "tool-call:call-bash",
            "type": "tool_call",
            "call_id": "call-bash",
            "group_id": assistant_entry_id,
            "execution_mode": "serial",
            "name": "bash",
            "display_name": "bash",
            "category": "command",
            "summary": "bash: touch results/report.txt",
            "arguments": {"command": "touch results/report.txt"},
        },
        {
            "id": "artifact:50000000-0000-0000-0000-000000000001",
            "type": "artifact_ref",
            "artifact_id": "50000000-0000-0000-0000-000000000001",
        },
    ]
    tool_payload = json.loads(migrated_entries[2]["payload"])
    assert tool_payload == {
        "role": "tool",
        "parts": [
            {
                "id": "tool-result:call-bash",
                "type": "tool_result",
                "call_id": "call-bash",
                "status": "completed",
                "output": {"type": "json", "value": {"ok": True}},
                "error": None,
            }
        ],
    }
    interaction_payload = json.loads(migrated_entries[3]["payload"])
    assert interaction_payload == {
        "interaction_id": "interaction-1",
        "request": {
            "type": "approval",
            "call_id": "call-bash",
            "tool_name": "bash",
            "summary": "Allow this tool to run?",
            "input_preview": None,
            "risk": {
                "level": "high",
                "effects": ["writes_workspace"],
                "reasons": ["modifies files"],
                "affected_resources": ["results/report.txt"],
            },
        },
    }
    assert "assessment_fingerprint" not in json.dumps(interaction_payload)
    assert "cwd_identity" not in json.dumps(interaction_payload)
    assert "replay_policy" not in json.dumps(interaction_payload)
