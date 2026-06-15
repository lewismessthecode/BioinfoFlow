from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

from app.database import get_alembic_head_revision


BACKEND_DIR = Path(__file__).resolve().parents[2]

PRE_REVISION = "0035_agent_turn_execution_leases"

BUILTIN_OLLAMA_PROVIDER_ID = "10000000-0000-4000-8000-000000000006"
BUILTIN_LLAMA_MODEL_ID = "11000000-0000-4000-8000-000000000010"
BUILTIN_DEEPSEEK_MODEL_ID = "11000000-0000-4000-8000-000000000011"
BUILTIN_AGENT_DEFAULT_PROFILE_ID = "12000000-0000-4000-8000-000000000001"


def _alembic_upgrade(db_path: Path, target: str) -> None:
    env = {
        **os.environ,
        "DATABASE_URL": f"sqlite+aiosqlite:///{db_path}",
    }
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", target],
        cwd=BACKEND_DIR,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_builtin_ollama_catalog_is_removed_while_manual_ollama_survives(tmp_path: Path):
    db_path = tmp_path / "builtin-ollama.db"

    # Build the schema and seed the historical built-in Ollama catalog by running
    # the real migration chain up to (but not including) the removal migration.
    _alembic_upgrade(db_path, PRE_REVISION)

    conn = sqlite3.connect(db_path)
    try:
        # Sanity: the built-in Ollama provider and its models exist pre-removal.
        builtin = conn.execute(
            "SELECT COUNT(*) FROM llm_providers WHERE id = ?",
            (BUILTIN_OLLAMA_PROVIDER_ID,),
        ).fetchone()
        assert builtin == (1,)
        assert conn.execute(
            "SELECT COUNT(*) FROM llm_models WHERE id IN (?, ?)",
            (BUILTIN_LLAMA_MODEL_ID, BUILTIN_DEEPSEEK_MODEL_ID),
        ).fetchone() == (2,)

        # A hand-configured (user-scoped) Ollama provider that must be preserved.
        conn.execute(
            """
            INSERT INTO llm_providers
              (id, name, kind, base_url, api_key_ref, scope, workspace_id, user_id,
               enabled, test_status, metadata, created_at, updated_at)
            VALUES
              ('aaaa1111-0000-4000-8000-000000000001', 'My Ollama', 'ollama',
               'http://127.0.0.1:11434', NULL, 'user', NULL, 'tester', 1, NULL,
               '{"providerTemplate": "ollama"}', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """
        )
        conn.execute(
            """
            INSERT INTO llm_models
              (id, provider_id, model_id, display_name, context_length,
               max_output_tokens, supports_tools, supports_streaming, supports_vision,
               supports_json_schema, supports_reasoning, created_at, updated_at)
            VALUES
              ('bbbb2222-0000-4000-8000-000000000001',
               'aaaa1111-0000-4000-8000-000000000001', 'qwen3', 'Qwen 3', NULL, NULL,
               1, 1, 0, 1, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """
        )

        # Point a profile fallback at a built-in Ollama model so we can confirm the
        # reference is scrubbed rather than left dangling.
        conn.execute(
            "UPDATE llm_model_profiles SET fallback_model_ids = ? WHERE id = ?",
            (
                f'["11000000-0000-4000-8000-000000000002", "{BUILTIN_DEEPSEEK_MODEL_ID}"]',
                BUILTIN_AGENT_DEFAULT_PROFILE_ID,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    _alembic_upgrade(db_path, "head")

    conn = sqlite3.connect(db_path)
    try:
        assert conn.execute("SELECT version_num FROM alembic_version").fetchone() == (
            get_alembic_head_revision(),
        )

        # Built-in Ollama provider, credential, and models are gone.
        assert conn.execute(
            "SELECT COUNT(*) FROM llm_providers WHERE id = ?",
            (BUILTIN_OLLAMA_PROVIDER_ID,),
        ).fetchone() == (0,)
        assert conn.execute(
            "SELECT COUNT(*) FROM llm_provider_credentials WHERE provider_id = ?",
            (BUILTIN_OLLAMA_PROVIDER_ID,),
        ).fetchone() == (0,)
        assert conn.execute(
            "SELECT COUNT(*) FROM llm_models WHERE id IN (?, ?)",
            (BUILTIN_LLAMA_MODEL_ID, BUILTIN_DEEPSEEK_MODEL_ID),
        ).fetchone() == (0,)

        # The hand-configured Ollama provider and its model are untouched.
        assert conn.execute(
            "SELECT enabled FROM llm_providers WHERE id = ?",
            ("aaaa1111-0000-4000-8000-000000000001",),
        ).fetchone() == (1,)
        assert conn.execute(
            "SELECT model_id FROM llm_models WHERE id = ?",
            ("bbbb2222-0000-4000-8000-000000000001",),
        ).fetchone() == ("qwen3",)

        # The fallback reference to the built-in model was removed.
        fallback = conn.execute(
            "SELECT fallback_model_ids FROM llm_model_profiles WHERE id = ?",
            (BUILTIN_AGENT_DEFAULT_PROFILE_ID,),
        ).fetchone()[0]
        assert BUILTIN_DEEPSEEK_MODEL_ID not in fallback
        assert "11000000-0000-4000-8000-000000000002" in fallback
    finally:
        conn.close()


def test_builtin_ollama_model_referenced_as_primary_is_kept_and_provider_disabled(
    tmp_path: Path,
):
    db_path = tmp_path / "builtin-ollama-primary.db"

    _alembic_upgrade(db_path, PRE_REVISION)

    conn = sqlite3.connect(db_path)
    try:
        # A profile whose primary model is the built-in Ollama llama3.3 entry.
        conn.execute(
            """
            INSERT INTO llm_model_profiles
              (id, name, task_type, primary_model_id, fallback_model_ids,
               reasoning_budget, max_tokens, prefer_streaming, allow_thinking,
               allow_tools, cost_ceiling, routing_policy, permission_overrides,
               scope, workspace_id, user_id, enabled, metadata, created_at, updated_at)
            VALUES
              ('cccc3333-0000-4000-8000-000000000001', 'Pinned Ollama', 'agent_core',
               ?, NULL, NULL, NULL, 1, 1, 1, NULL, NULL, NULL, 'global', NULL, NULL,
               1, NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (BUILTIN_LLAMA_MODEL_ID,),
        )
        conn.commit()
    finally:
        conn.close()

    _alembic_upgrade(db_path, "head")

    conn = sqlite3.connect(db_path)
    try:
        # The referenced model is retained (deleting it would orphan the profile).
        assert conn.execute(
            "SELECT COUNT(*) FROM llm_models WHERE id = ?",
            (BUILTIN_LLAMA_MODEL_ID,),
        ).fetchone() == (1,)
        # Its provider is kept but disabled so default selection skips it.
        assert conn.execute(
            "SELECT enabled FROM llm_providers WHERE id = ?",
            (BUILTIN_OLLAMA_PROVIDER_ID,),
        ).fetchone() == (0,)
        # The unreferenced built-in model is still removed.
        assert conn.execute(
            "SELECT COUNT(*) FROM llm_models WHERE id = ?",
            (BUILTIN_DEEPSEEK_MODEL_ID,),
        ).fetchone() == (0,)
    finally:
        conn.close()
