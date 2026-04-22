"""scheduled tasks

Revision ID: 0005_scheduled_tasks
Revises: 0004_agent_approvals_and_policy_mode
Create Date: 2026-03-17
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0005_scheduled_tasks"
down_revision = "0005_workflow_launch_defaults"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scheduled_tasks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("run_id", sa.String(50), nullable=False),
        sa.Column("state", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("priority", sa.String(20), nullable=False, server_default="normal"),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("worker_id", sa.String(50), nullable=True),
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
        sa.ForeignKeyConstraint(["run_id"], ["runs.run_id"]),
    )
    op.create_index(
        "ix_scheduled_tasks_dequeue",
        "scheduled_tasks",
        ["state", "priority", "created_at"],
    )
    op.create_index("ix_scheduled_tasks_run_id", "scheduled_tasks", ["run_id"])
    op.create_index("ix_scheduled_tasks_state", "scheduled_tasks", ["state"])


def downgrade() -> None:
    op.drop_index("ix_scheduled_tasks_state", table_name="scheduled_tasks")
    op.drop_index("ix_scheduled_tasks_run_id", table_name="scheduled_tasks")
    op.drop_index("ix_scheduled_tasks_dequeue", table_name="scheduled_tasks")
    op.drop_table("scheduled_tasks")
