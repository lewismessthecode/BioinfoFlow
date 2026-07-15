"""add timestamp defaults to agent tool batches

Revision ID: 0051_agent_tool_batch_timestamp_defaults
Revises: 0050_agent_session_active_turn
Create Date: 2026-07-15
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op


revision = "0051_agent_tool_batch_timestamp_defaults"
down_revision = "0050_agent_session_active_turn"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("agent_tool_call_batches"):
        return
    with op.batch_alter_table("agent_tool_call_batches") as batch:
        batch.alter_column(
            "created_at",
            existing_type=sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        )
        batch.alter_column(
            "updated_at",
            existing_type=sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("agent_tool_call_batches"):
        return
    with op.batch_alter_table("agent_tool_call_batches") as batch:
        batch.alter_column(
            "updated_at",
            existing_type=sa.DateTime(timezone=True),
            nullable=False,
            server_default=None,
        )
        batch.alter_column(
            "created_at",
            existing_type=sa.DateTime(timezone=True),
            nullable=False,
            server_default=None,
        )
