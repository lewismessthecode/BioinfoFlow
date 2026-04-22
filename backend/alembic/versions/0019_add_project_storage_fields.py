"""add project storage fields

Revision ID: 0019_add_project_storage_fields
Revises: 0018_merge_workspace_team_auth_and_image_pull_failures
Create Date: 2026-04-14
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0019_add_project_storage_fields"
down_revision = "0018_merge_workspace_team_auth_and_image_pull_failures"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column(
            "storage_mode",
            sa.String(length=20),
            nullable=False,
            server_default="managed",
        ),
    )
    op.add_column(
        "projects",
        sa.Column("storage_override_path", sa.String(length=500), nullable=True),
    )
    op.execute(
        "UPDATE projects SET storage_mode = 'managed' "
        "WHERE storage_mode IS NULL OR storage_mode = ''"
    )


def downgrade() -> None:
    op.drop_column("projects", "storage_override_path")
    op.drop_column("projects", "storage_mode")
