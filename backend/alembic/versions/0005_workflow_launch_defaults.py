"""legacy workflow launch defaults compatibility revision

Revision ID: 0005_workflow_launch_defaults
Revises: 0004_agent_approvals_and_policy_mode
Create Date: 2026-03-18
"""

from __future__ import annotations


revision = "0005_workflow_launch_defaults"
down_revision = "0004_agent_approvals_and_policy_mode"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Compatibility placeholder for legacy local databases.

    Historical local databases may already record this revision even though the
    original migration file is no longer present in the repo. We keep this
    revision as a no-op so Alembic can continue the migration chain without
    forcing a destructive rebuild of existing SQLite data.
    """


def downgrade() -> None:
    """No-op downgrade for compatibility placeholder."""
