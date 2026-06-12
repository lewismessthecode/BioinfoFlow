"""add agent turn execution lease fields

Revision ID: 0035_agent_turn_execution_leases
Revises: 0034_drop_legacy_user_settings
Create Date: 2026-06-11
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0035_agent_turn_execution_leases"
down_revision = "0034_drop_legacy_user_settings"
branch_labels = None
depends_on = None


def _existing_columns(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return {column["name"] for column in inspector.get_columns(table_name)}


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    if not _table_exists("agent_turns"):
        return
    columns = _existing_columns("agent_turns")
    with op.batch_alter_table("agent_turns") as batch:
        if "claimed_at" not in columns:
            batch.add_column(sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True))
        if "lease_until" not in columns:
            batch.add_column(sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    if not _table_exists("agent_turns"):
        return
    columns = _existing_columns("agent_turns")
    with op.batch_alter_table("agent_turns") as batch:
        if "lease_until" in columns:
            batch.drop_column("lease_until")
        if "claimed_at" in columns:
            batch.drop_column("claimed_at")
