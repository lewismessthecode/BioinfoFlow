"""merge agent attachment and steering heads

Revision ID: 0055_merge_agent_heads
Revises: 0054_agent_attachments, 0054_agent_turn_steering
Create Date: 2026-07-24
"""

from __future__ import annotations


revision = "0055_merge_agent_heads"
down_revision = ("0054_agent_attachments", "0054_agent_turn_steering")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
