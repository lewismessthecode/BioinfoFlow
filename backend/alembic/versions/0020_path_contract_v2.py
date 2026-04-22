"""path contract v2 full rewrite

Revision ID: 0020_path_contract_v2
Revises: 0019_add_project_storage_fields
Create Date: 2026-04-15
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0020_path_contract_v2"
down_revision = "0019_add_project_storage_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Before dropping ``workspace_path`` we classify existing rows into the
    # new managed/external scheme introduced in 0019. Rows whose path looks
    # like the default managed layout keep ``storage_mode='managed'`` and
    # discard the column; rows pointing somewhere bespoke are migrated to
    # ``storage_mode='external'`` with the old ``workspace_path`` preserved
    # in ``external_root_path`` so we don't lose the operator's location.
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    project_columns = {col["name"] for col in inspector.get_columns("projects")}
    if "workspace_path" in project_columns:
        rows = list(
            bind.execute(
                sa.text(
                    "SELECT id, storage_mode, storage_override_path, workspace_path "
                    "FROM projects"
                )
            ).mappings()
        )
        for row in rows:
            path = (row["workspace_path"] or "").strip()
            if not path or path in {".", "./"}:
                continue
            if row["storage_override_path"]:
                continue
            bind.execute(
                sa.text(
                    "UPDATE projects "
                    "SET storage_mode = 'external', storage_override_path = :path "
                    "WHERE id = :project_id"
                ),
                {"project_id": row["id"], "path": path},
            )

    with op.batch_alter_table("projects") as batch:
        batch.alter_column(
            "storage_override_path",
            new_column_name="external_root_path",
            existing_type=sa.String(length=500),
            existing_nullable=True,
        )
        batch.drop_column("workspace_path")

    with op.batch_alter_table("workflows") as batch:
        batch.add_column(sa.Column("source_ref", sa.String(length=500), nullable=True))
        batch.add_column(
            sa.Column("entrypoint_relpath", sa.String(length=500), nullable=True)
        )
        batch.add_column(sa.Column("bundle_kind", sa.String(length=50), nullable=True))

    bind = op.get_bind()
    rows = list(
        bind.execute(sa.text("SELECT id, source, source_url FROM workflows")).mappings()
    )
    for row in rows:
        source_url = str(row["source_url"] or "")
        source = str(row["source"] or "")
        entrypoint = source_url.replace("\\", "/").split("/")[-1] if source_url else None
        bind.execute(
            sa.text(
                "UPDATE workflows "
                "SET source_ref = :source_ref, bundle_kind = :bundle_kind, entrypoint_relpath = :entrypoint "
                "WHERE id = :workflow_id"
            ),
            {
                "workflow_id": row["id"],
                "source_ref": source_url or None,
                "bundle_kind": "local_bundle" if source == "local" else "remote_ref",
                "entrypoint": entrypoint if source == "local" else None,
            },
        )

    with op.batch_alter_table("workflows") as batch:
        batch.drop_column("source_url")

    with op.batch_alter_table("runs") as batch:
        batch.drop_column("workspace")


def downgrade() -> None:
    # Irreversible: the prior schema's ``workspace_path`` and
    # ``workflows.source_url`` values are not recoverable once this
    # migration has run. The original ``upgrade()`` classified each
    # project into managed/external and collapsed workflow metadata
    # into ``source_ref``/``bundle_kind``/``entrypoint_relpath`` —
    # inverting that would require per-row reconstruction from data
    # we no longer persist. Re-adding the columns with "." / empty
    # defaults (as the prior downgrade did) silently corrupts rows,
    # so we refuse instead. Restore from a pre-0020 backup.
    raise RuntimeError(
        "Migration 0020_path_contract_v2 is irreversible. "
        "Restore from a pre-0020 backup to roll back."
    )
