"""batches and notifications

Revision ID: 0007_batches_and_notifications
Revises: 0006_audit_logs_and_retry_delay
Create Date: 2026-03-17
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0007_batches_and_notifications"
down_revision = "0006_audit_logs_and_retry_delay"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "batches",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("batch_id", sa.String(length=50), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("total_runs", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completed_runs", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_runs", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("description", sa.Text(), nullable=True),
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
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("batch_id"),
    )
    op.create_index("ix_batches_batch_id", "batches", ["batch_id"])
    op.create_index("ix_batches_project_id", "batches", ["project_id"])

    op.create_table(
        "batch_runs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("batch_id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
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
        sa.ForeignKeyConstraint(["batch_id"], ["batches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("batch_id", "run_id", name="uq_batch_runs_batch_run"),
    )
    op.create_index("ix_batch_runs_batch_id", "batch_runs", ["batch_id"])
    op.create_index("ix_batch_runs_run_id", "batch_runs", ["run_id"])

    op.create_table(
        "notification_configs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("channel", sa.String(length=20), nullable=False),
        sa.Column("trigger", sa.String(length=50), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
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
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_notification_configs_project_id",
        "notification_configs",
        ["project_id"],
    )
    op.create_index(
        "ix_notification_configs_trigger",
        "notification_configs",
        ["trigger"],
    )


def downgrade() -> None:
    op.drop_index("ix_notification_configs_trigger", table_name="notification_configs")
    op.drop_index(
        "ix_notification_configs_project_id", table_name="notification_configs"
    )
    op.drop_table("notification_configs")

    op.drop_index("ix_batch_runs_run_id", table_name="batch_runs")
    op.drop_index("ix_batch_runs_batch_id", table_name="batch_runs")
    op.drop_table("batch_runs")

    op.drop_index("ix_batches_project_id", table_name="batches")
    op.drop_index("ix_batches_batch_id", table_name="batches")
    op.drop_table("batches")
