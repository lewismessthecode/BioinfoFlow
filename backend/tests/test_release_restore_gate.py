from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path

from cryptography.fernet import Fernet


BACKEND_DIR = Path(__file__).resolve().parents[1]
RELEASE_020_HEAD = "0058_remove_container_registry_default"
RELEASE_HEAD = "0063_agent_session_project_delete_cascade"


def _run_alembic(db_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    home = db_path.parent.parent
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND_DIR,
        env={
            **os.environ,
            "BIOINFOFLOW_HOME": str(home),
            "DATABASE_URL": f"sqlite+aiosqlite:///{db_path}",
        },
        capture_output=True,
        text=True,
        check=False,
    )


def _seed_release_020_clone(db_path: Path) -> dict[str, str]:
    upgraded = _run_alembic(db_path, "upgrade", RELEASE_020_HEAD)
    assert upgraded.returncode == 0, upgraded.stderr or upgraded.stdout

    ids = {
        "workspace": "00000000-0000-0000-0000-000000000011",
        "project": "00000000-0000-0000-0000-000000000012",
        "session": "00000000-0000-0000-0000-000000000013",
        "turn": "00000000-0000-0000-0000-000000000014",
        "message": "00000000-0000-0000-0000-000000000015",
        "attachment": "00000000-0000-0000-0000-000000000016",
        "artifact": "00000000-0000-0000-0000-000000000017",
    }
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "INSERT INTO workspaces (id, name, slug, created_at, updated_at) "
            "VALUES (?, '0.2 workspace', 'release-020', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            (ids["workspace"],),
        )
        connection.execute(
            "INSERT INTO projects "
            "(id, name, storage_mode, user_id, workspace_id, is_default, "
            "created_at, updated_at) VALUES "
            "(?, '0.2 project', 'managed', 'release-test', ?, 0, "
            "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            (ids["project"], ids["workspace"]),
        )
        connection.execute(
            "INSERT INTO agent_sessions "
            "(id, workspace_id, project_id, user_id, title, role_profile, "
            "permission_mode, automation_mode, runtime_mode, prompt_snapshot, "
            "status, created_at, updated_at) VALUES "
            "(?, ?, ?, 'release-test', '0.2 session', 'bioinformatician', "
            "'guarded_auto', 'assisted', 'api', ?, 'active', "
            "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            (
                ids["session"],
                ids["workspace"],
                ids["project"],
                json.dumps({"content": "legacy release evidence"}),
            ),
        )
        connection.execute(
            "INSERT INTO agent_turns "
            "(id, session_id, workspace_id, user_id, input_text, status, "
            "iteration_count, tool_batch_sequence, accepts_steer, created_at, "
            "updated_at) VALUES "
            "(?, ?, ?, 'release-test', 'preserve this history', 'completed', "
            "0, 0, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            (ids["turn"], ids["session"], ids["workspace"]),
        )
        connection.execute(
            "INSERT INTO agent_messages "
            "(id, session_id, turn_id, role, content_parts, status, ordering_index, "
            "created_at, updated_at) VALUES "
            "(?, ?, ?, 'user', ?, 'committed', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            (
                ids["message"],
                ids["session"],
                ids["turn"],
                json.dumps([{"type": "text", "text": "preserve this history"}]),
            ),
        )
        connection.execute(
            "INSERT INTO agent_attachments "
            "(id, session_id, workspace_id, user_id, kind, source, filename, "
            "storage_path, size_bytes, status, created_at, updated_at) VALUES "
            "(?, ?, ?, 'release-test', 'file', 'upload', 'reads.fastq.gz', "
            "'/tmp/release-020-reads.fastq.gz', 42, 'ready', "
            "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            (ids["attachment"], ids["session"], ids["workspace"]),
        )
        connection.execute(
            "INSERT INTO agent_artifacts "
            "(id, session_id, turn_id, type, title, file_path, created_at, updated_at) "
            "VALUES (?, ?, ?, 'file', '0.2 report', '/tmp/release-020-report.txt', "
            "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            (ids["artifact"], ids["session"], ids["turn"]),
        )
        connection.commit()
    return ids


