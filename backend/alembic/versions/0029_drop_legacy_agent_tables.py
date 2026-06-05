"""drop legacy agent runtime tables

Revision ID: 0029_drop_legacy_agent_tables
Revises: 0028_agent_core_llm_contracts
Create Date: 2026-06-04
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op


revision = "0029_drop_legacy_agent_tables"
down_revision = "0028_agent_core_llm_contracts"
branch_labels = None
depends_on = None


LEGACY_AGENT_TABLES = (
    "agent_approval_handles",
    "agent_response_handles",
    "agent_approvals",
    "agent_traces",
    "messages",
    "conversations",
)


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing_tables = set(inspector.get_table_names())

    for table_name in LEGACY_AGENT_TABLES:
        if table_name in existing_tables:
            op.drop_table(table_name)


def downgrade() -> None:
    # Destructive AgentCore replacement: legacy conversations/messages/history
    # are intentionally not recreated or migrated back.
    return None
