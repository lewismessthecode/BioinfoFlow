"""add data_roots to projects

Revision ID: 0011_add_data_roots_to_projects
Revises: 0010_add_submission_hint_to_workflow
Create Date: 2026-04-03
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0011_add_data_roots_to_projects"
down_revision = "0010_add_submission_hint_to_workflow"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("data_roots", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("projects", "data_roots")
