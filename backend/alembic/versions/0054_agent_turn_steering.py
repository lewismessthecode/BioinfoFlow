"""add active turn steering state

Revision ID: 0054_agent_turn_steering
Revises: 0053_remote_connection_jump_host
Create Date: 2026-07-24
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op


revision = "0054_agent_turn_steering"
down_revision = "0053_remote_connection_jump_host"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agent_turns",
        sa.Column(
            "accepts_steer",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )


def downgrade() -> None:
    op.drop_column("agent_turns", "accepts_steer")
