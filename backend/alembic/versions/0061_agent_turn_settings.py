"""add mutable conversation settings and immutable run configuration

Revision ID: 0061_agent_turn_settings
Revises: 0060_agent_harness_public_revisions
Create Date: 2026-08-16
"""

from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op


revision = "0061_agent_turn_settings"
down_revision = "0060_agent_harness_public_revisions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("agent_sessions") as batch:
        batch.add_column(
            sa.Column(
                "settings_revision",
                sa.Integer(),
                nullable=False,
                server_default="1",
            )
        )
        batch.add_column(
            sa.Column(
                "environment_scope",
                sa.JSON(),
                nullable=False,
                server_default=json.dumps({"mode": "auto"}),
            )
        )
    with op.batch_alter_table("agent_runs") as batch:
        batch.add_column(sa.Column("turn_execution_config", sa.JSON(), nullable=True))

    connection = op.get_bind()
    sessions = sa.table(
        "agent_sessions",
        sa.column("id", sa.String()),
        sa.column("workspace_id", sa.String()),
        sa.column("model_snapshot", sa.JSON()),
        sa.column("permission_mode", sa.String()),
        sa.column("workspace_access", sa.String()),
        sa.column("settings_revision", sa.Integer()),
        sa.column("environment_scope", sa.JSON()),
    )
    runs = sa.table(
        "agent_runs",
        sa.column("session_id", sa.String()),
        sa.column("model_snapshot", sa.JSON()),
        sa.column("turn_execution_config", sa.JSON()),
    )
    remote_connections = sa.table(
        "remote_connections",
        sa.column("id", sa.String()),
        sa.column("workspace_id", sa.String()),
    )
    environment_ids_by_workspace: dict[str, list[str]] = {}
    remote_rows = connection.execute(
        sa.select(remote_connections.c.id, remote_connections.c.workspace_id).order_by(
            remote_connections.c.workspace_id,
            remote_connections.c.id,
        )
    ).all()
    for remote_row in remote_rows:
        environment_ids_by_workspace.setdefault(
            str(remote_row.workspace_id), ["local"]
        ).append(str(remote_row.id))
    session_rows = {
        str(row.id): row for row in connection.execute(sa.select(sessions)).all()
    }
    for session_id, row in session_rows.items():
        scope = row.environment_scope or {"mode": "auto"}
        if scope.get("mode") == "auto":
            scope = {
                "mode": "auto",
                "environment_ids": environment_ids_by_workspace.get(
                    str(row.workspace_id), ["local"]
                ),
            }
        connection.execute(
            sa.update(runs)
            .where(runs.c.session_id == session_id)
            .values(
                turn_execution_config={
                    "settings_revision": int(row.settings_revision or 1),
                    "model": row.model_snapshot,
                    "permission_mode": row.permission_mode,
                    "workspace_access": row.workspace_access,
                    "environment_scope": scope,
                }
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("agent_runs") as batch:
        batch.drop_column("turn_execution_config")
    with op.batch_alter_table("agent_sessions") as batch:
        batch.drop_column("environment_scope")
        batch.drop_column("settings_revision")
