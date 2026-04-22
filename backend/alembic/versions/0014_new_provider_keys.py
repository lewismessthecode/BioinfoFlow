"""add deepseek qwen kimi minimax api key columns

Revision ID: 0014_new_provider_keys
Revises: 0013_add_weight_to_workflow_and_task
Create Date: 2026-04-07
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0014_new_provider_keys"
down_revision = "0013_add_weight_to_workflow_and_task"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("user_settings") as batch_op:
        batch_op.add_column(sa.Column("deepseek_api_key", sa.String(500), server_default="", nullable=False))
        batch_op.add_column(sa.Column("qwen_api_key", sa.String(500), server_default="", nullable=False))
        batch_op.add_column(sa.Column("kimi_api_key", sa.String(500), server_default="", nullable=False))
        batch_op.add_column(sa.Column("minimax_api_key", sa.String(500), server_default="", nullable=False))


def downgrade() -> None:
    with op.batch_alter_table("user_settings") as batch_op:
        batch_op.drop_column("minimax_api_key")
        batch_op.drop_column("kimi_api_key")
        batch_op.drop_column("qwen_api_key")
        batch_op.drop_column("deepseek_api_key")
