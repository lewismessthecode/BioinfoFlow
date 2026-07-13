"""add durable agent turn owner token

Revision ID: 0045_agent_turn_owner_token
Revises: 0044_llm_provider_wire_protocol
Create Date: 2026-07-13
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0045_agent_turn_owner_token"
down_revision = "0044_llm_provider_wire_protocol"
branch_labels = None
depends_on = None

_TABLE = "agent_turns"


def _table_exists() -> bool:
    return _TABLE in sa.inspect(op.get_bind()).get_table_names()


def _column_names() -> set[str]:
    return {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns(_TABLE)
    }


def upgrade() -> None:
    if not _table_exists():
        return
    columns = _column_names()
    with op.batch_alter_table(_TABLE) as batch:
        if "owner_token" not in columns:
            batch.add_column(sa.Column("owner_token", sa.String(length=36), nullable=True))
        if "resume_batch_token" not in columns:
            batch.add_column(
                sa.Column("resume_batch_token", sa.String(length=36), nullable=True)
            )


def downgrade() -> None:
    if not _table_exists():
        return
    columns = _column_names()
    with op.batch_alter_table(_TABLE) as batch:
        if "resume_batch_token" in columns:
            batch.drop_column("resume_batch_token")
        if "owner_token" in columns:
            batch.drop_column("owner_token")
