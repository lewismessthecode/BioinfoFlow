"""add container registries

Revision ID: 0039_container_registries
Revises: 0038_remote_projects
Create Date: 2026-06-29
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0039_container_registries"
down_revision = "0038_remote_projects"
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
    if not _table_exists("container_registries"):
        op.create_table(
            "container_registries",
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("endpoint", sa.String(length=500), nullable=False),
            sa.Column("namespace", sa.String(length=255), nullable=True),
            sa.Column("insecure", sa.Boolean(), nullable=False),
            sa.Column("is_default", sa.Boolean(), nullable=False),
            sa.Column("credential_source", sa.String(length=20), nullable=False),
            sa.Column("env_username_var", sa.String(length=120), nullable=True),
            sa.Column("env_password_var", sa.String(length=120), nullable=True),
            sa.Column("encrypted_username", sa.Text(), nullable=True),
            sa.Column("encrypted_password", sa.Text(), nullable=True),
            sa.Column("credential_fingerprint", sa.String(length=64), nullable=True),
            sa.Column("username_hint", sa.String(length=120), nullable=True),
            sa.Column("password_hint", sa.String(length=120), nullable=True),
            sa.Column("last_status", sa.String(length=20), nullable=False),
            sa.Column("last_error", sa.Text(), nullable=True),
            sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_by", sa.String(length=36), nullable=True),
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
                "credential_source IN ('none', 'env', 'stored')",
                name="ck_container_registries_credential_source",
            ),
            sa.CheckConstraint(
                "last_status IN ('untested', 'ok', 'error')",
                name="ck_container_registries_last_status",
            ),
            sa.PrimaryKeyConstraint("id", name="pk_container_registries"),
        )
    if "ix_container_registries_is_default" not in _existing_indexes(
        "container_registries"
    ):
        op.create_index(
            "ix_container_registries_is_default",
            "container_registries",
            ["is_default"],
        )

    if not _table_exists("projects"):
        return
    columns = _existing_columns("projects")
    foreign_keys = _existing_foreign_keys("projects")
    with op.batch_alter_table("projects") as batch:
        if "container_registry_id" not in columns:
            batch.add_column(
                sa.Column(
                    "container_registry_id",
                    sa.String(length=36),
                    nullable=True,
                )
            )
        if "fk_projects_container_registry_id_container_registries" not in foreign_keys:
            batch.create_foreign_key(
                "fk_projects_container_registry_id_container_registries",
                "container_registries",
                ["container_registry_id"],
                ["id"],
                ondelete="SET NULL",
            )
    if "ix_projects_container_registry_id" not in _existing_indexes("projects"):
        op.create_index(
            "ix_projects_container_registry_id",
            "projects",
            ["container_registry_id"],
        )

    if not _table_exists("workflows"):
        return
    columns = _existing_columns("workflows")
    foreign_keys = _existing_foreign_keys("workflows")
    with op.batch_alter_table("workflows") as batch:
        if "container_registry_id" not in columns:
            batch.add_column(
                sa.Column(
                    "container_registry_id",
                    sa.String(length=36),
                    nullable=True,
                )
            )
        if "fk_workflows_container_registry_id_container_registries" not in foreign_keys:
            batch.create_foreign_key(
                "fk_workflows_container_registry_id_container_registries",
                "container_registries",
                ["container_registry_id"],
                ["id"],
                ondelete="SET NULL",
            )
    if "ix_workflows_container_registry_id" not in _existing_indexes("workflows"):
        op.create_index(
            "ix_workflows_container_registry_id",
            "workflows",
            ["container_registry_id"],
        )


def downgrade() -> None:
    if _table_exists("workflows"):
        columns = _existing_columns("workflows")
        foreign_keys = _existing_foreign_keys("workflows")
        if "ix_workflows_container_registry_id" in _existing_indexes("workflows"):
            op.drop_index("ix_workflows_container_registry_id", table_name="workflows")
        with op.batch_alter_table("workflows") as batch:
            if "fk_workflows_container_registry_id_container_registries" in foreign_keys:
                batch.drop_constraint(
                    "fk_workflows_container_registry_id_container_registries",
                    type_="foreignkey",
                )
            if "container_registry_id" in columns:
                batch.drop_column("container_registry_id")
    if _table_exists("projects"):
        columns = _existing_columns("projects")
        foreign_keys = _existing_foreign_keys("projects")
        if "ix_projects_container_registry_id" in _existing_indexes("projects"):
            op.drop_index("ix_projects_container_registry_id", table_name="projects")
        with op.batch_alter_table("projects") as batch:
            if "fk_projects_container_registry_id_container_registries" in foreign_keys:
                batch.drop_constraint(
                    "fk_projects_container_registry_id_container_registries",
                    type_="foreignkey",
                )
            if "container_registry_id" in columns:
                batch.drop_column("container_registry_id")
    if _table_exists("container_registries"):
        if "ix_container_registries_is_default" in _existing_indexes(
            "container_registries"
        ):
            op.drop_index(
                "ix_container_registries_is_default",
                table_name="container_registries",
            )
        op.drop_table("container_registries")
