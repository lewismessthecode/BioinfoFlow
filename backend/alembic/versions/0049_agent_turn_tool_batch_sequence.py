"""serialize per-turn tool batch ordinals

Revision ID: 0049_agent_turn_tool_batch_sequence
Revises: 0048_agent_tool_batch_order
Create Date: 2026-07-13
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0049_agent_turn_tool_batch_sequence"
down_revision = "0048_agent_tool_batch_order"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if not _table_exists("agent_turns"):
        return
    with op.batch_alter_table("agent_turns") as batch:
        batch.add_column(
            sa.Column(
                "tool_batch_sequence",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )
    op.execute(
        sa.text(
            """
            UPDATE agent_turns
            SET tool_batch_sequence = COALESCE(
                (
                    SELECT MAX(agent_tool_call_batches.batch_ordinal)
                    FROM agent_tool_call_batches
                    WHERE agent_tool_call_batches.turn_id = agent_turns.id
                ),
                0
            )
            """
        )
    )


def downgrade() -> None:
    if not _table_exists("agent_turns"):
        return
    with op.batch_alter_table("agent_turns") as batch:
        batch.drop_column("tool_batch_sequence")
