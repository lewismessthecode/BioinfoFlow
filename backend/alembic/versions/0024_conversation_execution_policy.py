"""add conversation execution_policy

Revision ID: 0024_conversation_execution_policy
Revises: 0023_add_hermes_agent_handles
Create Date: 2026-04-20
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0024_conversation_execution_policy"
down_revision = "0023_add_hermes_agent_handles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Per-conversation execution mode. NULL means "fall back to the
    # settings.agent_execution_policy default". Explicit values ("auto",
    # "approve_all", "bypass") override the global for this conversation
    # only. Users set this via the composer mode picker; toggling emits
    # `agent.execution_policy_changed` in the log for audit.
    with op.batch_alter_table("conversations") as batch:
        batch.add_column(
            sa.Column("execution_policy", sa.String(length=20), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("conversations") as batch:
        batch.drop_column("execution_policy")
