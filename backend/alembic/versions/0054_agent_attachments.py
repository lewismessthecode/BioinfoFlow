"""add agent attachments

Revision ID: 0054_agent_attachments
Revises: 0053_remote_connection_jump_host
Create Date: 2026-07-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0054_agent_attachments"
down_revision = "0053_remote_connection_jump_host"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_attachments",
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("source", sa.String(length=30), nullable=False),
        sa.Column("filename", sa.String(length=500), nullable=False),
        sa.Column("storage_path", sa.String(length=1000), nullable=False),
        sa.Column("mime_type", sa.String(length=200), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("file_count", sa.Integer(), nullable=True),
        sa.Column("image_width", sa.Integer(), nullable=True),
        sa.Column("image_height", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["agent_sessions.id"],
            name="fk_agent_attachments_session_id_agent_sessions",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_agent_attachments_workspace_id_workspaces",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_agent_attachments"),
    )
    op.create_index(
        "ix_agent_attachments_session_id", "agent_attachments", ["session_id"]
    )
    op.create_index(
        "ix_agent_attachments_workspace_id", "agent_attachments", ["workspace_id"]
    )
    op.create_index(
        "ix_agent_attachments_user_id", "agent_attachments", ["user_id"]
    )
    op.create_index(
        "ix_agent_attachments_status", "agent_attachments", ["status"]
    )
    op.create_index(
        "ix_agent_attachments_created_at", "agent_attachments", ["created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_agent_attachments_created_at", table_name="agent_attachments")
    op.drop_index("ix_agent_attachments_status", table_name="agent_attachments")
    op.drop_index("ix_agent_attachments_user_id", table_name="agent_attachments")
    op.drop_index("ix_agent_attachments_workspace_id", table_name="agent_attachments")
    op.drop_index("ix_agent_attachments_session_id", table_name="agent_attachments")
    op.drop_table("agent_attachments")
