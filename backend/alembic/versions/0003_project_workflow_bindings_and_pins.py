"""project workflow bindings + pins

Revision ID: 0003_project_workflow_bindings_and_pins
Revises: 0002_agent_traces_and_conversation_fields
Create Date: 2026-02-02
"""

from __future__ import annotations

import uuid

from alembic import op
import sqlalchemy as sa


revision = "0003_project_workflow_bindings_and_pins"
down_revision = "0002_agent_traces_and_conversation_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "project_workflow_bindings",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("workflow_id", sa.String(36), nullable=False),
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
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workflow_id"], ["workflows.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "project_id",
            "workflow_id",
            name="uq_project_workflow_bindings_project_workflow",
        ),
    )
    op.create_index(
        "ix_project_workflow_bindings_project_id",
        "project_workflow_bindings",
        ["project_id"],
    )
    op.create_index(
        "ix_project_workflow_bindings_workflow_id",
        "project_workflow_bindings",
        ["workflow_id"],
    )

    op.create_table(
        "project_workflow_pins",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), nullable=False),
        sa.Column("workflow_source", sa.String(20), nullable=False),
        sa.Column("workflow_name", sa.String(200), nullable=False),
        sa.Column("pinned_workflow_id", sa.String(36), nullable=False),
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
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["pinned_workflow_id"], ["workflows.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint(
            "project_id",
            "workflow_source",
            "workflow_name",
            name="uq_project_workflow_pins_project_source_name",
        ),
    )
    op.create_index(
        "ix_project_workflow_pins_project_id",
        "project_workflow_pins",
        ["project_id"],
    )

    # Backfill bindings from historical runs so existing projects keep visibility.
    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            "SELECT DISTINCT project_id, workflow_id FROM runs WHERE workflow_id IS NOT NULL"
        )
    ).fetchall()

    if rows:
        bindings_table = sa.table(
            "project_workflow_bindings",
            sa.column("id", sa.String),
            sa.column("project_id", sa.String),
            sa.column("workflow_id", sa.String),
        )
        op.bulk_insert(
            bindings_table,
            [
                {
                    "id": str(uuid.uuid4()),
                    "project_id": str(project_id),
                    "workflow_id": str(workflow_id),
                }
                for (project_id, workflow_id) in rows
                if project_id and workflow_id
            ],
        )


def downgrade() -> None:
    op.drop_index(
        "ix_project_workflow_pins_project_id", table_name="project_workflow_pins"
    )
    op.drop_table("project_workflow_pins")
    op.drop_index(
        "ix_project_workflow_bindings_workflow_id",
        table_name="project_workflow_bindings",
    )
    op.drop_index(
        "ix_project_workflow_bindings_project_id",
        table_name="project_workflow_bindings",
    )
    op.drop_table("project_workflow_bindings")
