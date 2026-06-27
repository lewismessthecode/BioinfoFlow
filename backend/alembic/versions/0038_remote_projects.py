"""add remote project fields

Revision ID: 0038_remote_projects
Revises: 0037_remote_connections
Create Date: 2026-06-27
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0038_remote_projects"
down_revision = "0037_remote_connections"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("projects") as batch:
        batch.add_column(sa.Column("remote_connection_id", sa.String(length=36), nullable=True))
        batch.add_column(sa.Column("remote_root_path", sa.String(length=1000), nullable=True))
        batch.create_foreign_key(
            "fk_projects_remote_connection_id_remote_connections",
            "remote_connections",
            ["remote_connection_id"],
            ["id"],
            ondelete="SET NULL",
        )
    op.create_index(
        "ix_projects_remote_connection_id",
        "projects",
        ["remote_connection_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_projects_remote_connection_id", table_name="projects")
    with op.batch_alter_table("projects") as batch:
        batch.drop_constraint(
            "fk_projects_remote_connection_id_remote_connections",
            type_="foreignkey",
        )
        batch.drop_column("remote_root_path")
        batch.drop_column("remote_connection_id")
