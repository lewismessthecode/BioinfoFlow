"""add durable raw model traces

Revision ID: 0062_agent_model_traces
Revises: 0061_agent_turn_settings
Create Date: 2026-08-17
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.database import GUID


revision = "0062_agent_model_traces"
down_revision = "0061_agent_turn_settings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_model_traces",
        sa.Column("session_id", GUID(), nullable=False),
        sa.Column("run_id", GUID(), nullable=True),
        sa.Column("iteration", sa.Integer(), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("context_through_sequence", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=100), nullable=False),
        sa.Column("model", sa.String(length=500), nullable=False),
        sa.Column("wire_protocol", sa.String(length=40), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("context_snapshot", sa.JSON(), nullable=False),
        sa.Column("request_payload", sa.JSON(), nullable=True),
        sa.Column("response_payload", sa.JSON(), nullable=True),
        sa.Column("usage", sa.JSON(), nullable=True),
        sa.Column("provider_response_id", sa.String(length=500), nullable=True),
        sa.Column("finish_reason", sa.String(length=100), nullable=True),
        sa.Column("error", sa.JSON(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("request_prepared_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_byte_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", GUID(), nullable=False),
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
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["session_id"], ["agent_sessions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_agent_model_traces_run_id",
        "agent_model_traces",
        ["run_id"],
    )
    op.create_index(
        "ix_agent_model_traces_session_id",
        "agent_model_traces",
        ["session_id"],
    )
    op.create_index(
        "ix_agent_model_traces_status",
        "agent_model_traces",
        ["status"],
    )
    op.create_index(
        "ix_agent_model_traces_session_started",
        "agent_model_traces",
        ["session_id", "started_at", "id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_agent_model_traces_session_started",
        table_name="agent_model_traces",
    )
    op.drop_index("ix_agent_model_traces_status", table_name="agent_model_traces")
    op.drop_index("ix_agent_model_traces_session_id", table_name="agent_model_traces")
    op.drop_index("ix_agent_model_traces_run_id", table_name="agent_model_traces")
    op.drop_table("agent_model_traces")
