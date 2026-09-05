"""give published artifacts stable identities and immutable versions

Revision ID: 0065_versioned_agent_artifacts
Revises: 0064_agent_tool_outputs
"""

from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op


revision = "0065_versioned_agent_artifacts"
down_revision = "0064_agent_tool_outputs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("agent_artifacts") as batch:
        batch.add_column(sa.Column("artifact_id", sa.String(length=36), nullable=True))
        batch.add_column(sa.Column("version", sa.Integer(), nullable=True))
        batch.add_column(
            sa.Column("declaration_id", sa.String(length=200), nullable=True)
        )

    bind = op.get_bind()
    table = sa.table(
        "agent_artifacts",
        sa.column("id", sa.String()),
        sa.column("artifact_id", sa.String()),
        sa.column("version", sa.Integer()),
        sa.column("declaration_id", sa.String()),
        sa.column("payload", sa.JSON()),
    )
    rows = bind.execute(sa.select(table)).mappings().all()
    for row in rows:
        payload = row.get("payload")
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except (TypeError, ValueError):
                payload = None
        declaration_id = (
            payload.get("declaration_id") if isinstance(payload, dict) else None
        )
        bind.execute(
            table.update()
            .where(table.c.id == row["id"])
            .values(
                artifact_id=row["id"],
                version=1,
                declaration_id=declaration_id,
            )
        )
    op.create_index(
        "ix_agent_artifacts_artifact_id", "agent_artifacts", ["artifact_id"]
    )
    op.create_index(
        "ix_agent_artifacts_declaration_id", "agent_artifacts", ["declaration_id"]
    )
    op.create_index(
        "uq_agent_artifacts_identity_version",
        "agent_artifacts",
        ["artifact_id", "version"],
        unique=True,
    )


def downgrade() -> None:
    bind = op.get_bind()
    artifacts = sa.table(
        "agent_artifacts",
        sa.column("artifact_id", sa.String()),
        sa.column("version", sa.Integer()),
    )
    has_new_versions = bind.execute(
        sa.select(sa.literal(1))
        .select_from(artifacts)
        .where(artifacts.c.version > 1)
        .limit(1)
    ).first()
    if has_new_versions is not None:
        raise RuntimeError(
            "Cannot downgrade 0065 after Artifact versions were created; "
            "restore the pre-upgrade state snapshot instead."
        )
    op.drop_index("uq_agent_artifacts_identity_version", table_name="agent_artifacts")
    op.drop_index("ix_agent_artifacts_declaration_id", table_name="agent_artifacts")
    op.drop_index("ix_agent_artifacts_artifact_id", table_name="agent_artifacts")
    with op.batch_alter_table("agent_artifacts") as batch:
        batch.drop_column("declaration_id")
        batch.drop_column("version")
        batch.drop_column("artifact_id")
