"""persist agent tool call batches

Revision ID: 0045_agent_tool_call_batches
Revises: 0044_agent_permission_policy
Create Date: 2026-07-13
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0045_agent_tool_call_batches"
down_revision = "0044_agent_permission_policy"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _column_names(table_name: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)}


def upgrade() -> None:
    if not _table_exists("agent_tool_call_batches"):
        op.create_table(
            "agent_tool_call_batches",
            sa.Column("session_id", sa.String(36), nullable=False),
            sa.Column("turn_id", sa.String(36), nullable=False),
            sa.Column("status", sa.String(30), nullable=False, server_default="evaluating"),
            sa.Column("tool_call_count", sa.Integer(), nullable=False),
            sa.Column("continuation_claimed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("id", sa.String(36), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["session_id"], ["agent_sessions.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["turn_id"], ["agent_turns.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_agent_tool_call_batches_session_id", "agent_tool_call_batches", ["session_id"])
        op.create_index("ix_agent_tool_call_batches_turn_id", "agent_tool_call_batches", ["turn_id"])
        op.create_index("ix_agent_tool_call_batches_status", "agent_tool_call_batches", ["status"])

    if _table_exists("agent_actions"):
        columns = _column_names("agent_actions")
        with op.batch_alter_table("agent_actions") as batch:
            if "tool_batch_id" not in columns:
                batch.add_column(sa.Column("tool_batch_id", sa.String(36), nullable=True))
                batch.create_foreign_key(
                    "fk_agent_actions_tool_batch_id",
                    "agent_tool_call_batches",
                    ["tool_batch_id"],
                    ["id"],
                    ondelete="CASCADE",
                )
                batch.create_index("ix_agent_actions_tool_batch_id", ["tool_batch_id"])
            if "tool_call_ordinal" not in columns:
                batch.add_column(sa.Column("tool_call_ordinal", sa.Integer(), nullable=True))
        with op.batch_alter_table("agent_actions") as batch:
            batch.create_unique_constraint(
                "uq_agent_actions_tool_batch_ordinal",
                ["tool_batch_id", "tool_call_ordinal"],
            )
            batch.create_unique_constraint(
                "uq_agent_actions_tool_batch_call_id",
                ["tool_batch_id", "tool_call_id"],
            )


def downgrade() -> None:
    if _table_exists("agent_actions"):
        columns = _column_names("agent_actions")
        with op.batch_alter_table("agent_actions") as batch:
            if "tool_call_ordinal" in columns:
                batch.drop_constraint("uq_agent_actions_tool_batch_ordinal", type_="unique")
                batch.drop_column("tool_call_ordinal")
            if "tool_batch_id" in columns:
                batch.drop_constraint("uq_agent_actions_tool_batch_call_id", type_="unique")
                batch.drop_index("ix_agent_actions_tool_batch_id")
                batch.drop_constraint("fk_agent_actions_tool_batch_id", type_="foreignkey")
                batch.drop_column("tool_batch_id")
    if _table_exists("agent_tool_call_batches"):
        op.drop_table("agent_tool_call_batches")
