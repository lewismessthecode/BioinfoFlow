"""merge workspace auth and image pull failure heads

Revision ID: 0018_merge_workspace_team_auth_and_image_pull_failures
Revises: 0017_workspace_team_auth, 0017_image_pull_failures
Create Date: 2026-04-08
"""

from __future__ import annotations


revision = "0018_merge_workspace_team_auth_and_image_pull_failures"
down_revision = ("0017_workspace_team_auth", "0017_image_pull_failures")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
