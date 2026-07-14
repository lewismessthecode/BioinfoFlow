"""add versioned agent permission policy audit fields

Revision ID: 0046_agent_permission_policy
Revises: 0045_agent_turn_owner_token
Create Date: 2026-07-13
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0046_agent_permission_policy"
down_revision = "0045_agent_turn_owner_token"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _column_names(table_name: str) -> set[str]:
    return {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns(table_name)
    }


def upgrade() -> None:
    if _table_exists("agent_sessions"):
        columns = _column_names("agent_sessions")
        if "permission_policy_version" not in columns:
            with op.batch_alter_table("agent_sessions") as batch:
                batch.add_column(
                    sa.Column(
                        "permission_policy_version",
                        sa.Integer(),
                        nullable=False,
                        server_default="1",
                    )
                )

    if _table_exists("agent_actions"):
        columns = _column_names("agent_actions")
        with op.batch_alter_table("agent_actions") as batch:
            if "evaluated_policy_version" not in columns:
                batch.add_column(
                    sa.Column("evaluated_policy_version", sa.Integer(), nullable=True)
                )
            if "permission_context_snapshot" not in columns:
                batch.add_column(
                    sa.Column("permission_context_snapshot", sa.JSON(), nullable=True)
                )


def downgrade() -> None:
    if _table_exists("agent_actions"):
        columns = _column_names("agent_actions")
        with op.batch_alter_table("agent_actions") as batch:
            if "permission_context_snapshot" in columns:
                batch.drop_column("permission_context_snapshot")
            if "evaluated_policy_version" in columns:
                batch.drop_column("evaluated_policy_version")

    if _table_exists("agent_sessions"):
        columns = _column_names("agent_sessions")
        if "permission_policy_version" in columns:
            with op.batch_alter_table("agent_sessions") as batch:
                batch.drop_column("permission_policy_version")
