"""add explicit insecure HTTP opt-in for LLM providers

Revision ID: 0043_llm_provider_insecure_http_opt_in
Revises: 0042_remote_connection_stored_credentials
Create Date: 2026-07-12
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0043_llm_provider_insecure_http_opt_in"
down_revision = "0042_remote_connection_stored_credentials"
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
    if not _table_exists("llm_providers"):
        return
    if "allow_insecure_http" in _column_names("llm_providers"):
        return

    with op.batch_alter_table("llm_providers") as batch:
        batch.add_column(
            sa.Column(
                "allow_insecure_http",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            )
        )


def downgrade() -> None:
    if not _table_exists("llm_providers"):
        return
    if "allow_insecure_http" not in _column_names("llm_providers"):
        return

    with op.batch_alter_table("llm_providers") as batch:
        batch.drop_column("allow_insecure_http")
