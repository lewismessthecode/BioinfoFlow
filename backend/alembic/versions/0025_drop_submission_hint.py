"""drop workflows.submission_hint column

Revision ID: 0025_drop_submission_hint
Revises: 0024_run_error_heartbeat
Create Date: 2026-04-20

Removes the legacy ``submission_hint`` JSON column. Phase 1 of the run
rewrite introduced ``form_spec`` as the deterministic, frontend-renderable
description of run inputs; the hint was kept transitionally for the
RunSubmissionService compile path. With the bridge translating asset URIs
and engine keys directly, the hint is no longer consumed.
"""

from __future__ import annotations

from alembic import op


revision = "0025_drop_submission_hint"
down_revision = "0024_run_error_heartbeat"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("workflows") as batch:
        batch.drop_column("submission_hint")


def downgrade() -> None:
    raise RuntimeError(
        "Migration 0025_drop_submission_hint is irreversible. "
        "submission_hint contents were derived from schema_json + workflow text "
        "and cannot be reconstructed faithfully. Restore from a pre-0025 "
        "backup if a downgrade is required."
    )
