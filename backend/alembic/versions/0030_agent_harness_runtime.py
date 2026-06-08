"""agent harness runtime

Revision ID: 0030_agent_harness_runtime
Revises: 0029_drop_legacy_agent_tables
Create Date: 2026-06-08
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op


revision = "0030_agent_harness_runtime"
down_revision = "0029_drop_legacy_agent_tables"
branch_labels = None
depends_on = None


def _timestamps() -> tuple[sa.Column, sa.Column]:
    return (
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def upgrade() -> None:
    with op.batch_alter_table("agent_sessions") as batch:
        batch.alter_column("project_id", existing_type=sa.String(length=36), nullable=True)
        batch.add_column(sa.Column("runtime_mode", sa.String(length=40), nullable=False, server_default="api"))
        batch.add_column(sa.Column("prompt_snapshot", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("toolset_policy", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("context_policy", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("compression_state", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("lineage", sa.JSON(), nullable=True))

    with op.batch_alter_table("agent_turns") as batch:
        batch.alter_column("project_id", existing_type=sa.String(length=36), nullable=True)
        batch.add_column(sa.Column("termination_reason", sa.String(length=80), nullable=True))
        batch.add_column(sa.Column("loop_state", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("iteration_count", sa.Integer(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("budget_snapshot", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("interrupt_requested_at", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "agent_messages",
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("turn_id", sa.String(length=36), nullable=True),
        sa.Column("role", sa.String(length=40), nullable=False),
        sa.Column("content_parts", sa.JSON(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("ordering_index", sa.Integer(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["agent_sessions.id"],
            name="fk_agent_messages_session_id_agent_sessions",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["turn_id"],
            ["agent_turns.id"],
            name="fk_agent_messages_turn_id_agent_turns",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_agent_messages"),
    )
    op.create_index("ix_agent_messages_ordering_index", "agent_messages", ["ordering_index"])
    op.create_index("ix_agent_messages_role", "agent_messages", ["role"])
    op.create_index("ix_agent_messages_session_id", "agent_messages", ["session_id"])
    op.create_index("ix_agent_messages_status", "agent_messages", ["status"])
    op.create_index("ix_agent_messages_turn_id", "agent_messages", ["turn_id"])

    _resequence_events()
    with op.batch_alter_table("agent_events") as batch:
        batch.drop_constraint("uq_agent_events_turn_seq", type_="unique")
        batch.alter_column("turn_id", existing_type=sa.String(length=36), nullable=True)
        batch.create_unique_constraint("uq_agent_events_session_seq", ["session_id", "seq"])

    with op.batch_alter_table("agent_actions") as batch:
        batch.add_column(sa.Column("tool_call_id", sa.String(length=120), nullable=True))
        batch.add_column(sa.Column("normalized_input", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("exposure_policy", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("output_ref", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("output_summary", sa.Text(), nullable=True))
        batch.add_column(sa.Column("requires_resume", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_index("ix_agent_actions_tool_call_id", "agent_actions", ["tool_call_id"])

    with op.batch_alter_table("agent_sessions") as batch:
        batch.alter_column("runtime_mode", server_default=None)
    with op.batch_alter_table("agent_turns") as batch:
        batch.alter_column("iteration_count", server_default=None)
    with op.batch_alter_table("agent_actions") as batch:
        batch.alter_column("requires_resume", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_agent_actions_tool_call_id", table_name="agent_actions")
    with op.batch_alter_table("agent_actions") as batch:
        batch.drop_column("requires_resume")
        batch.drop_column("output_summary")
        batch.drop_column("output_ref")
        batch.drop_column("exposure_policy")
        batch.drop_column("normalized_input")
        batch.drop_column("tool_call_id")

    with op.batch_alter_table("agent_events") as batch:
        batch.drop_constraint("uq_agent_events_session_seq", type_="unique")
        batch.alter_column("turn_id", existing_type=sa.String(length=36), nullable=False)
        batch.create_unique_constraint("uq_agent_events_turn_seq", ["turn_id", "seq"])

    op.drop_index("ix_agent_messages_turn_id", table_name="agent_messages")
    op.drop_index("ix_agent_messages_status", table_name="agent_messages")
    op.drop_index("ix_agent_messages_session_id", table_name="agent_messages")
    op.drop_index("ix_agent_messages_role", table_name="agent_messages")
    op.drop_index("ix_agent_messages_ordering_index", table_name="agent_messages")
    op.drop_table("agent_messages")

    with op.batch_alter_table("agent_turns") as batch:
        batch.drop_column("interrupt_requested_at")
        batch.drop_column("budget_snapshot")
        batch.drop_column("iteration_count")
        batch.drop_column("loop_state")
        batch.drop_column("termination_reason")
        batch.alter_column("project_id", existing_type=sa.String(length=36), nullable=False)

    with op.batch_alter_table("agent_sessions") as batch:
        batch.drop_column("lineage")
        batch.drop_column("compression_state")
        batch.drop_column("context_policy")
        batch.drop_column("toolset_policy")
        batch.drop_column("prompt_snapshot")
        batch.drop_column("runtime_mode")
        batch.alter_column("project_id", existing_type=sa.String(length=36), nullable=False)


def _resequence_events() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name
    if dialect == "sqlite":
        op.execute(
            """
            WITH ordered AS (
              SELECT id, ROW_NUMBER() OVER (
                PARTITION BY session_id ORDER BY created_at, id
              ) AS next_seq
              FROM agent_events
            )
            UPDATE agent_events
            SET seq = (SELECT next_seq FROM ordered WHERE ordered.id = agent_events.id)
            """
        )
        return

    op.execute(
        """
        UPDATE agent_events AS event
        SET seq = ordered.next_seq
        FROM (
          SELECT id, ROW_NUMBER() OVER (
            PARTITION BY session_id ORDER BY created_at, id
          ) AS next_seq
          FROM agent_events
        ) AS ordered
        WHERE ordered.id = event.id
        """
    )
