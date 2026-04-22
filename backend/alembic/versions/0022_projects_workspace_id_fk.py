"""enforce projects.workspace_id FK at the DB level

Revision ID: 0022_projects_workspace_id_fk
Revises: 0021_remove_data_roots
Create Date: 2026-04-17

The ORM has declared ``projects.workspace_id`` as a ``ForeignKey``
with ``ON DELETE CASCADE`` since 0017, but no previous migration
emitted the DDL for it. Referential integrity was therefore only
enforced in application code, letting a direct-DB delete or seed
leave orphaned projects pointing at a non-existent workspace.

This migration adds the real FK constraint and, defensively,
reassigns any already-orphaned rows to the default workspace so
the constraint can be added on existing databases.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0022_projects_workspace_id_fk"
down_revision = "0021_remove_data_roots"
branch_labels = None
depends_on = None


DEFAULT_WORKSPACE_ID = "00000000-0000-0000-0000-000000000001"


def upgrade() -> None:
    bind = op.get_bind()

    # Reassign orphaned rows before adding the constraint so the DDL
    # doesn't fail on existing databases with dangling workspace_ids.
    orphan_count = bind.execute(
        sa.text(
            "SELECT COUNT(*) FROM projects "
            "WHERE workspace_id NOT IN (SELECT id FROM workspaces)"
        )
    ).scalar_one()

    if orphan_count:
        default_exists = bind.execute(
            sa.text("SELECT 1 FROM workspaces WHERE id = :id"),
            {"id": DEFAULT_WORKSPACE_ID},
        ).scalar_one_or_none()
        if not default_exists:
            raise RuntimeError(
                f"Cannot add projects.workspace_id FK: {orphan_count} orphan "
                f"row(s) point at missing workspaces and the default workspace "
                f"{DEFAULT_WORKSPACE_ID} does not exist. Seed the default "
                "workspace or manually resolve orphans before re-running."
            )
        bind.execute(
            sa.text(
                "UPDATE projects SET workspace_id = :default_id "
                "WHERE workspace_id NOT IN (SELECT id FROM workspaces)"
            ),
            {"default_id": DEFAULT_WORKSPACE_ID},
        )

    with op.batch_alter_table("projects") as batch:
        batch.create_foreign_key(
            "fk_projects_workspace_id_workspaces",
            "workspaces",
            ["workspace_id"],
            ["id"],
            ondelete="CASCADE",
        )


def downgrade() -> None:
    with op.batch_alter_table("projects") as batch:
        batch.drop_constraint(
            "fk_projects_workspace_id_workspaces", type_="foreignkey"
        )
