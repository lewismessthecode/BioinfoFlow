"""order durable agent tool call batches

Revision ID: 0046_agent_tool_batch_order
Revises: 0045_agent_tool_call_batches
Create Date: 2026-07-13
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0046_agent_tool_batch_order"
down_revision = "0045_agent_tool_call_batches"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("agent_tool_call_batches") as batch:
        batch.add_column(sa.Column("batch_ordinal", sa.Integer(), nullable=True))
        batch.create_unique_constraint(
            "uq_agent_tool_batches_turn_ordinal", ["turn_id", "batch_ordinal"]
        )


def downgrade() -> None:
    with op.batch_alter_table("agent_tool_call_batches") as batch:
        batch.drop_constraint("uq_agent_tool_batches_turn_ordinal", type_="unique")
        batch.drop_column("batch_ordinal")
