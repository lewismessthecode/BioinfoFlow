"""agent approvals and policy mode

Revision ID: 0004_agent_approvals_and_policy_mode
Revises: 0003_project_workflow_bindings_and_pins
Create Date: 2026-02-04
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0004_agent_approvals_and_policy_mode"
down_revision = "0003_project_workflow_bindings_and_pins"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create agent_approvals table
    op.create_table(
        "agent_approvals",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("conversation_id", sa.String(36), nullable=False),
        sa.Column("step_id", sa.String(100), nullable=False),
        sa.Column("approval_type", sa.String(50), nullable=False, default="run"),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, default="pending"),
        sa.Column("resolved_by", sa.String(100), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
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
            ["conversation_id"], ["conversations.id"], ondelete="CASCADE"
        ),
    )
    op.create_index(
        "ix_agent_approvals_conversation_id",
        "agent_approvals",
        ["conversation_id"],
    )
    op.create_index(
        "ix_agent_approvals_status",
        "agent_approvals",
        ["status"],
    )

    # Add policy_mode column to conversations table
    op.add_column(
        "conversations",
        sa.Column(
            "policy_mode",
            sa.String(20),
            nullable=False,
            server_default="SAFE_AUTO",
        ),
    )


def downgrade() -> None:
    # Remove policy_mode column from conversations
    op.drop_column("conversations", "policy_mode")

    # Drop agent_approvals table
    op.drop_index("ix_agent_approvals_status", table_name="agent_approvals")
    op.drop_index("ix_agent_approvals_conversation_id", table_name="agent_approvals")
    op.drop_table("agent_approvals")
