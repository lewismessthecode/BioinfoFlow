"""persist long tool output separately from user-facing artifacts

Revision ID: 0064_agent_tool_outputs
Revises: 0063_agent_session_project_delete_cascade
"""

from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op


revision = "0064_agent_tool_outputs"
down_revision = "0063_agent_session_project_delete_cascade"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_tool_outputs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=True),
        sa.Column("tool_call_id", sa.String(length=200), nullable=False),
        sa.Column("command", sa.Text(), nullable=False),
        sa.Column("cwd", sa.String(length=1000), nullable=True),
        sa.Column("exit_code", sa.Integer(), nullable=True),
        sa.Column("file_path", sa.String(length=1000), nullable=False),
        sa.Column("resource_ref", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["agent_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["session_id"], ["agent_sessions.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "session_id",
            "run_id",
            "tool_call_id",
            name="uq_agent_tool_outputs_session_run_tool_call",
        ),
    )
    op.create_index(
        "ix_agent_tool_outputs_session_id", "agent_tool_outputs", ["session_id"]
    )
    op.create_index("ix_agent_tool_outputs_run_id", "agent_tool_outputs", ["run_id"])
    _move_legacy_command_outputs()


def downgrade() -> None:
    _restore_legacy_command_outputs()
    op.drop_index("ix_agent_tool_outputs_run_id", table_name="agent_tool_outputs")
    op.drop_index("ix_agent_tool_outputs_session_id", table_name="agent_tool_outputs")
    op.drop_table("agent_tool_outputs")


def _restore_legacy_command_outputs() -> None:
    bind = op.get_bind()
    metadata = sa.MetaData()
    artifacts = sa.Table("agent_artifacts", metadata, autoload_with=bind)
    outputs = sa.Table("agent_tool_outputs", metadata, autoload_with=bind)
    rows = list(bind.execute(sa.select(outputs)).mappings())
    if any(
        _json_object(row.get("resource_ref")).get("legacy_storage") != "artifact"
        for row in rows
    ):
        raise RuntimeError(
            "Cannot downgrade 0064 after new Tool Output records were created; "
            "restore the pre-upgrade state snapshot instead."
        )
    for row in rows:
        resource_ref = _json_object(row.get("resource_ref"))
        if resource_ref.pop("legacy_storage", None) != "artifact":
            continue
        bind.execute(
            artifacts.insert().values(
                id=row["id"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                session_id=row["session_id"],
                run_id=row.get("run_id"),
                type="command_output",
                title=row.get("command") or "Shell command",
                summary="Full output preserved because the inline result was truncated.",
                payload=None,
                file_path=row.get("file_path"),
                resource_ref=resource_ref,
            )
        )


def _json_object(value) -> dict:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
        except (TypeError, ValueError):
            return {}
        return decoded if isinstance(decoded, dict) else {}
    return {}


def _move_legacy_command_outputs() -> None:
    bind = op.get_bind()
    metadata = sa.MetaData()
    artifacts = sa.Table("agent_artifacts", metadata, autoload_with=bind)
    outputs = sa.Table("agent_tool_outputs", metadata, autoload_with=bind)
    rows = bind.execute(
        sa.select(artifacts).where(artifacts.c.type == "command_output")
    ).mappings()
    for row in rows:
        resource_ref = _json_object(row.get("resource_ref"))
        resource_ref["legacy_storage"] = "artifact"
        bind.execute(
            outputs.insert().values(
                id=row["id"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                session_id=row["session_id"],
                run_id=row.get("run_id"),
                tool_call_id=f"legacy-artifact:{row['id']}",
                command=row.get("title") or "Shell command",
                cwd=None,
                exit_code=None,
                file_path=row.get("file_path") or "",
                resource_ref=resource_ref,
            )
        )
    bind.execute(artifacts.delete().where(artifacts.c.type == "command_output"))
