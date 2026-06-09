"""llm provider credentials

Revision ID: 0031_llm_provider_credentials
Revises: 0030_agent_harness_runtime
Create Date: 2026-06-08
"""

from __future__ import annotations

import hashlib
import json
import os
import base64
from pathlib import Path
import uuid

import sqlalchemy as sa
from alembic import op
from cryptography.fernet import Fernet


revision = "0031_llm_provider_credentials"
down_revision = "0030_agent_harness_runtime"
branch_labels = None
depends_on = None


PROVIDERS = [
    {
        "id": "10000000-0000-4000-8000-000000000001",
        "name": "OpenAI",
        "kind": "openai",
        "base_url": "https://api.openai.com/v1",
        "env_var": "OPENAI_API_KEY",
        "models": [
            ("11000000-0000-4000-8000-000000000001", "gpt-5.4", "GPT-5.4", 1_000_000, 16_384, True, True),
            ("11000000-0000-4000-8000-000000000002", "gpt-5.4-mini", "GPT-5.4 mini", 1_000_000, 16_384, True, True),
        ],
    },
    {
        "id": "10000000-0000-4000-8000-000000000002",
        "name": "Anthropic",
        "kind": "anthropic",
        "base_url": None,
        "env_var": "ANTHROPIC_API_KEY",
        "models": [
            ("11000000-0000-4000-8000-000000000003", "claude-sonnet-4-6", "Claude Sonnet 4.6", 200_000, 16_384, True, True),
            ("11000000-0000-4000-8000-000000000004", "claude-haiku-4-5", "Claude Haiku 4.5", 200_000, 8_192, True, False),
        ],
    },
    {
        "id": "10000000-0000-4000-8000-000000000003",
        "name": "Gemini",
        "kind": "gemini",
        "base_url": None,
        "env_var": "GEMINI_API_KEY",
        "models": [
            ("11000000-0000-4000-8000-000000000005", "gemini-3-flash-preview", "Gemini 3 Flash", 1_000_000, 16_384, True, True),
            ("11000000-0000-4000-8000-000000000006", "gemini-2.5-pro", "Gemini 2.5 Pro", 1_000_000, 16_384, True, True),
        ],
    },
    {
        "id": "10000000-0000-4000-8000-000000000004",
        "name": "OpenRouter",
        "kind": "openrouter",
        "base_url": "https://openrouter.ai/api/v1",
        "env_var": "OPENROUTER_API_KEY",
        "models": [
            ("11000000-0000-4000-8000-000000000007", "openrouter/auto", "OpenRouter Auto", 200_000, 8_192, True, False),
        ],
    },
    {
        "id": "10000000-0000-4000-8000-000000000005",
        "name": "DeepSeek",
        "kind": "deepseek",
        "base_url": None,
        "env_var": "DEEPSEEK_API_KEY",
        "models": [
            ("11000000-0000-4000-8000-000000000008", "deepseek-chat", "DeepSeek V3.2", 128_000, 8_192, True, False),
            ("11000000-0000-4000-8000-000000000009", "deepseek-reasoner", "DeepSeek V3.2 Thinking", 128_000, 8_192, True, True),
        ],
    },
    {
        "id": "10000000-0000-4000-8000-000000000006",
        "name": "Ollama",
        "kind": "ollama",
        "base_url": "http://localhost:11434",
        "env_var": None,
        "models": [
            ("11000000-0000-4000-8000-000000000010", "llama3.3", "Llama 3.3", 128_000, 8_192, True, False),
        ],
    },
]


