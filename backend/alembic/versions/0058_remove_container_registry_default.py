"""remove global container registry default

Revision ID: 0058_remove_container_registry_default
Revises: 0057_merge_agent_heads
Create Date: 2026-07-28
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0058_remove_container_registry_default"
down_revision = "0057_merge_agent_heads"
branch_labels = None
depends_on = None


TABLE_NAME = "container_registries"
DEFAULT_INDEX = "ix_container_registries_is_default"
DEFAULT_SINGLETON_INDEX = "uq_container_registries_default_singleton"


def _table_exists(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _existing_columns(table_name: str) -> set[str]:
    return {
        column["name"]
        for column in sa.inspect(op.get_bind()).get_columns(table_name)
    }


def _existing_indexes(table_name: str) -> set[str]:
    return {
        index["name"]
        for index in sa.inspect(op.get_bind()).get_indexes(table_name)
    }


def upgrade() -> None:
    if not _table_exists(TABLE_NAME):
        return

    indexes = _existing_indexes(TABLE_NAME)
    for index_name in (DEFAULT_SINGLETON_INDEX, DEFAULT_INDEX):
        if index_name in indexes:
            op.drop_index(index_name, table_name=TABLE_NAME)

    if "is_default" in _existing_columns(TABLE_NAME):
        with op.batch_alter_table(TABLE_NAME) as batch:
            batch.drop_column("is_default")


def downgrade() -> None:
    if not _table_exists(TABLE_NAME):
        return

    if "is_default" not in _existing_columns(TABLE_NAME):
        with op.batch_alter_table(TABLE_NAME) as batch:
            batch.add_column(
                sa.Column(
                    "is_default",
                    sa.Boolean(),
                    nullable=False,
                    server_default=sa.false(),
                )
            )

    indexes = _existing_indexes(TABLE_NAME)
    if DEFAULT_INDEX not in indexes:
        op.create_index(DEFAULT_INDEX, TABLE_NAME, ["is_default"])
    if DEFAULT_SINGLETON_INDEX not in indexes:
        op.create_index(
            DEFAULT_SINGLETON_INDEX,
            TABLE_NAME,
            ["is_default"],
            unique=True,
            sqlite_where=sa.text("is_default = true"),
            postgresql_where=sa.text("is_default = true"),
        )
