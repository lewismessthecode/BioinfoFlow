"""add durable agent turn lease ownership

Revision ID: 0048_agent_turn_lease_ownership
Revises: 0047_agent_turn_tool_batch_sequence
Create Date: 2026-07-14
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0048_agent_turn_lease_ownership"
down_revision = "0047_agent_turn_tool_batch_sequence"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _existing_columns(table_name: str) -> set[str]:
    return {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns(table_name)
    }


def upgrade() -> None:
    if not _table_exists("agent_turns"):
        return
    if "lease_owner_token" in _existing_columns("agent_turns"):
        return
    with op.batch_alter_table("agent_turns") as batch:
        batch.add_column(sa.Column("lease_owner_token", sa.String(64), nullable=True))


def downgrade() -> None:
    if not _table_exists("agent_turns"):
        return
    if "lease_owner_token" not in _existing_columns("agent_turns"):
        return
    with op.batch_alter_table("agent_turns") as batch:
        batch.drop_column("lease_owner_token")