def upgrade() -> None:
    op.create_table(
        "llm_provider_credentials",
        sa.Column("provider_id", sa.String(length=36), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("env_var_name", sa.String(length=120), nullable=True),
        sa.Column("encrypted_secret", sa.Text(), nullable=True),
        sa.Column("fingerprint", sa.String(length=64), nullable=True),
        sa.Column("masked_hint", sa.String(length=120), nullable=True),
        sa.Column("updated_by", sa.String(length=36), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["provider_id"],
            ["llm_providers.id"],
            name="fk_llm_provider_credentials_provider_id_llm_providers",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_llm_provider_credentials"),
        sa.UniqueConstraint(
            "provider_id",
            name="uq_llm_provider_credentials_provider_id",
        ),
    )
    op.create_index(
        "ix_llm_provider_credentials_provider_id",
        "llm_provider_credentials",
        ["provider_id"],
    )
    _seed_builtin_catalog()
    _migrate_legacy_user_settings()


def downgrade() -> None:
    op.drop_index(
        "ix_llm_provider_credentials_provider_id",
        table_name="llm_provider_credentials",
    )
    op.drop_table("llm_provider_credentials")


def _seed_builtin_catalog() -> None:
    bind = op.get_bind()

    for provider in PROVIDERS:
        bind.execute(
            sa.text(
                """
                INSERT INTO llm_providers
                  (id, name, kind, base_url, api_key_ref, scope, workspace_id, user_id,
                   enabled, test_status, metadata, created_at, updated_at)
                SELECT
                  :id, :name, :kind, :base_url, NULL, 'global', NULL, NULL,
                  1, NULL, :metadata, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                WHERE NOT EXISTS (
                  SELECT 1 FROM llm_providers
                  WHERE id = :id
                     OR (scope = 'global' AND workspace_id IS NULL
                         AND user_id IS NULL AND name = :name)
                )
                """
            ),
            {
                "id": provider["id"],
                "name": provider["name"],
                "kind": provider["kind"],
                "base_url": provider["base_url"],
                "metadata": json.dumps({"builtin": True}),
            },
        )
        bind.execute(
            sa.text(
                """
                INSERT INTO llm_provider_credentials
                  (id, provider_id, source, env_var_name, encrypted_secret, fingerprint,
                   masked_hint, updated_by, created_at, updated_at)
                SELECT
                  :id, :provider_id, :source, :env_var_name, NULL, NULL,
                  :masked_hint, NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                WHERE EXISTS (
                  SELECT 1 FROM llm_providers WHERE id = :provider_id
                )
                AND NOT EXISTS (
                  SELECT 1 FROM llm_provider_credentials
                  WHERE provider_id = :provider_id
                )
                """
            ),
            {
                "id": str(uuid.uuid4()),
                "provider_id": provider["id"],
                "source": "env" if provider["env_var"] else "none",
                "env_var_name": provider["env_var"],
                "masked_hint": f"env:{provider['env_var']}" if provider["env_var"] else None,
            },
        )
        for model in provider["models"]:
            bind.execute(
                sa.text(
                    """
                    INSERT INTO llm_models
                      (id, provider_id, model_id, display_name, context_length,
                       max_output_tokens, supports_tools, supports_streaming,
                       supports_vision, supports_json_schema, supports_reasoning,
                       default_temperature, default_top_p, cost_metadata, metadata,
                       created_at, updated_at)
                    SELECT
                      :id, :provider_id, :model_id, :display_name, :context_length,
                      :max_output_tokens, :supports_tools, 1, 0, 1, :supports_reasoning,
                      NULL, NULL, NULL, NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                    WHERE EXISTS (
                      SELECT 1 FROM llm_providers WHERE id = :provider_id
                    )
                    AND NOT EXISTS (
                      SELECT 1 FROM llm_models
                      WHERE provider_id = :provider_id AND model_id = :model_id
                    )
                    """
                ),
                {
                    "id": model[0],
                    "provider_id": provider["id"],
                    "model_id": model[1],
                    "display_name": model[2],
                    "context_length": model[3],
                    "max_output_tokens": model[4],
                    "supports_tools": model[5],
                    "supports_reasoning": model[6],
                },
            )

    bind.execute(
        sa.text(
            """
            INSERT INTO llm_model_profiles
              (id, name, task_type, primary_model_id, fallback_model_ids,
               reasoning_budget, max_tokens, cost_ceiling, routing_policy,
               permission_overrides, scope, workspace_id, user_id, enabled,
               metadata, created_at, updated_at)
            SELECT
              :id, 'Agent default', 'agent_core', :primary_model_id,
              :fallback_model_ids, 4096, 8192, NULL, :routing_policy, NULL,
              'global', NULL, NULL, 1, :metadata, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            WHERE EXISTS (
              SELECT 1 FROM llm_models WHERE id = :primary_model_id
            )
            AND NOT EXISTS (
              SELECT 1 FROM llm_model_profiles
              WHERE id = :id
                 OR (scope = 'global' AND workspace_id IS NULL
                     AND user_id IS NULL AND name = 'Agent default')
            )
            """
        ),
        {
            "id": "12000000-0000-4000-8000-000000000001",
            "primary_model_id": "11000000-0000-4000-8000-000000000003",
            "fallback_model_ids": json.dumps(["11000000-0000-4000-8000-000000000002"]),
            "routing_policy": json.dumps({"fallback": "on_error"}),
            "metadata": json.dumps({"builtin": True}),
        },
    )


def _migrate_legacy_user_settings() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT id, user_id, provider_credentials, selected_provider, selected_model "
            "FROM user_settings"
        )
    ).mappings()
    builtin_provider_ids = {
        str(row.kind): str(row.id)
        for row in bind.execute(
            sa.text("SELECT id, kind FROM llm_providers WHERE scope = 'global'")
        )
    }
    migrated_provider_ids: dict[tuple[str, str], str] = {}
    model_ids = {
        (str(row.provider_id), str(row.model_id)): str(row.id)
        for row in bind.execute(sa.text("SELECT id, provider_id, model_id FROM llm_models"))
    }
    workspace_ids = {
        str(row.user_id): str(row.workspace_id)
        for row in bind.execute(
            sa.text(
                """
                SELECT user_id, MIN(workspace_id) AS workspace_id
                FROM workspace_memberships
                GROUP BY user_id
                """
            )
        )
    }

    for row in rows:
        user_id = str(row["user_id"])
        workspace_id = workspace_ids.get(user_id) or "00000000-0000-0000-0000-000000000001"
        try:
            credentials = json.loads(row["provider_credentials"] or "{}")
        except json.JSONDecodeError:
            credentials = {}
        for provider_key, fields in credentials.items():
            builtin_provider_id = builtin_provider_ids.get(str(provider_key))
            if not builtin_provider_id or not isinstance(fields, dict):
                continue
            api_key = str(fields.get("api_key") or "").strip()
            if not api_key or "..." in api_key:
                continue
            provider_id = str(uuid.uuid4())
            migrated_provider_ids[(user_id, str(provider_key))] = provider_id
            builtin = next(
                provider for provider in PROVIDERS if provider["kind"] == str(provider_key)
            )
            base_url = str(fields.get("base_url") or builtin["base_url"] or "").strip() or None
            provider_name = f"{builtin['name']} ({user_id[:8]})"
            bind.execute(
                sa.text(
                    """
                    INSERT INTO llm_providers
                      (id, name, kind, base_url, api_key_ref, scope, workspace_id, user_id,
                       enabled, test_status, metadata, created_at, updated_at)
                    VALUES
                      (:id, :name, :kind, :base_url, NULL, 'user', :workspace_id, :user_id,
                       1, NULL, :metadata, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    """
                ),
                {
                    "id": provider_id,
                    "name": provider_name,
                    "kind": builtin["kind"],
                    "base_url": base_url,
                    "workspace_id": workspace_id,
                    "user_id": user_id,
                    "metadata": json.dumps({"migrated_from": "user_settings"}),
                },
            )
            for model in builtin["models"]:
                migrated_model_id = str(uuid.uuid4())
                bind.execute(
                    sa.text(
                        """
                        INSERT INTO llm_models
                          (id, provider_id, model_id, display_name, context_length, max_output_tokens,
                           supports_tools, supports_streaming, supports_vision, supports_json_schema,
                           supports_reasoning, created_at, updated_at)
                        VALUES
                          (:id, :provider_id, :model_id, :display_name, :context_length, :max_output_tokens,
                           :supports_tools, 1, 0, 1, :supports_reasoning, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                        """
                    ),
                    {
                        "id": migrated_model_id,
                        "provider_id": provider_id,
                        "model_id": model[1],
                        "display_name": model[2],
                        "context_length": model[3],
                        "max_output_tokens": model[4],
                        "supports_tools": model[5],
                        "supports_reasoning": model[6],
                    },
                )
                model_ids[(provider_id, model[1])] = migrated_model_id
            bind.execute(
                sa.text(
                    """
                    INSERT INTO llm_provider_credentials
                      (id, provider_id, source, env_var_name, encrypted_secret, fingerprint, masked_hint, updated_by, created_at, updated_at)
                    VALUES
                      (:id, :provider_id, 'stored', NULL, :secret, :fingerprint, :masked_hint, :updated_by, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "provider_id": provider_id,
                    "secret": _encrypt_secret(api_key),
                    "fingerprint": hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:16],
                    "masked_hint": _mask_secret(api_key),
                    "updated_by": user_id,
                },
            )

        selected_provider = str(row["selected_provider"] or "").strip()
        selected_model = str(row["selected_model"] or "").strip()
        provider_id = migrated_provider_ids.get((user_id, selected_provider)) or builtin_provider_ids.get(selected_provider)
        model_id = model_ids.get((provider_id, selected_model)) if provider_id else None
        if model_id:
            bind.execute(
                sa.text(
                    """
                    INSERT INTO llm_model_profiles
                      (id, name, task_type, primary_model_id, fallback_model_ids, reasoning_budget, max_tokens,
                       cost_ceiling, routing_policy, permission_overrides, scope, workspace_id, user_id, enabled, metadata,
                       created_at, updated_at)
                    VALUES
                      (:id, :name, 'agent_core', :model_id, NULL, NULL, NULL, NULL, :routing_policy, NULL,
                       'user', :workspace_id, :user_id, 1, :metadata, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    """
                ),
                {
                    "id": str(uuid.uuid4()),
                    "name": "Migrated agent default",
                    "model_id": model_id,
                    "routing_policy": json.dumps({"fallback": "on_error"}),
                    "metadata": json.dumps({"legacy_user_settings_id": row["id"]}),
                    "workspace_id": workspace_id,
                    "user_id": user_id,
                },
            )


def _mask_secret(secret: str) -> str:
    if len(secret) <= 8:
        return f"{secret[:2]}...{secret[-2:]}"
    return f"{secret[:4]}...{secret[-4:]}"


def _encrypt_secret(secret: str) -> str:
    return Fernet(_credential_key()).encrypt(secret.encode("utf-8")).decode("utf-8")


def _credential_key() -> bytes:
    configured = os.getenv("BIOINFOFLOW_CREDENTIAL_KEY", "").strip()
    if configured:
        raw = configured.encode("utf-8")
        try:
            Fernet(raw)
            return raw
        except Exception:
            digest = hashlib.sha256(raw).digest()
            return base64.urlsafe_b64encode(digest)

    home = Path(os.getenv("BIOINFOFLOW_HOME") or "data").expanduser()
    path = home / "state" / "credentials" / "fernet.key"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return path.read_bytes().strip()
    key = Fernet.generate_key()
    path.write_bytes(key)
    return key
