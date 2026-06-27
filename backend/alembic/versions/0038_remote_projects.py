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


def _table_exists(table_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return table_name in inspector.get_table_names()


def _existing_columns(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {column["name"] for column in inspector.get_columns(table_name)}


def _existing_indexes(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {index["name"] for index in inspector.get_indexes(table_name)}


def _existing_foreign_keys(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {key["name"] for key in inspector.get_foreign_keys(table_name)}


def upgrade() -> None:
    if not _table_exists("projects"):
        return
    columns = _existing_columns("projects")
    foreign_keys = _existing_foreign_keys("projects")
    with op.batch_alter_table("projects") as batch:
        if "remote_connection_id" not in columns:
            batch.add_column(sa.Column("remote_connection_id", sa.String(length=36), nullable=True))
        if "remote_root_path" not in columns:
            batch.add_column(sa.Column("remote_root_path", sa.String(length=1000), nullable=True))
        if (
            "fk_projects_remote_connection_id_remote_connections" not in foreign_keys
            and _table_exists("remote_connections")
        ):
            batch.create_foreign_key(
                "fk_projects_remote_connection_id_remote_connections",
                "remote_connections",
                ["remote_connection_id"],
                ["id"],
                ondelete="RESTRICT",
            )
    if "ix_projects_remote_connection_id" not in _existing_indexes("projects"):
        op.create_index(
            "ix_projects_remote_connection_id",
            "projects",
            ["remote_connection_id"],
        )


def downgrade() -> None:
    if not _table_exists("projects"):
        return
    columns = _existing_columns("projects")
    foreign_keys = _existing_foreign_keys("projects")
    if "ix_projects_remote_connection_id" in _existing_indexes("projects"):
        op.drop_index("ix_projects_remote_connection_id", table_name="projects")
    with op.batch_alter_table("projects") as batch:
        if "fk_projects_remote_connection_id_remote_connections" in foreign_keys:
            batch.drop_constraint(
                "fk_projects_remote_connection_id_remote_connections",
                type_="foreignkey",
            )
        if "remote_root_path" in columns:
            batch.drop_column("remote_root_path")
        if "remote_connection_id" in columns:
            batch.drop_column("remote_connection_id")
