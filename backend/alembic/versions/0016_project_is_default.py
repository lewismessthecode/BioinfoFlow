"""add is_default column to projects

Revision ID: 0016_project_is_default
Revises: 0015_provider_credentials_json
Create Date: 2026-04-07
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0016_project_is_default"
down_revision = "0015_provider_credentials_json"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("0")),
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_projects_one_default_per_user "
        "ON projects (user_id) WHERE is_default = 1"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_projects_one_default_per_user")
    op.drop_column("projects", "is_default")
