"""cascade scheduled tasks when deleting runs

Revision ID: 0027_scheduler_tasks_cascade
Revises: 0026_merge_conversation_and_form
Create Date: 2026-04-29
"""

from __future__ import annotations

from alembic import op


revision = "0027_scheduler_tasks_cascade"
down_revision = "0026_merge_conversation_and_form"
branch_labels = None
depends_on = None


_FK_NAME = "fk_scheduled_tasks_run_id_runs"
_NAMING_CONVENTION = {
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
}


def upgrade() -> None:
    with op.batch_alter_table(
        "scheduled_tasks",
        naming_convention=_NAMING_CONVENTION,
    ) as batch_op:
        batch_op.drop_constraint(_FK_NAME, type_="foreignkey")
        batch_op.create_foreign_key(
            _FK_NAME,
            "runs",
            ["run_id"],
            ["run_id"],
            ondelete="CASCADE",
        )


def downgrade() -> None:
    with op.batch_alter_table(
        "scheduled_tasks",
        naming_convention=_NAMING_CONVENTION,
    ) as batch_op:
        batch_op.drop_constraint(_FK_NAME, type_="foreignkey")
        batch_op.create_foreign_key(
            _FK_NAME,
            "runs",
            ["run_id"],
            ["run_id"],
        )
