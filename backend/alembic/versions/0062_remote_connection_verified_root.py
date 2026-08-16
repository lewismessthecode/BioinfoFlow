"""store verified remote Agent roots

Revision ID: 0062_remote_connection_verified_root
Revises: 0061_agent_ui_run_settings
Create Date: 2026-08-16
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0062_remote_connection_verified_root"
down_revision = "0061_agent_ui_run_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "remote_connections",
        sa.Column("verified_root_path", sa.String(length=1000), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("remote_connections", "verified_root_path")
