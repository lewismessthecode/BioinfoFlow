"""drop legacy user settings

Revision ID: 0034_drop_legacy_user_settings
Revises: 0033_llm_profile_runtime_strategy
Create Date: 2026-06-10
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0034_drop_legacy_user_settings"
down_revision = "0033_llm_profile_runtime_strategy"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    if _table_exists("user_settings"):
        op.drop_index("ix_user_settings_user_id", table_name="user_settings")
        op.drop_table("user_settings")


def downgrade() -> None:
    if _table_exists("user_settings"):
        return
    op.create_table(
        "user_settings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("provider_credentials", sa.Text(), server_default="{}", nullable=False),
        sa.Column("anthropic_api_key", sa.String(length=500), server_default="", nullable=False),
        sa.Column("openai_api_key", sa.String(length=500), server_default="", nullable=False),
        sa.Column("openai_base_url", sa.String(length=500), server_default="", nullable=False),
        sa.Column("gemini_api_key", sa.String(length=500), server_default="", nullable=False),
        sa.Column("openrouter_api_key", sa.String(length=500), server_default="", nullable=False),
        sa.Column("ollama_base_url", sa.String(length=500), server_default="", nullable=False),
        sa.Column("ollama_model", sa.String(length=100), server_default="", nullable=False),
        sa.Column("deepseek_api_key", sa.String(length=500), server_default="", nullable=False),
        sa.Column("qwen_api_key", sa.String(length=500), server_default="", nullable=False),
        sa.Column("kimi_api_key", sa.String(length=500), server_default="", nullable=False),
        sa.Column("minimax_api_key", sa.String(length=500), server_default="", nullable=False),
        sa.Column("selected_provider", sa.String(length=50), server_default="auto", nullable=False),
        sa.Column("selected_model", sa.String(length=100), server_default="", nullable=False),
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
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_settings_user_id", "user_settings", ["user_id"], unique=True)