def test_representative_020_sqlite_clone_upgrades_to_head(tmp_path: Path) -> None:
    db_path = tmp_path / "bioinfoflow-home" / "state" / "bioinfoflow.db"
    ids = _seed_release_020_clone(db_path)

    upgraded = _run_alembic(db_path, "upgrade", "head")
    assert upgraded.returncode == 0, upgraded.stderr or upgraded.stdout

    with sqlite3.connect(db_path) as connection:
        connection.row_factory = sqlite3.Row
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        session = connection.execute(
            "SELECT project_id, status, history_revision "
            "FROM agent_sessions WHERE id = ?",
            (ids["session"],),
        ).fetchone()
        entry = connection.execute(
            "SELECT type, payload FROM agent_entries WHERE session_id = ?",
            (ids["session"],),
        ).fetchone()
        attachment = connection.execute(
            "SELECT filename FROM agent_attachments WHERE id = ?",
            (ids["attachment"],),
        ).fetchone()
        artifact = connection.execute(
            "SELECT run_id, title FROM agent_artifacts WHERE id = ?",
            (ids["artifact"],),
        ).fetchone()
        revision = connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()

        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("DELETE FROM projects WHERE id = ?", (ids["project"],))
        deleted_session = connection.execute(
            "SELECT id FROM agent_sessions WHERE id = ?", (ids["session"],)
        ).fetchone()

    assert session is not None
    assert tuple(session) == (ids["project"], "active", 1)
    assert entry is not None
    assert entry["type"] == "message"
    assert json.loads(entry["payload"])["parts"][0]["text"] == ("preserve this history")
    assert tuple(attachment) == ("reads.fastq.gz",)
    assert tuple(artifact) == (ids["turn"], "0.2 report")
    assert {"agent_sessions", "agent_runs", "agent_entries"} <= tables
    assert {"agent_attachments", "agent_artifacts"} <= tables
    assert "agent_turns" not in tables
    assert tuple(revision) == (RELEASE_HEAD,)
    assert deleted_session is None


