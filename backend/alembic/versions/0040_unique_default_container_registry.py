"""enforce single default container registry

Revision ID: 0040_unique_default_container_registry
Revises: 0039_container_registries
Create Date: 2026-06-29
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0040_unique_default_container_registry"
down_revision = "0039_container_registries"
branch_labels = None
depends_on = None


INDEX_NAME = "uq_container_registries_default_singleton"


def _table_exists(table_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return table_name in inspector.get_table_names()


def _existing_indexes(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {index["name"] for index in inspector.get_indexes(table_name)}


def upgrade() -> None:
    if not _table_exists("container_registries"):
        return

    op.execute(
        """
        UPDATE container_registries
        SET is_default = false
        WHERE is_default = true
          AND id NOT IN (
            SELECT id
            FROM container_registries
            WHERE is_default = true
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
          )
        """
    )
    if INDEX_NAME not in _existing_indexes("container_registries"):
        op.create_index(
            INDEX_NAME,
            "container_registries",
            ["is_default"],
            unique=True,
            sqlite_where=sa.text("is_default = true"),
            postgresql_where=sa.text("is_default = true"),
        )


def downgrade() -> None:
    if not _table_exists("container_registries"):
        return
    if INDEX_NAME in _existing_indexes("container_registries"):
        op.drop_index(INDEX_NAME, table_name="container_registries")
