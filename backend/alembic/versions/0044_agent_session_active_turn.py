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
    op.add_column(
        "agent_sessions",
        sa.Column("active_turn_id", sa.String(length=36), nullable=True),
    )
    op.create_index(
        "ix_agent_sessions_active_turn_id",
        "agent_sessions",
        ["active_turn_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_agent_sessions_active_turn_id", table_name="agent_sessions")
    op.drop_column("agent_sessions", "active_turn_id")
