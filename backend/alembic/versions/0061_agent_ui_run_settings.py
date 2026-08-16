"""add agent UI run settings and composer defaults

Revision ID: 0061_agent_ui_run_settings
Revises: 0060_agent_harness_public_revisions
Create Date: 2026-08-16
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0061_agent_ui_run_settings"
down_revision = "0060_agent_harness_public_revisions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agent_sessions",
        sa.Column("execution_scope", sa.JSON(), nullable=True),
    )
    op.add_column(
        "agent_runs",
        sa.Column("settings_snapshot", sa.JSON(), nullable=True),
    )
    op.add_column(
        "agent_user_settings",
        sa.Column("composer_defaults", sa.JSON(), nullable=True),
    )

    bind = op.get_bind()
    sessions = sa.table(
        "agent_sessions",
        sa.column("id", sa.String(length=36)),
        sa.column("workspace_snapshot", sa.JSON()),
        sa.column("execution_scope", sa.JSON()),
    )
    rows = bind.execute(
        sa.select(sessions.c.id, sessions.c.workspace_snapshot)
    ).mappings()
    for row in rows:
        workspace = row["workspace_snapshot"]
        if not isinstance(workspace, dict):
            workspace = {}
        connection = workspace.get("remote_connection")
        connection_id = (
            str(connection.get("id") or "")
            if isinstance(connection, dict)
            else ""
        )
        scope = (
            {"mode": "manual", "target_ids": [connection_id]}
            if workspace.get("runtime") == "remote_ssh" and connection_id
            else {"mode": "auto", "target_ids": []}
        )
        bind.execute(
            sessions.update()
            .where(sessions.c.id == row["id"])
            .values(execution_scope=scope)
        )


def downgrade() -> None:
    op.drop_column("agent_user_settings", "composer_defaults")
    op.drop_column("agent_runs", "settings_snapshot")
    op.drop_column("agent_sessions", "execution_scope")
