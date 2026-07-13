"""serialize active turns per agent session

Revision ID: 0044_agent_session_active_turn
Revises: 0043_llm_provider_insecure_http_opt_in
Create Date: 2026-07-13
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op


revision = "0044_agent_session_active_turn"
down_revision = "0043_llm_provider_insecure_http_opt_in"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("agent_sessions"):
        return
    columns = {column["name"] for column in inspector.get_columns("agent_sessions")}
    if "active_turn_id" not in columns:
        op.add_column(
            "agent_sessions",
            sa.Column("active_turn_id", sa.String(length=36), nullable=True),
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("agent_sessions"):
        return
    columns = {column["name"] for column in inspector.get_columns("agent_sessions")}
    if "active_turn_id" in columns:
        op.drop_column("agent_sessions", "active_turn_id")
