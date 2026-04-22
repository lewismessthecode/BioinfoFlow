"""add image pull failure metadata

Revision ID: 0017_image_pull_failures
Revises: 0016_project_is_default
Create Date: 2026-04-08
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0017_image_pull_failures"
down_revision = "0016_project_is_default"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("docker_images") as batch_op:
        batch_op.add_column(sa.Column("error_message", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("docker_images") as batch_op:
        batch_op.drop_column("error_message")
