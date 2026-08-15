from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

from app.services.agent_harness.contracts import ENTRY_PAYLOAD_TYPES
from app.services.agent_harness.history import build_history_view
from app.services.model_runtime.contracts import TextPart, ToolCallPart, ToolResultPart
from app.database import get_alembic_head_revision


BACKEND_DIR = Path(__file__).resolve().parents[2]
PREVIOUS_REVISION = "0058_remove_container_registry_default"


def _run_alembic(db_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND_DIR,
        env={"DATABASE_URL": f"sqlite+aiosqlite:///{db_path}"},
        capture_output=True,
        text=True,
        check=False,
    )


def test_complete_harness_migration_preserves_history_and_interrupts_unfinished_work(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "agent-harness.db"
    previous = _run_alembic(db_path, "upgrade", PREVIOUS_REVISION)
    assert previous.returncode == 0, previous.stderr

    workspace_id = "00000000-0000-0000-0000-000000000011"
    session_id = "10000000-0000-0000-0000-000000000001"
    remote_session_id = "10000000-0000-0000-0000-000000000002"
    remote_project_id = "10000000-0000-0000-0000-000000000003"
    remote_connection_id = "10000000-0000-0000-0000-000000000004"
    completed_turn_id = "20000000-0000-0000-0000-000000000001"
    running_turn_id = "20000000-0000-0000-0000-000000000002"
    attachment_id = "30000000-0000-0000-0000-000000000001"
    artifact_id = "40000000-0000-0000-0000-000000000001"
    pending_action_id = "70000000-0000-0000-0000-000000000001"
    approved_action_id = "70000000-0000-0000-0000-000000000002"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "INSERT INTO workspaces (id, name, slug, created_at, updated_at) "
            "VALUES (?, 'Harness', 'harness', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            (workspace_id,),
        )
        connection.execute(
            "INSERT INTO agent_sessions "
            "(id, workspace_id, user_id, title, role_profile, permission_mode, "
            "automation_mode, runtime_mode, prompt_snapshot, status, created_at, updated_at) "
            "VALUES (?, ?, 'user-1', 'Migrated', 'bioinformatician', 'guarded_auto', "
            "'assisted', 'api', ?, 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            (session_id, workspace_id, json.dumps({"system": "legacy"})),
        )
        connection.execute(
            "INSERT INTO remote_connections "
            "(id, workspace_id, name, host, port, username, auth_method, last_status, "
            "created_at, updated_at) VALUES (?, ?, 'cluster', 'cluster.example', 22, "
            "'runner', 'agent', 'unknown', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            (remote_connection_id, workspace_id),
        )
        connection.execute(
            "INSERT INTO projects "
            "(id, name, storage_mode, remote_connection_id, remote_root_path, user_id, "
            "workspace_id, is_default, created_at, updated_at) VALUES "
            "(?, 'Remote', 'remote', ?, '/srv/bioinfoflow', 'user-1', ?, 0, "
            "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            (remote_project_id, remote_connection_id, workspace_id),
        )
        connection.execute(
            "INSERT INTO agent_sessions "
            "(id, workspace_id, user_id, project_id, title, role_profile, "
            "permission_mode, automation_mode, runtime_mode, prompt_snapshot, status, "
            "created_at, updated_at) VALUES (?, ?, 'user-1', ?, 'Remote migrated', "
            "'bioinformatician', 'guarded_auto', 'assisted', 'api', ?, 'active', "
            "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            (
                remote_session_id,
                workspace_id,
                remote_project_id,
                json.dumps({"content": "remote legacy"}),
            ),
        )
        for turn_id, status, input_text, final_text in (
            (completed_turn_id, "completed", "old prompt", "old answer"),
            (running_turn_id, "running", "dangerous work", None),
        ):
            connection.execute(
                "INSERT INTO agent_turns "
                "(id, session_id, workspace_id, user_id, input_text, status, final_text, "
                "iteration_count, tool_batch_sequence, accepts_steer, created_at, updated_at) "
                "VALUES (?, ?, ?, 'user-1', ?, ?, ?, 0, 0, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
                (turn_id, session_id, workspace_id, input_text, status, final_text),
            )
        messages = (
            (
                "50000000-0000-0000-0000-000000000001",
                completed_turn_id,
                "user",
                "old prompt",
                "committed",
                1,
            ),
            (
                "50000000-0000-0000-0000-000000000002",
                completed_turn_id,
                "assistant",
                "old answer",
                "committed",
                2,
            ),
            (
                "50000000-0000-0000-0000-000000000003",
                running_turn_id,
                "tool",
                "partial output",
                "committed",
                3,
            ),
            (
                "50000000-0000-0000-0000-000000000004",
                completed_turn_id,
                "assistant",
                "older answer",
                "superseded",
                4,
            ),
            (
                "50000000-0000-0000-0000-000000000005",
                running_turn_id,
                "assistant",
                "unfinished draft",
                "draft",
                5,
            ),
        )
        for message_id, turn_id, role, text, status, ordering_index in messages:
            connection.execute(
                "INSERT INTO agent_messages "
                "(id, session_id, turn_id, role, content_parts, status, ordering_index, "
                "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, "
                "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
                (
                    message_id,
                    session_id,
                    turn_id,
                    role,
                    json.dumps([{"type": "text", "text": text}]),
                    status,
                    ordering_index,
                ),
            )
        connection.execute(
            "INSERT INTO agent_attachments "
            "(id, session_id, workspace_id, user_id, kind, source, filename, storage_path, "
            "size_bytes, status, created_at, updated_at) VALUES (?, ?, ?, 'user-1', "
            "'file', 'upload', 'reads.txt', '/tmp/reads.txt', 12, 'ready', "
            "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            (attachment_id, session_id, workspace_id),
        )
        connection.execute(
            "INSERT INTO agent_artifacts "
            "(id, session_id, turn_id, type, title, file_path, created_at, updated_at) "
            "VALUES (?, ?, ?, 'file', 'Report', '/tmp/report.txt', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            (artifact_id, session_id, completed_turn_id),
        )
        for action_id, status, permission_decision in (
            (
                pending_action_id,
                "waiting_decision",
                {"decision": "ask", "risk_level": "act_high"},
            ),
            (
                approved_action_id,
                "completed",
                {"decision": "approve", "source": "user"},
            ),
        ):
            connection.execute(
                "INSERT INTO agent_actions "
                "(id, session_id, turn_id, kind, name, input, risk_level, "
                "permission_decision, status, requires_resume, created_at, updated_at) "
                "VALUES (?, ?, ?, 'tool', 'bash', '{}', 'act_high', ?, ?, 0, "
                "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
                (
                    action_id,
                    session_id,
                    completed_turn_id,
                    json.dumps(permission_decision),
                    status,
                ),
            )
        connection.commit()

    upgraded = _run_alembic(db_path, "upgrade", "head")
    assert upgraded.returncode == 0, upgraded.stderr

    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        session = connection.execute(
            "SELECT permission_mode, history_revision, prompt_snapshot, "
            "workspace_snapshot FROM agent_sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
        runs = connection.execute(
            "SELECT id, status, termination_reason, checkpoint, completed_at, error "
            "FROM agent_runs "
            "ORDER BY id"
        ).fetchall()
        entries = connection.execute(
            "SELECT sequence, type, payload FROM agent_entries ORDER BY sequence"
        ).fetchall()
        attachment = connection.execute(
            "SELECT filename FROM agent_attachments WHERE id = ?", (attachment_id,)
        ).fetchone()
        artifact = connection.execute(
            "SELECT run_id, title FROM agent_artifacts WHERE id = ?", (artifact_id,)
        ).fetchone()
        token_indexes = {
            row[1]: row for row in connection.execute("PRAGMA index_list(agent_tokens)")
        }
        token_foreign_keys = {
            (row[2], row[3], row[6])
            for row in connection.execute("PRAGMA foreign_key_list(agent_tokens)")
        }
        revision = connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()
        remote_workspace = connection.execute(
            "SELECT workspace_snapshot FROM agent_sessions WHERE id = ?",
            (remote_session_id,),
        ).fetchone()

        token_id = "60000000-0000-0000-0000-000000000001"
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute(
            "INSERT INTO agent_tokens "
            "(id, token_hash, user_id, workspace_id, session_id, run_id, expires_at, "
            "created_at, updated_at) VALUES (?, ?, 'user-1', ?, ?, ?, "
            "datetime('now', '+5 minutes'), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            (token_id, "a" * 64, workspace_id, session_id, completed_turn_id),
        )
        connection.execute("DELETE FROM agent_runs WHERE id = ?", (completed_turn_id,))
        remaining_token = connection.execute(
            "SELECT id FROM agent_tokens WHERE id = ?", (token_id,)
        ).fetchone()

    assert tuple(session[:2]) == ("ask_dangerous", 7)
    assert json.loads(session["prompt_snapshot"]) == {
        "schema_version": 1,
        "content": "legacy",
    }
    workspace_snapshot = json.loads(session["workspace_snapshot"])
    assert workspace_snapshot["runtime"] == "local"
    assert (
        Path(workspace_snapshot["root"])
        == (BACKEND_DIR.parent / "data" / "sources" / "deliveries").resolve()
    )
    assert json.loads(remote_workspace["workspace_snapshot"]) == {
        "runtime": "remote_ssh",
        "root": "/srv/bioinfoflow",
        "remote_connection": {
            "id": remote_connection_id,
            "name": "cluster",
            "host": "cluster.example",
            "port": 22,
            "username": "runner",
        },
    }
    assert [(row["id"], row["status"], row["termination_reason"]) for row in runs] == [
        (completed_turn_id, "completed", None),
        (running_turn_id, "failed", "interrupted_by_upgrade"),
    ]
    assert all(row["checkpoint"] is None for row in runs)
    assert runs[0]["completed_at"] is None
    assert runs[1]["completed_at"] is not None
    assert json.loads(runs[1]["error"]) == {"code": "interrupted_by_upgrade"}
    assert [row["type"] for row in entries] == [
        "message",
        "message",
        "message",
        "notice",
        "notice",
        "interaction_request",
        "interaction_response",
    ]
    assert json.loads(entries[3]["payload"])["code"] == "interrupted_by_upgrade"
    superseded = json.loads(entries[4]["payload"])
    assert superseded["code"] == "legacy_superseded_message"
    assert superseded["details"]["message"]["role"] == "assistant"
    request = json.loads(entries[5]["payload"])
    response = json.loads(entries[6]["payload"])
    assert request["interaction_id"] == f"legacy-action:{pending_action_id}"
    assert request["request"] == {
        "type": "approval",
        "call_id": "interaction",
        "tool_name": "bash",
        "summary": "Allow this tool to run?",
        "input_preview": None,
        "allowed_responses": ["approve", "reject"],
        "risk": {
            "level": "act_high",
            "effects": [],
            "reasons": [],
            "affected_resources": [],
        },
    }
    assert response["interaction_id"] == f"legacy-action:{approved_action_id}"
    assert response["response"] == {"type": "approval", "approved": True}
    for entry in entries:
        ENTRY_PAYLOAD_TYPES[entry["type"]].model_validate(json.loads(entry["payload"]))
    assert attachment["filename"] == "reads.txt"
    assert tuple(artifact) == (completed_turn_id, "Report")
    assert {
        "agent_turns",
        "agent_messages",
        "agent_actions",
        "agent_tool_call_batches",
        "agent_events",
        "agent_memories",
    }.isdisjoint(tables)
    assert {
        "agent_sessions",
        "agent_runs",
        "agent_entries",
        "agent_attachments",
        "agent_artifacts",
        "agent_tokens",
    } <= tables
    assert token_indexes["uq_agent_tokens_active_run"][2] == 1
    assert token_indexes["ix_agent_tokens_token_hash"][2] == 1
    assert any(row[2] == 1 for row in token_indexes.values())
    assert {
        ("workspaces", "workspace_id", "CASCADE"),
        ("agent_sessions", "session_id", "CASCADE"),
        ("agent_runs", "run_id", "CASCADE"),
    } <= token_foreign_keys
    assert remaining_token is None
    assert tuple(revision) == (get_alembic_head_revision(),)


def test_complete_harness_migration_is_intentionally_irreversible(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "irreversible-agent-harness.db"
    upgraded = _run_alembic(db_path, "upgrade", "head")
    assert upgraded.returncode == 0, upgraded.stderr

    downgraded = _run_alembic(db_path, "downgrade", PREVIOUS_REVISION)

    assert downgraded.returncode != 0
    assert (
        "0059_complete_agent_harness is an intentional one-way data migration"
        in downgraded.stderr
    )
    with sqlite3.connect(db_path) as connection:
        revision = connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()
    assert tuple(revision) == (get_alembic_head_revision(),)


def test_complete_harness_migration_merges_interleaved_legacy_timeline(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "interleaved-legacy-timeline.db"
    previous = _run_alembic(db_path, "upgrade", PREVIOUS_REVISION)
    assert previous.returncode == 0, previous.stderr

    workspace_id = "00000000-0000-0000-0000-000000000011"
    session_id = "10000000-0000-0000-0000-000000000001"
    completed_turn_id = "20000000-0000-0000-0000-000000000001"
    running_turn_id = "20000000-0000-0000-0000-000000000002"
    request_action_id = "70000000-0000-0000-0000-000000000001"
    response_action_id = "70000000-0000-0000-0000-000000000002"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "INSERT INTO workspaces (id, name, slug, created_at, updated_at) "
            "VALUES (?, 'Harness', 'harness', '2026-08-13 10:00:00', "
            "'2026-08-13 10:00:00')",
            (workspace_id,),
        )
        connection.execute(
            "INSERT INTO agent_sessions "
            "(id, workspace_id, user_id, title, role_profile, permission_mode, "
            "automation_mode, runtime_mode, prompt_snapshot, status, created_at, "
            "updated_at) VALUES (?, ?, 'user-1', 'Interleaved', "
            "'bioinformatician', 'guarded_auto', 'assisted', 'api', '{}', "
            "'active', '2026-08-13 10:00:00', '2026-08-13 10:00:08')",
            (session_id, workspace_id),
        )
        for turn_id, status, created_at, updated_at in (
            (
                completed_turn_id,
                "completed",
                "2026-08-13 10:00:01",
                "2026-08-13 10:00:03",
            ),
            (
                running_turn_id,
                "running",
                "2026-08-13 10:00:04",
                "2026-08-13 10:00:07",
            ),
        ):
            connection.execute(
                "INSERT INTO agent_turns "
                "(id, session_id, workspace_id, user_id, input_text, status, "
                "iteration_count, tool_batch_sequence, accepts_steer, created_at, "
                "updated_at) VALUES (?, ?, ?, 'user-1', 'timeline', ?, 0, 0, 1, ?, ?)",
                (turn_id, session_id, workspace_id, status, created_at, updated_at),
            )
        for message_id, turn_id, role, text, ordering_index, created_at in (
            (
                "50000000-0000-0000-0000-000000000001",
                completed_turn_id,
                "user",
                "turn one prompt",
                1,
                "2026-08-13 10:00:01",
            ),
            (
                "50000000-0000-0000-0000-000000000002",
                completed_turn_id,
                "assistant",
                "turn one continued",
                2,
                "2026-08-13 10:00:03",
            ),
            (
                "50000000-0000-0000-0000-000000000003",
                running_turn_id,
                "user",
                "turn two prompt",
                3,
                "2026-08-13 10:00:04",
            ),
            (
                "50000000-0000-0000-0000-000000000004",
                running_turn_id,
                "assistant",
                "turn two continued",
                4,
                "2026-08-13 10:00:06",
            ),
        ):
            connection.execute(
                "INSERT INTO agent_messages "
                "(id, session_id, turn_id, role, content_parts, status, "
                "ordering_index, created_at, updated_at) VALUES (?, ?, ?, ?, ?, "
                "'committed', ?, ?, ?)",
                (
                    message_id,
                    session_id,
                    turn_id,
                    role,
                    json.dumps([{"type": "text", "text": text}]),
                    ordering_index,
                    created_at,
                    created_at,
                ),
            )
        for action_id, turn_id, decision, status, created_at in (
            (
                request_action_id,
                completed_turn_id,
                {"decision": "ask", "risk_level": "act_high"},
                "waiting_decision",
                "2026-08-13 10:00:02",
            ),
            (
                response_action_id,
                running_turn_id,
                {"decision": "approve", "source": "user"},
                "completed",
                "2026-08-13 10:00:05",
            ),
        ):
            connection.execute(
                "INSERT INTO agent_actions "
                "(id, session_id, turn_id, kind, name, input, risk_level, "
                "permission_decision, status, requires_resume, created_at, updated_at) "
                "VALUES (?, ?, ?, 'tool', 'bash', '{}', 'act_high', ?, ?, 0, ?, ?)",
                (
                    action_id,
                    session_id,
                    turn_id,
                    json.dumps(decision),
                    status,
                    created_at,
                    created_at,
                ),
            )
        connection.commit()

    upgraded = _run_alembic(db_path, "upgrade", "head")
    assert upgraded.returncode == 0, upgraded.stderr

    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            "SELECT sequence, run_id, type, payload, created_at "
            "FROM agent_entries WHERE session_id = ? ORDER BY sequence",
            (session_id,),
        ).fetchall()
        history_revision = connection.execute(
            "SELECT history_revision FROM agent_sessions WHERE id = ?",
            (session_id,),
        ).fetchone()[0]

    assert [row["sequence"] for row in rows] == list(range(1, 8))
    assert [row["type"] for row in rows] == [
        "message",
        "message",
        "interaction_request",
        "message",
        "message",
        "interaction_response",
        "notice",
    ]
    assert [row["run_id"] for row in rows] == [
        completed_turn_id,
        completed_turn_id,
        completed_turn_id,
        running_turn_id,
        running_turn_id,
        running_turn_id,
        running_turn_id,
    ]
    assert json.loads(rows[2]["payload"])["interaction_id"] == (
        f"legacy-action:{request_action_id}"
    )
    assert json.loads(rows[5]["payload"])["interaction_id"] == (
        f"legacy-action:{response_action_id}"
    )
    assert json.loads(rows[6]["payload"])["code"] == "interrupted_by_upgrade"
    assert history_revision == 7


def test_complete_harness_migration_preserves_canonical_message_ordering_index(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "canonical-legacy-message-order.db"
    previous = _run_alembic(db_path, "upgrade", PREVIOUS_REVISION)
    assert previous.returncode == 0, previous.stderr

    workspace_id = "00000000-0000-0000-0000-000000000011"
    session_id = "10000000-0000-0000-0000-000000000001"
    turn_id = "20000000-0000-0000-0000-000000000001"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "INSERT INTO workspaces (id, name, slug, created_at, updated_at) "
            "VALUES (?, 'Harness', 'harness', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            (workspace_id,),
        )
        connection.execute(
            "INSERT INTO agent_sessions "
            "(id, workspace_id, user_id, title, role_profile, permission_mode, "
            "automation_mode, runtime_mode, prompt_snapshot, status, created_at, "
            "updated_at) VALUES (?, ?, 'user-1', 'Canonical order', "
            "'bioinformatician', 'guarded_auto', 'assisted', 'api', '{}', "
            "'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            (session_id, workspace_id),
        )
        connection.execute(
            "INSERT INTO agent_turns "
            "(id, session_id, workspace_id, user_id, input_text, status, "
            "iteration_count, tool_batch_sequence, accepts_steer, created_at, "
            "updated_at) VALUES (?, ?, ?, 'user-1', 'ordered', 'completed', "
            "0, 0, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            (turn_id, session_id, workspace_id),
        )
        for index, role, text, created_at in (
            (1, "user", "first", "2026-08-13 10:00:01"),
            (2, "assistant", "second", "2026-08-13 10:00:00"),
            (3, "tool", "third", "2026-08-13 09:59:59"),
        ):
            connection.execute(
                "INSERT INTO agent_messages "
                "(id, session_id, turn_id, role, content_parts, status, "
                "ordering_index, created_at, updated_at) VALUES (?, ?, ?, ?, ?, "
                "'committed', ?, ?, ?)",
                (
                    f"50000000-0000-0000-0000-{index:012d}",
                    session_id,
                    turn_id,
                    role,
                    json.dumps([{"type": "text", "text": text}]),
                    index,
                    created_at,
                    created_at,
                ),
            )
        connection.commit()

    upgraded = _run_alembic(db_path, "upgrade", "head")
    assert upgraded.returncode == 0, upgraded.stderr

    with sqlite3.connect(db_path) as connection:
        rows = connection.execute(
            "SELECT payload FROM agent_entries WHERE session_id = ? ORDER BY sequence",
            (session_id,),
        ).fetchall()

    parts = [json.loads(row[0])["parts"][0] for row in rows]
    assert [part.get("text", part.get("display_text")) for part in parts] == [
        "first",
        "second",
        "third",
    ]


def test_complete_harness_migration_normalizes_legacy_tool_and_attachment_history(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "legacy-history.db"
    previous = _run_alembic(db_path, "upgrade", PREVIOUS_REVISION)
    assert previous.returncode == 0, previous.stderr

    workspace_id = "00000000-0000-0000-0000-000000000011"
    session_id = "10000000-0000-0000-0000-000000000001"
    turn_id = "20000000-0000-0000-0000-000000000001"
    attachment_id = "30000000-0000-0000-0000-000000000001"
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "INSERT INTO workspaces (id, name, slug, created_at, updated_at) "
            "VALUES (?, 'Harness', 'harness', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            (workspace_id,),
        )
        connection.execute(
            "INSERT INTO agent_sessions "
            "(id, workspace_id, user_id, title, role_profile, permission_mode, "
            "automation_mode, runtime_mode, prompt_snapshot, status, created_at, updated_at) "
            "VALUES (?, ?, 'user-1', 'Migrated', 'bioinformatician', 'guarded_auto', "
            "'assisted', 'api', '{}', 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            (session_id, workspace_id),
        )
        connection.execute(
            "INSERT INTO agent_turns "
            "(id, session_id, workspace_id, user_id, input_text, status, "
            "iteration_count, tool_batch_sequence, accepts_steer, created_at, updated_at) "
            "VALUES (?, ?, ?, 'user-1', 'Inspect the image', 'completed', "
            "0, 0, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            (turn_id, session_id, workspace_id),
        )
        connection.execute(
            "INSERT INTO agent_attachments "
            "(id, session_id, workspace_id, user_id, kind, source, filename, "
            "storage_path, size_bytes, status, created_at, updated_at) "
            "VALUES (?, ?, ?, 'user-1', 'image', 'upload', 'plot.png', "
            "'/tmp/plot.png', 12, 'ready', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            (attachment_id, session_id, workspace_id),
        )
        messages = (
            (
                "50000000-0000-0000-0000-000000000001",
                "assistant",
                [
                    {
                        "type": "tool_calls",
                        "tool_calls": [
                            {
                                "id": "read-1",
                                "name": "read",
                                "arguments": {"path": "results.txt"},
                            }
                        ],
                    }
                ],
                None,
                1,
            ),
            (
                "50000000-0000-0000-0000-000000000002",
                "tool",
                [{"type": "text", "text": "missing"}],
                {"tool_call_id": "read-1", "is_error": True},
                2,
            ),
            (
                "50000000-0000-0000-0000-000000000003",
                "user",
                [
                    {"type": "text", "text": "Inspect this image."},
                    {
                        "type": "image_ref",
                        "attachment_id": attachment_id,
                        "sha256": "legacy-sha",
                        "detail": "high",
                    },
                ],
                None,
                3,
            ),
        )
        for message_id, role, parts, metadata, ordering_index in messages:
            connection.execute(
                "INSERT INTO agent_messages "
                "(id, session_id, turn_id, role, content_parts, metadata, status, "
                "ordering_index, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, "
                "'committed', ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
                (
                    message_id,
                    session_id,
                    turn_id,
                    role,
                    json.dumps(parts),
                    json.dumps(metadata) if metadata is not None else None,
                    ordering_index,
                ),
            )
        connection.commit()

    upgraded = _run_alembic(db_path, "upgrade", "head")
    assert upgraded.returncode == 0, upgraded.stderr

    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            "SELECT sequence, type, payload FROM agent_entries ORDER BY sequence"
        ).fetchall()
    entries = [
        {
            "sequence": row["sequence"],
            "type": row["type"],
            "payload": json.loads(row["payload"]),
        }
        for row in rows
    ]

    assert entries[0]["payload"]["parts"] == [
        {
            "id": "tool-call:read-1",
            "type": "tool_call",
            "call_id": "read-1",
            "group_id": "50000000-0000-0000-0000-000000000001",
            "execution_mode": "serial",
            "name": "read",
            "display_name": "read",
            "category": "read",
            "summary": "read: results.txt",
            "arguments": {"path": "results.txt"},
        }
    ]
    assert entries[1]["payload"]["parts"] == [
        {
            "id": "tool-result:read-1",
            "type": "tool_result",
            "call_id": "read-1",
            "status": "failed",
            "output": {"type": "text", "text": "missing"},
            "error": "missing",
        }
    ]
    assert entries[2]["payload"]["parts"][1] == {
        "id": f"attachment:{attachment_id}",
        "type": "attachment_ref",
        "attachment_id": attachment_id,
        "filename": "plot.png",
        "kind": "image",
        "mime_type": None,
        "size_bytes": 12,
    }

    history = build_history_view(
        entries,
        attachment_parts_by_id={attachment_id: (TextPart("image-loaded"),)},
    )
    assert history.input_items == (
        ToolCallPart(
            call_id="read-1",
            name="read",
            arguments={"path": "results.txt"},
        ),
        ToolResultPart(call_id="read-1", output="missing", is_error=True),
        TextPart("Inspect this image."),
        TextPart("image-loaded"),
    )
