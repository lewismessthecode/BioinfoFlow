"""merge conversation policy and run form heads

Revision ID: 0026_merge_conversation_and_form
Revises: 0024_conversation_execution_policy, 0025_drop_submission_hint
Create Date: 2026-04-20
"""

from __future__ import annotations


revision = "0026_merge_conversation_and_form"
down_revision = ("0024_conversation_execution_policy", "0025_drop_submission_hint")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
