"""persist readable project directory names

Revision ID: 0056_readable_project_directories
Revises: 0055_merge_agent_heads
Create Date: 2026-07-27
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0056_readable_project_directories"
down_revision = "0055_merge_agent_heads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if not sa.inspect(op.get_bind()).has_table("projects"):
        return

    op.add_column(
        "projects",
        sa.Column("directory_name", sa.String(length=120), nullable=True),
    )
    op.create_index(
        "uq_projects_directory_name",
        "projects",
        ["directory_name"],
        unique=True,
    )


def downgrade() -> None:
    if not sa.inspect(op.get_bind()).has_table("projects"):
        return

    op.drop_index("uq_projects_directory_name", table_name="projects")
    op.drop_column("projects", "directory_name")
