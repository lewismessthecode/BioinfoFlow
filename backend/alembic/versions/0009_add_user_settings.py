"""add user_settings table

Revision ID: 0009_add_user_settings
Revises: 0008_add_user_id_to_projects_and_conversations
Create Date: 2026-04-02
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0009_add_user_settings"
down_revision = "0008_add_user_id_to_projects_and_conversations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_settings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("anthropic_api_key", sa.String(length=500), server_default="", nullable=False),
        sa.Column("openai_api_key", sa.String(length=500), server_default="", nullable=False),
        sa.Column("openai_base_url", sa.String(length=500), server_default="", nullable=False),
        sa.Column("gemini_api_key", sa.String(length=500), server_default="", nullable=False),
        sa.Column("selected_provider", sa.String(length=50), server_default="auto", nullable=False),
        sa.Column("selected_model", sa.String(length=100), server_default="", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_settings_user_id", "user_settings", ["user_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_user_settings_user_id", table_name="user_settings")
    op.drop_table("user_settings")
