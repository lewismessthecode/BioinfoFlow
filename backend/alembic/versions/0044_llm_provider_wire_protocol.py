"""add explicit wire protocol for LLM providers

Revision ID: 0044_llm_provider_wire_protocol
Revises: 0043_llm_provider_insecure_http_opt_in
Create Date: 2026-07-13
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0044_llm_provider_wire_protocol"
down_revision = "0043_llm_provider_insecure_http_opt_in"
branch_labels = None
depends_on = None

_TABLE = "llm_providers"
_CONSTRAINT = "ck_llm_providers_wire_protocol"


def _table_exists(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _column_names(table_name: str) -> set[str]:
    return {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns(table_name)
    }


def upgrade() -> None:
    if not _table_exists(_TABLE) or "wire_protocol" in _column_names(_TABLE):
        return
    with op.batch_alter_table(_TABLE) as batch:
        batch.add_column(
            sa.Column(
                "wire_protocol",
                sa.String(length=32),
                nullable=False,
                server_default="chat_completions",
            )
        )
        batch.create_check_constraint(
            _CONSTRAINT,
            "wire_protocol IN ('chat_completions', 'responses')",
        )


def downgrade() -> None:
    if not _table_exists(_TABLE) or "wire_protocol" not in _column_names(_TABLE):
        return
    with op.batch_alter_table(_TABLE) as batch:
        batch.drop_constraint(_CONSTRAINT, type_="check")
        batch.drop_column("wire_protocol")
