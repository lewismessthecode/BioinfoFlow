"""add workflows.form_spec column

Revision ID: 0023_workflow_form_spec
Revises: 0022_projects_workspace_id_fk
Create Date: 2026-04-20

The form_spec column holds a deterministic, frontend-renderable description
of the run submission form (one entry per user-facing input). It replaces
the role of submission_hint (which conflated UI policy with engine
normalization). submission_hint is left in place for now; it is removed
in Phase 3 of the run-layer rewrite.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0023_workflow_form_spec"
down_revision = "0022_projects_workspace_id_fk"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("workflows") as batch:
        batch.add_column(sa.Column("form_spec", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("workflows") as batch:
        batch.drop_column("form_spec")
