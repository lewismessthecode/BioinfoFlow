"""add runs.error_json and runs.last_heartbeat_at columns

Revision ID: 0024_run_error_heartbeat
Revises: 0023_workflow_form_spec
Create Date: 2026-04-20

Adds structured error storage (``error_json``) and worker heartbeat
tracking (``last_heartbeat_at``) on the ``runs`` table. The existing
freeform ``error_message`` column is retained for back-compat — it's
populated from ``error_json["message"]`` when set, and remains the
display field in legacy surfaces until they migrate to RunError.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0024_run_error_heartbeat"
down_revision = "0023_workflow_form_spec"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("runs") as batch:
        batch.add_column(sa.Column("error_json", sa.JSON(), nullable=True))
        batch.add_column(
            sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("runs") as batch:
        batch.drop_column("last_heartbeat_at")
        batch.drop_column("error_json")
