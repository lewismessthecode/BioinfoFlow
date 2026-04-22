"""add provider_credentials JSON column and migrate legacy keys

Revision ID: 0015_provider_credentials_json
Revises: 0014_new_provider_keys
Create Date: 2026-04-07
"""

from __future__ import annotations

import json

from alembic import op
import sqlalchemy as sa


revision = "0015_provider_credentials_json"
down_revision = "0014_new_provider_keys"
branch_labels = None
depends_on = None

# Legacy column → JSON path mapping for data migration
_LEGACY_MAPPING = {
    "anthropic_api_key": ("anthropic", "api_key"),
    "openai_api_key": ("openai", "api_key"),
    "openai_base_url": ("openai", "base_url"),
    "gemini_api_key": ("gemini", "api_key"),
    "openrouter_api_key": ("openrouter", "api_key"),
    "ollama_base_url": ("ollama", "base_url"),
    "ollama_model": ("ollama", "model"),
    "deepseek_api_key": ("deepseek", "api_key"),
    "qwen_api_key": ("qwen", "api_key"),
    "kimi_api_key": ("kimi", "api_key"),
    "minimax_api_key": ("minimax", "api_key"),
}


def upgrade() -> None:
    # 1. Add the new column
    with op.batch_alter_table("user_settings") as batch_op:
        batch_op.add_column(
            sa.Column("provider_credentials", sa.Text(), server_default="{}", nullable=False)
        )

    # 2. Copy legacy column values into the JSON blob
    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            "SELECT id, anthropic_api_key, openai_api_key, openai_base_url, "
            "gemini_api_key, openrouter_api_key, ollama_base_url, ollama_model, "
            "deepseek_api_key, qwen_api_key, kimi_api_key, minimax_api_key "
            "FROM user_settings"
        )
    ).fetchall()

    for row in rows:
        row_id = row[0]
        creds: dict[str, dict[str, str]] = {}
        col_names = [
            "anthropic_api_key", "openai_api_key", "openai_base_url",
            "gemini_api_key", "openrouter_api_key", "ollama_base_url", "ollama_model",
            "deepseek_api_key", "qwen_api_key", "kimi_api_key", "minimax_api_key",
        ]
        for i, col in enumerate(col_names):
            val = row[i + 1]  # +1 because row[0] is id
            if val:
                provider, field = _LEGACY_MAPPING[col]
                if provider not in creds:
                    creds[provider] = {}
                creds[provider][field] = val

        if creds:
            conn.execute(
                sa.text("UPDATE user_settings SET provider_credentials = :creds WHERE id = :id"),
                {"creds": json.dumps(creds), "id": row_id},
            )


def downgrade() -> None:
    with op.batch_alter_table("user_settings") as batch_op:
        batch_op.drop_column("provider_credentials")
