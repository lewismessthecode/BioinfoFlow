"""add weight column to workflows and scheduled_tasks

Revision ID: 0013_add_weight_to_workflow_and_task
Revises: 0012_add_openrouter_ollama_settings
Create Date: 2026-04-05
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0013_add_weight_to_workflow_and_task"
down_revision = "0012_add_openrouter_ollama_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "workflows",
        sa.Column("weight", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "scheduled_tasks",
        sa.Column("weight", sa.Integer(), nullable=False, server_default="1"),
    )


def downgrade() -> None:
    op.drop_column("scheduled_tasks", "weight")
    op.drop_column("workflows", "weight")