def _seed_current_home(home: Path) -> dict[str, str | bytes]:
    state = home / "state"
    platform_db = state / "bioinfoflow.db"
    auth_db = state / "auth" / "better-auth.db"
    upgraded = _run_alembic(platform_db, "upgrade", "head")
    assert upgraded.returncode == 0, upgraded.stderr or upgraded.stdout

    ids = {
        "workspace": "10000000-0000-0000-0000-000000000011",
        "project": "10000000-0000-0000-0000-000000000012",
        "session": "10000000-0000-0000-0000-000000000013",
        "run": "10000000-0000-0000-0000-000000000014",
        "entry": "10000000-0000-0000-0000-000000000015",
        "attachment": "10000000-0000-0000-0000-000000000016",
        "artifact": "10000000-0000-0000-0000-000000000017",
        "provider": "10000000-0000-0000-0000-000000000018",
        "credential": "10000000-0000-0000-0000-000000000019",
    }
    key = Fernet.generate_key()
    credential = Fernet(key).encrypt(b"restore-gate-secret").decode()
    key_path = state / "credentials" / "fernet.key"
    key_path.parent.mkdir(parents=True, exist_ok=True)
    key_path.write_bytes(key)

    project_root = home / "projects" / "restore-project"
    workflow_root = state / "workflows" / "local" / "restore-workflow" / "bundle"
    source_files = {
        project_root / "data" / "reads.fastq": "project input",
        project_root / "runs" / "run-restore" / "results" / "report.txt": "run result",
        workflow_root / "main.wdl": "version 1.0",
        home / "sources" / "deliveries" / "delivery.fastq": "delivery",
        home / "sources" / "reference" / "reference.fa": ">reference",
        home / "sources" / "database" / "annotation.db": "annotation",
        state
        / "agent_harness"
        / "attachments"
        / ids["session"]
        / ids["attachment"]
        / "payload.bin": "attachment",
        state
        / "agent_harness"
        / "artifacts"
        / ids["session"]
        / ids["artifact"]
        / "report.html": "artifact",
    }
    for path, contents in source_files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents)

    with sqlite3.connect(platform_db) as connection:
        connection.execute(
            "INSERT INTO workspaces (id, name, slug, created_at, updated_at) "
            "VALUES (?, 'Restore workspace', 'restore-gate', CURRENT_TIMESTAMP, "
            "CURRENT_TIMESTAMP)",
            (ids["workspace"],),
        )
        connection.execute(
            "INSERT INTO projects "
            "(id, name, directory_name, storage_mode, user_id, workspace_id, "
            "is_default, created_at, updated_at) VALUES "
            "(?, 'Restore project', 'restore-project', 'managed', 'restore-test', "
            "?, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            (ids["project"], ids["workspace"]),
        )
        connection.execute(
            "INSERT INTO agent_sessions "
            "(id, workspace_id, project_id, user_id, title, permission_mode, "
            "workspace_access, settings_revision, environment_scope, prompt_snapshot, "
            "history_revision, command_queue, command_ids, status, created_at, "
            "updated_at) VALUES "
            "(?, ?, ?, 'restore-test', 'Restore history', 'ask_changes', "
            "'read_write', 1, ?, ?, 2, '[]', '[]', 'completed', "
            "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            (
                ids["session"],
                ids["workspace"],
                ids["project"],
                json.dumps({"mode": "auto"}),
                json.dumps({"content": "history survives restore"}),
            ),
        )
        connection.execute(
            "INSERT INTO agent_runs "
            "(id, session_id, status, phase, revision, lease_generation, "
            "command_queue, command_ids, draft, tool_progress, checkpoint, "
            "retry_count, created_at, updated_at) VALUES "
            "(?, ?, 'completed', 'final', 1, 0, '[]', '[]', ?, '[]', NULL, "
            "0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            (ids["run"], ids["session"], json.dumps({"text": "done"})),
        )
        connection.execute(
            "INSERT INTO agent_entries "
            "(id, session_id, run_id, sequence, type, schema_version, payload, "
            "created_at, updated_at) VALUES "
            "(?, ?, ?, 1, 'message', 2, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            (
                ids["entry"],
                ids["session"],
                ids["run"],
                json.dumps(
                    {
                        "role": "assistant",
                        "parts": [{"id": "text:0", "type": "text", "text": "done"}],
                    }
                ),
            ),
        )
        attachment_path = (
            state
            / "agent_harness"
            / "attachments"
            / ids["session"]
            / ids["attachment"]
            / "payload.bin"
        )
        connection.execute(
            "INSERT INTO agent_attachments "
            "(id, session_id, workspace_id, user_id, kind, source, filename, "
            "storage_path, mime_type, size_bytes, status, created_at, updated_at) "
            "VALUES (?, ?, ?, 'restore-test', 'file', 'upload', 'payload.bin', "
            "?, 'application/octet-stream', 10, 'ready', CURRENT_TIMESTAMP, "
            "CURRENT_TIMESTAMP)",
            (ids["attachment"], ids["session"], ids["workspace"], str(attachment_path)),
        )
        artifact_path = (
            state
            / "agent_harness"
            / "artifacts"
            / ids["session"]
            / ids["artifact"]
            / "report.html"
        )
        connection.execute(
            "INSERT INTO agent_artifacts "
            "(id, session_id, run_id, type, title, file_path, created_at, updated_at) "
            "VALUES (?, ?, ?, 'file', 'Restore report', ?, CURRENT_TIMESTAMP, "
            "CURRENT_TIMESTAMP)",
            (ids["artifact"], ids["session"], ids["run"], str(artifact_path)),
        )
        connection.execute(
            "INSERT INTO llm_providers "
            "(id, name, kind, wire_protocol, scope, user_id, enabled, created_at, "
            "updated_at) VALUES (?, 'Restore provider', 'openai', "
            "'chat_completions', 'user', 'restore-test', 1, CURRENT_TIMESTAMP, "
            "CURRENT_TIMESTAMP)",
            (ids["provider"],),
        )
        connection.execute(
            "INSERT INTO llm_provider_credentials "
            "(id, provider_id, source, encrypted_secret, fingerprint, created_at, "
            "updated_at) VALUES (?, ?, 'stored', ?, 'restore-fingerprint', "
            "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
            (ids["credential"], ids["provider"], credential),
        )
        connection.commit()

    auth_db.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(auth_db) as connection:
        connection.execute(
            "CREATE TABLE user (id TEXT PRIMARY KEY, email TEXT NOT NULL)"
        )
        connection.execute(
            "INSERT INTO user (id, email) VALUES ('restore-user', 'restore@example.test')"
        )
        connection.commit()

    return {
        **ids,
        "key": key,
        "credential_token": credential,
    }


