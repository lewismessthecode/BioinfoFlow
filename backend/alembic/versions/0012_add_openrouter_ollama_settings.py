"""add openrouter and ollama to user_settings

Revision ID: 0012_add_openrouter_ollama_settings
Revises: 0011_add_data_roots_to_projects
Create Date: 2026-04-02
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0012_add_openrouter_ollama_settings"
down_revision = "0011_add_data_roots_to_projects"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_settings",
        sa.Column("openrouter_api_key", sa.String(length=500), server_default="", nullable=False),
    )
    op.add_column(
        "user_settings",
        sa.Column("ollama_base_url", sa.String(length=500), server_default="", nullable=False),
    )
    op.add_column(
        "user_settings",
        sa.Column("ollama_model", sa.String(length=100), server_default="", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("user_settings", "ollama_model")
    op.drop_column("user_settings", "ollama_base_url")
    op.drop_column("user_settings", "openrouter_api_key")
