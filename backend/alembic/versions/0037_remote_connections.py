"""add remote SSH connections

Revision ID: 0037_remote_connections
Revises: 0036_remove_builtin_ollama_catalog
Create Date: 2026-06-25
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0037_remote_connections"
down_revision = "0036_remove_builtin_ollama_catalog"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "remote_connections",
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("host", sa.String(length=255), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(length=120), nullable=False),
        sa.Column("auth_method", sa.String(length=20), nullable=False),
        sa.Column("ssh_alias", sa.String(length=255), nullable=True),
        sa.Column("key_path", sa.String(length=500), nullable=True),
        sa.Column("skill_instructions", sa.Text(), nullable=True),
        sa.Column("last_status", sa.String(length=20), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "port >= 1 AND port <= 65535",
            name="ck_remote_connections_port_range",
        ),
        sa.CheckConstraint(
            "auth_method IN ('ssh_config', 'key_file', 'agent')",
            name="ck_remote_connections_auth_method",
        ),
        sa.CheckConstraint(
            "last_status IN ('unknown', 'online', 'offline', 'error')",
            name="ck_remote_connections_last_status",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_remote_connections_workspace_id_workspaces",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_remote_connections"),
        sa.UniqueConstraint(
            "workspace_id",
            "name",
            name="uq_remote_connections_workspace_name",
        ),
    )
    op.create_index(
        "ix_remote_connections_last_status",
        "remote_connections",
        ["last_status"],
    )
    op.create_index(
        "ix_remote_connections_workspace_id",
        "remote_connections",
        ["workspace_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_remote_connections_workspace_id",
        table_name="remote_connections",
    )
    op.drop_index(
        "ix_remote_connections_last_status",
        table_name="remote_connections",
    )
    op.drop_table("remote_connections")
