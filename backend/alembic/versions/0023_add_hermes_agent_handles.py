"""add Hermes-backed agent handle metadata

Revision ID: 0023_add_hermes_agent_handles
Revises: 0022_projects_workspace_id_fk
Create Date: 2026-04-14
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0023_add_hermes_agent_handles"
down_revision = "0022_projects_workspace_id_fk"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column(
            "storage_backend",
            sa.String(length=20),
            nullable=False,
            server_default="legacy",
        ),
    )
    op.add_column(
        "conversations",
        sa.Column("hermes_session_id", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "conversations",
        sa.Column("workspace_binding_id", sa.String(length=36), nullable=True),
    )
    op.create_index(
        "ix_conversations_storage_backend",
        "conversations",
        ["storage_backend"],
    )
    op.create_index(
        "ix_conversations_hermes_session_id",
        "conversations",
        ["hermes_session_id"],
        unique=True,
    )
    op.create_index(
        "ix_conversations_workspace_binding_id",
        "conversations",
        ["workspace_binding_id"],
    )

    op.create_table(
        "agent_response_handles",
        sa.Column("conversation_id", sa.String(length=36), nullable=False),
        sa.Column("runtime_instance_id", sa.String(length=100), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("last_event_seq", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_message", sa.String(length=500), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
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
            ["conversation_id"],
            ["conversations.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_agent_response_handles"),
    )
    op.create_index(
        "ix_agent_response_handles_conversation_id",
        "agent_response_handles",
        ["conversation_id"],
    )
    op.create_index(
        "ix_agent_response_handles_status",
        "agent_response_handles",
        ["status"],
    )

    op.create_table(
        "agent_approval_handles",
        sa.Column("conversation_id", sa.String(length=36), nullable=False),
        sa.Column("response_id", sa.String(length=36), nullable=False),
        sa.Column("call_id", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("resolved_by", sa.String(length=100), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
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
            ["conversation_id"],
            ["conversations.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["response_id"],
            ["agent_response_handles.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_agent_approval_handles"),
    )
    op.create_index(
        "ix_agent_approval_handles_conversation_id",
        "agent_approval_handles",
        ["conversation_id"],
    )
    op.create_index(
        "ix_agent_approval_handles_response_id",
        "agent_approval_handles",
        ["response_id"],
    )
    op.create_index(
        "ix_agent_approval_handles_call_id",
        "agent_approval_handles",
        ["call_id"],
    )
    op.create_index(
        "ix_agent_approval_handles_status",
        "agent_approval_handles",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index("ix_agent_approval_handles_status", table_name="agent_approval_handles")
    op.drop_index("ix_agent_approval_handles_call_id", table_name="agent_approval_handles")
    op.drop_index("ix_agent_approval_handles_response_id", table_name="agent_approval_handles")
    op.drop_index("ix_agent_approval_handles_conversation_id", table_name="agent_approval_handles")
    op.drop_table("agent_approval_handles")

    op.drop_index("ix_agent_response_handles_status", table_name="agent_response_handles")
    op.drop_index("ix_agent_response_handles_conversation_id", table_name="agent_response_handles")
    op.drop_table("agent_response_handles")

    op.drop_index("ix_conversations_workspace_binding_id", table_name="conversations")
    op.drop_index("ix_conversations_hermes_session_id", table_name="conversations")
    op.drop_index("ix_conversations_storage_backend", table_name="conversations")
    op.drop_column("conversations", "workspace_binding_id")
    op.drop_column("conversations", "hermes_session_id")
    op.drop_column("conversations", "storage_backend")
