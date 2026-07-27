"""add durable agent collaboration tree

Revision ID: 0056_agent_collaboration_tree
Revises: 0055_merge_agent_heads
Create Date: 2026-07-27
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0056_agent_collaboration_tree"
down_revision = "0055_merge_agent_heads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("agent_sessions"):
        return

    columns = {column["name"] for column in inspector.get_columns("agent_sessions")}
    additions = {
        "parent_session_id": sa.Column(
            "parent_session_id",
            sa.String(length=36),
            sa.ForeignKey("agent_sessions.id", ondelete="CASCADE"),
            nullable=True,
        ),
        "root_session_id": sa.Column(
            "root_session_id",
            sa.String(length=36),
            sa.ForeignKey("agent_sessions.id", ondelete="CASCADE"),
            nullable=True,
        ),
        "agent_name": sa.Column("agent_name", sa.String(length=80), nullable=True),
        "collaboration_slot": sa.Column(
            "collaboration_slot", sa.Integer(), nullable=True
        ),
        "spawned_by_turn_id": sa.Column(
            "spawned_by_turn_id",
            sa.String(length=36),
            sa.ForeignKey("agent_turns.id", ondelete="SET NULL"),
            nullable=True,
        ),
    }
    with op.batch_alter_table("agent_sessions") as batch_op:
        for name, column in additions.items():
            if name not in columns:
                batch_op.add_column(column)

    existing_indexes = {
        index["name"] for index in sa.inspect(op.get_bind()).get_indexes("agent_sessions")
    }
    indexes = (
        (
            "uq_agent_sessions_parent_agent_name",
            ["parent_session_id", "agent_name"],
            True,
            sa.text("parent_session_id IS NOT NULL AND agent_name IS NOT NULL"),
        ),
        (
            "uq_agent_sessions_root_collaboration_slot",
            ["root_session_id", "collaboration_slot"],
            True,
            sa.text("root_session_id IS NOT NULL AND collaboration_slot IS NOT NULL"),
        ),
        ("ix_agent_sessions_root_status", ["root_session_id", "status"], False, None),
        (
            "ix_agent_sessions_root_active_turn",
            ["root_session_id", "active_turn_id"],
            False,
            None,
        ),
        ("ix_agent_sessions_parent_session_id", ["parent_session_id"], False, None),
        ("ix_agent_sessions_spawned_by_turn_id", ["spawned_by_turn_id"], False, None),
    )
    for name, fields, unique, where in indexes:
        if name not in existing_indexes:
            op.create_index(
                name,
                "agent_sessions",
                fields,
                unique=unique,
                sqlite_where=where,
                postgresql_where=where,
            )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("agent_sessions"):
        return

    existing_indexes = {
        index["name"] for index in inspector.get_indexes("agent_sessions")
    }
    for name in (
        "ix_agent_sessions_spawned_by_turn_id",
        "ix_agent_sessions_parent_session_id",
        "ix_agent_sessions_root_active_turn",
        "ix_agent_sessions_root_status",
        "uq_agent_sessions_root_collaboration_slot",
        "uq_agent_sessions_parent_agent_name",
    ):
        if name in existing_indexes:
            op.drop_index(name, table_name="agent_sessions")

    columns = {column["name"] for column in inspector.get_columns("agent_sessions")}
    with op.batch_alter_table("agent_sessions") as batch_op:
        for name in (
            "spawned_by_turn_id",
            "collaboration_slot",
            "agent_name",
            "root_session_id",
            "parent_session_id",
        ):
            if name in columns:
                batch_op.drop_column(name)
