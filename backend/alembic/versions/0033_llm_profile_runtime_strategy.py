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


def _existing_columns(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {column["name"] for column in inspector.get_columns(table_name)}


def _is_sqlite() -> bool:
    return op.get_bind().dialect.name == "sqlite"


def upgrade() -> None:
    columns = _existing_columns("llm_model_profiles")

    additions = (
        ("prefer_streaming", sa.Column("prefer_streaming", sa.Boolean(), nullable=False, server_default=sa.true())),
        ("allow_thinking", sa.Column("allow_thinking", sa.Boolean(), nullable=False, server_default=sa.true())),
        ("allow_tools", sa.Column("allow_tools", sa.Boolean(), nullable=False, server_default=sa.true())),
    )
    for column_name, column in additions:
        if column_name not in columns:
            op.add_column("llm_model_profiles", column)

    if not _is_sqlite():
        op.alter_column("llm_model_profiles", "prefer_streaming", server_default=None)
        op.alter_column("llm_model_profiles", "allow_thinking", server_default=None)
        op.alter_column("llm_model_profiles", "allow_tools", server_default=None)


def downgrade() -> None:
    columns = _existing_columns("llm_model_profiles")

    if "allow_tools" in columns:
        op.drop_column("llm_model_profiles", "allow_tools")
    if "allow_thinking" in columns:
        op.drop_column("llm_model_profiles", "allow_thinking")
    if "prefer_streaming" in columns:
        op.drop_column("llm_model_profiles", "prefer_streaming")