def test_stopped_home_backup_restore_retains_state_and_credentials(
    tmp_path: Path,
) -> None:
    home = tmp_path / "bioinfoflow-home"
    records = _seed_current_home(home)
    platform_db = home / "state" / "bioinfoflow.db"
    auth_db = home / "state" / "auth" / "better-auth.db"
    backup = tmp_path / "bioinfoflow-home-backup"

    # The fixture has no open application/database handles: this models the
    # stopped or quiesced service precondition for a filesystem-level backup.
    shutil.copytree(home, backup)

    shutil.rmtree(home)
    shutil.copytree(backup, home)

    expected_files = {
        home / "projects" / "restore-project" / "data" / "reads.fastq": "project input",
        home
        / "projects"
        / "restore-project"
        / "runs"
        / "run-restore"
        / "results"
        / "report.txt": "run result",
        home
        / "state"
        / "workflows"
        / "local"
        / "restore-workflow"
        / "bundle"
        / "main.wdl": "version 1.0",
        home / "sources" / "deliveries" / "delivery.fastq": "delivery",
        home / "sources" / "reference" / "reference.fa": ">reference",
        home / "sources" / "database" / "annotation.db": "annotation",
        home
        / "state"
        / "agent_harness"
        / "attachments"
        / records["session"]
        / records["attachment"]
        / "payload.bin": "attachment",
        home
        / "state"
        / "agent_harness"
        / "artifacts"
        / records["session"]
        / records["artifact"]
        / "report.html": "artifact",
    }
    for path, contents in expected_files.items():
        assert path.read_text() == contents

    restored_key = (home / "state" / "credentials" / "fernet.key").read_bytes()
    assert restored_key == records["key"]
    assert (
        Fernet(restored_key)
        .decrypt(records["credential_token"].encode("utf-8"))
        .decode("utf-8")
        == "restore-gate-secret"
    )

    with sqlite3.connect(platform_db) as connection:
        history = connection.execute(
            "SELECT history_revision FROM agent_sessions WHERE id = ?",
            (records["session"],),
        ).fetchone()
        history_entry = connection.execute(
            "SELECT payload FROM agent_entries WHERE id = ?",
            (records["entry"],),
        ).fetchone()
        attachment = connection.execute(
            "SELECT storage_path FROM agent_attachments WHERE id = ?",
            (records["attachment"],),
        ).fetchone()
        artifact = connection.execute(
            "SELECT file_path FROM agent_artifacts WHERE id = ?",
            (records["artifact"],),
        ).fetchone()
        credential = connection.execute(
            "SELECT encrypted_secret FROM llm_provider_credentials WHERE id = ?",
            (records["credential"],),
        ).fetchone()
    with sqlite3.connect(auth_db) as connection:
        auth_user = connection.execute(
            "SELECT email FROM user WHERE id = 'restore-user'"
        ).fetchone()

    assert history == (2,)
    assert json.loads(history_entry[0])["parts"][0]["text"] == "done"
    assert Path(attachment[0]).read_text() == "attachment"
    assert Path(artifact[0]).read_text() == "artifact"
    assert credential == (records["credential_token"],)
    assert auth_user == ("restore@example.test",)
