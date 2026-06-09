"""add llm profile runtime strategy fields

Revision ID: 0033_llm_profile_runtime_strategy
Revises: 0032_seed_ollama_deepseek_r1
Create Date: 2026-06-09
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0033_llm_profile_runtime_strategy"
down_revision = "0032_seed_ollama_deepseek_r1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "llm_model_profiles",
        sa.Column("prefer_streaming", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "llm_model_profiles",
        sa.Column("allow_thinking", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "llm_model_profiles",
        sa.Column("allow_tools", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.alter_column("llm_model_profiles", "prefer_streaming", server_default=None)
    op.alter_column("llm_model_profiles", "allow_thinking", server_default=None)
    op.alter_column("llm_model_profiles", "allow_tools", server_default=None)


def downgrade() -> None:
    op.drop_column("llm_model_profiles", "allow_tools")
    op.drop_column("llm_model_profiles", "allow_thinking")
    op.drop_column("llm_model_profiles", "prefer_streaming")
