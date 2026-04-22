"""add user_id to projects and conversations

Revision ID: 0008_add_user_id_to_projects_and_conversations
Revises: 0007_batches_and_notifications
Create Date: 2026-03-31
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0008_add_user_id_to_projects_and_conversations"
down_revision = "0007_batches_and_notifications"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- projects ---
    with op.batch_alter_table("projects") as batch_op:
        batch_op.add_column(sa.Column("user_id", sa.String(length=36), nullable=True))

    op.execute("UPDATE projects SET user_id = 'system' WHERE user_id IS NULL")

    with op.batch_alter_table("projects") as batch_op:
        batch_op.alter_column("user_id", nullable=False)

    op.create_index("ix_projects_user_id", "projects", ["user_id"])

    # --- conversations ---
    with op.batch_alter_table("conversations") as batch_op:
        batch_op.add_column(sa.Column("user_id", sa.String(length=36), nullable=True))

    op.execute("UPDATE conversations SET user_id = 'system' WHERE user_id IS NULL")

    with op.batch_alter_table("conversations") as batch_op:
        batch_op.alter_column("user_id", nullable=False)

    op.create_index("ix_conversations_user_id", "conversations", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_conversations_user_id", table_name="conversations")
    with op.batch_alter_table("conversations") as batch_op:
        batch_op.drop_column("user_id")

    op.drop_index("ix_projects_user_id", table_name="projects")
    with op.batch_alter_table("projects") as batch_op:
        batch_op.drop_column("user_id")
