"""add agent user custom instructions

Revision ID: 0052_agent_user_custom_instructions
Revises: 0051_agent_tool_batch_timestamp_defaults
Create Date: 2026-07-23
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op


revision = "0052_agent_user_custom_instructions"
down_revision = "0051_agent_tool_batch_timestamp_defaults"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_user_settings",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column(
            "custom_instructions",
            sa.Text(),
            nullable=False,
            server_default=sa.text("''"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"], ["workspaces.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "user_id",
            name="uq_agent_user_settings_workspace_user",
        ),
    )
    op.create_index(
        "ix_agent_user_settings_workspace_id",
        "agent_user_settings",
        ["workspace_id"],
    )
    op.create_index(
        "ix_agent_user_settings_user_id",
        "agent_user_settings",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_agent_user_settings_user_id", table_name="agent_user_settings")
    op.drop_index(
        "ix_agent_user_settings_workspace_id", table_name="agent_user_settings"
    )
    op.drop_table("agent_user_settings")
