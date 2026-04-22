"""add submission_hint to workflow

Revision ID: 0010_add_submission_hint_to_workflow
Revises: 0009_add_user_settings
Create Date: 2026-04-03
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0010_add_submission_hint_to_workflow"
down_revision = "0009_add_user_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("workflows", sa.Column("submission_hint", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("workflows", "submission_hint")
