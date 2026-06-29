"""add run module lifecycle invariants

Revision ID: 0041_run_module_invariants
Revises: 0040_unique_default_container_registry
Create Date: 2026-06-29
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0041_run_module_invariants"
down_revision = "0040_unique_default_container_registry"
branch_labels = None
depends_on = None


RUN_STATUS_SQL = (
    "('pending', 'queued', 'preparing', 'running', 'completed', 'failed', 'cancelled')"
)
TASK_ACTIVE_STATE_SQL = "('queued', 'dispatched')"

RUN_REPLAY_INDEX = "uq_runs_replay_intent"
TASK_ACTIVE_RUN_INDEX = "uq_scheduled_tasks_active_run"


def _table_exists(table_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return table_name in inspector.get_table_names()


def _columns(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {column["name"] for column in inspector.get_columns(table_name)}


def _indexes(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {index["name"] for index in inspector.get_indexes(table_name)}


def upgrade() -> None:
    if _table_exists("runs"):
        _normalize_run_statuses()
        existing_columns = _columns("runs")
        with op.batch_alter_table("runs") as batch:
            if "source_run_id" not in existing_columns:
                batch.add_column(sa.Column("source_run_id", sa.String(50)))
            if "replay_kind" not in existing_columns:
                batch.add_column(sa.Column("replay_kind", sa.String(20)))
            if "replay_idempotency_key" not in existing_columns:
                batch.add_column(sa.Column("replay_idempotency_key", sa.String(128)))
            if "attempt_number" not in existing_columns:
                batch.add_column(
                    sa.Column(
                        "attempt_number",
                        sa.Integer(),
                        nullable=False,
                        server_default="1",
                    )
                )
            batch.create_check_constraint(
                "ck_runs_status_valid",
                f"status IN {RUN_STATUS_SQL}",
            )
            batch.create_check_constraint(
                "ck_runs_replay_kind_valid",
                "replay_kind IS NULL OR replay_kind IN ('retry', 'resume')",
            )
            batch.create_check_constraint(
                "ck_runs_attempt_number_positive",
                "attempt_number >= 1",
            )
            batch.create_check_constraint(
                "ck_runs_replay_lineage_complete",
                "("
                "source_run_id IS NULL "
                "AND replay_kind IS NULL "
                "AND replay_idempotency_key IS NULL "
                "AND attempt_number = 1"
                ") OR ("
                "source_run_id IS NOT NULL "
                "AND replay_kind IS NOT NULL "
                "AND replay_idempotency_key IS NOT NULL "
                "AND attempt_number > 1"
                ")",
            )
            batch.create_check_constraint(
                "ck_runs_source_not_self",
                "source_run_id IS NULL OR source_run_id != run_id",
            )
            batch.create_foreign_key(
                "fk_runs_source_run_id_runs",
                "runs",
                ["source_run_id"],
                ["run_id"],
            )
        if RUN_REPLAY_INDEX not in _indexes("runs"):
            op.create_index(
                RUN_REPLAY_INDEX,
                "runs",
                ["source_run_id", "replay_kind", "replay_idempotency_key"],
                unique=True,
                sqlite_where=sa.text(
                    "source_run_id IS NOT NULL "
                    "AND replay_kind IS NOT NULL "
                    "AND replay_idempotency_key IS NOT NULL"
                ),
                postgresql_where=sa.text(
                    "source_run_id IS NOT NULL "
                    "AND replay_kind IS NOT NULL "
                    "AND replay_idempotency_key IS NOT NULL"
                ),
            )

    if _table_exists("scheduled_tasks"):
        _terminalize_duplicate_active_tasks()
        if TASK_ACTIVE_RUN_INDEX not in _indexes("scheduled_tasks"):
            op.create_index(
                TASK_ACTIVE_RUN_INDEX,
                "scheduled_tasks",
                ["run_id"],
                unique=True,
                sqlite_where=sa.text(f"state IN {TASK_ACTIVE_STATE_SQL}"),
                postgresql_where=sa.text(f"state IN {TASK_ACTIVE_STATE_SQL}"),
            )


def downgrade() -> None:
    if _table_exists("scheduled_tasks") and TASK_ACTIVE_RUN_INDEX in _indexes(
        "scheduled_tasks"
    ):
        op.drop_index(TASK_ACTIVE_RUN_INDEX, table_name="scheduled_tasks")

    if _table_exists("runs"):
        if RUN_REPLAY_INDEX in _indexes("runs"):
            op.drop_index(RUN_REPLAY_INDEX, table_name="runs")
        existing_columns = _columns("runs")
        with op.batch_alter_table("runs") as batch:
            batch.drop_constraint("fk_runs_source_run_id_runs", type_="foreignkey")
            batch.drop_constraint("ck_runs_source_not_self", type_="check")
            batch.drop_constraint("ck_runs_replay_lineage_complete", type_="check")
            batch.drop_constraint("ck_runs_attempt_number_positive", type_="check")
            batch.drop_constraint("ck_runs_replay_kind_valid", type_="check")
            batch.drop_constraint("ck_runs_status_valid", type_="check")
            if "attempt_number" in existing_columns:
                batch.drop_column("attempt_number")
            if "replay_idempotency_key" in existing_columns:
                batch.drop_column("replay_idempotency_key")
            if "replay_kind" in existing_columns:
                batch.drop_column("replay_kind")
            if "source_run_id" in existing_columns:
                batch.drop_column("source_run_id")


def _normalize_run_statuses() -> None:
    op.execute(
        f"""
        UPDATE runs
        SET status = 'failed',
            error_message = COALESCE(
                error_message,
                'Migration normalized invalid run status'
            ),
            completed_at = COALESCE(completed_at, CURRENT_TIMESTAMP)
        WHERE status NOT IN {RUN_STATUS_SQL}
        """
    )


def _terminalize_duplicate_active_tasks() -> None:
    op.execute(
        f"""
        UPDATE scheduled_tasks
        SET state = 'failed',
            completed_at = COALESCE(completed_at, CURRENT_TIMESTAMP),
            error_message = COALESCE(
                error_message,
                'Migration resolved duplicate active scheduler task'
            )
        WHERE id IN (
            SELECT id
            FROM (
                SELECT
                    id,
                    ROW_NUMBER() OVER (
                        PARTITION BY run_id
                        ORDER BY
                            CASE WHEN state = 'dispatched' THEN 0 ELSE 1 END,
                            updated_at DESC,
                            created_at DESC,
                            id DESC
                    ) AS row_number
                FROM scheduled_tasks
                WHERE state IN {TASK_ACTIVE_STATE_SQL}
            ) ranked
            WHERE row_number > 1
        )
        """
    )
