"""add agent core and llm contract tables

Revision ID: 0028_agent_core_llm_contracts
Revises: 0027_scheduler_tasks_cascade
Create Date: 2026-06-04
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op


revision = "0028_agent_core_llm_contracts"
down_revision = "0027_scheduler_tasks_cascade"
branch_labels = None
depends_on = None


def _timestamps() -> tuple[sa.Column, sa.Column]:
    return (
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def upgrade() -> None:
    op.create_table(
        "llm_providers",
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("base_url", sa.String(length=500), nullable=True),
        sa.Column("api_key_ref", sa.String(length=300), nullable=True),
        sa.Column("scope", sa.String(length=20), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=True),
        sa.Column("user_id", sa.String(length=36), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("test_status", sa.JSON(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_llm_providers_workspace_id_workspaces",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_llm_providers"),
        sa.UniqueConstraint(
            "scope",
            "workspace_id",
            "user_id",
            "name",
            name="uq_llm_providers_scope_name",
        ),
    )
    op.create_index("ix_llm_providers_kind", "llm_providers", ["kind"])
    op.create_index("ix_llm_providers_scope", "llm_providers", ["scope"])
    op.create_index("ix_llm_providers_user_id", "llm_providers", ["user_id"])
    op.create_index(
        "ix_llm_providers_workspace_id",
        "llm_providers",
        ["workspace_id"],
    )

    op.create_table(
        "llm_models",
        sa.Column("provider_id", sa.String(length=36), nullable=False),
        sa.Column("model_id", sa.String(length=200), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("context_length", sa.Integer(), nullable=True),
        sa.Column("max_output_tokens", sa.Integer(), nullable=True),
        sa.Column("supports_tools", sa.Boolean(), nullable=False),
        sa.Column("supports_streaming", sa.Boolean(), nullable=False),
        sa.Column("supports_vision", sa.Boolean(), nullable=False),
        sa.Column("supports_json_schema", sa.Boolean(), nullable=False),
        sa.Column("supports_reasoning", sa.Boolean(), nullable=False),
        sa.Column("default_temperature", sa.String(length=20), nullable=True),
        sa.Column("default_top_p", sa.String(length=20), nullable=True),
        sa.Column("cost_metadata", sa.JSON(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["provider_id"],
            ["llm_providers.id"],
            name="fk_llm_models_provider_id_llm_providers",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_llm_models"),
        sa.UniqueConstraint(
            "provider_id",
            "model_id",
            name="uq_llm_models_provider_model",
        ),
    )
    op.create_index("ix_llm_models_provider_id", "llm_models", ["provider_id"])

    op.create_table(
        "llm_model_profiles",
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("task_type", sa.String(length=80), nullable=False),
        sa.Column("primary_model_id", sa.String(length=36), nullable=False),
        sa.Column("fallback_model_ids", sa.JSON(), nullable=True),
        sa.Column("reasoning_budget", sa.Integer(), nullable=True),
        sa.Column("max_tokens", sa.Integer(), nullable=True),
        sa.Column("cost_ceiling", sa.String(length=40), nullable=True),
        sa.Column("routing_policy", sa.JSON(), nullable=True),
        sa.Column("permission_overrides", sa.JSON(), nullable=True),
        sa.Column("scope", sa.String(length=20), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=True),
        sa.Column("user_id", sa.String(length=36), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["primary_model_id"],
            ["llm_models.id"],
            name="fk_llm_model_profiles_primary_model_id_llm_models",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_llm_model_profiles_workspace_id_workspaces",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_llm_model_profiles"),
        sa.UniqueConstraint(
            "scope",
            "workspace_id",
            "user_id",
            "name",
            name="uq_llm_model_profiles_scope_name",
        ),
    )
    op.create_index(
        "ix_llm_model_profiles_primary_model_id",
        "llm_model_profiles",
        ["primary_model_id"],
    )
    op.create_index(
        "ix_llm_model_profiles_scope",
        "llm_model_profiles",
        ["scope"],
    )
    op.create_index(
        "ix_llm_model_profiles_task_type",
        "llm_model_profiles",
        ["task_type"],
    )
    op.create_index(
        "ix_llm_model_profiles_user_id",
        "llm_model_profiles",
        ["user_id"],
    )
    op.create_index(
        "ix_llm_model_profiles_workspace_id",
        "llm_model_profiles",
        ["workspace_id"],
    )

    op.create_table(
        "agent_sessions",
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=True),
        sa.Column("role_profile", sa.String(length=80), nullable=False),
        sa.Column("permission_mode", sa.String(length=40), nullable=False),
        sa.Column("automation_mode", sa.String(length=40), nullable=False),
        sa.Column("default_model_profile_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["default_model_profile_id"],
            ["llm_model_profiles.id"],
            name="fk_agent_sessions_default_model_profile_id_llm_model_profiles",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_agent_sessions_project_id_projects",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_agent_sessions_workspace_id_workspaces",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_agent_sessions"),
    )
    op.create_index(
        "ix_agent_sessions_default_model_profile_id",
        "agent_sessions",
        ["default_model_profile_id"],
    )
    op.create_index("ix_agent_sessions_project_id", "agent_sessions", ["project_id"])
    op.create_index("ix_agent_sessions_status", "agent_sessions", ["status"])
    op.create_index("ix_agent_sessions_user_id", "agent_sessions", ["user_id"])
    op.create_index(
        "ix_agent_sessions_workspace_id",
        "agent_sessions",
        ["workspace_id"],
    )

    op.create_table(
        "agent_turns",
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("input_text", sa.Text(), nullable=False),
        sa.Column("input_parts", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("model_profile_snapshot", sa.JSON(), nullable=True),
        sa.Column("final_text", sa.Text(), nullable=True),
        sa.Column("token_usage", sa.JSON(), nullable=True),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_agent_turns_project_id_projects",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["agent_sessions.id"],
            name="fk_agent_turns_session_id_agent_sessions",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_agent_turns_workspace_id_workspaces",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_agent_turns"),
    )
    op.create_index("ix_agent_turns_project_id", "agent_turns", ["project_id"])
    op.create_index("ix_agent_turns_session_id", "agent_turns", ["session_id"])
    op.create_index("ix_agent_turns_status", "agent_turns", ["status"])
    op.create_index("ix_agent_turns_user_id", "agent_turns", ["user_id"])
    op.create_index("ix_agent_turns_workspace_id", "agent_turns", ["workspace_id"])

    op.create_table(
        "agent_events",
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("turn_id", sa.String(length=36), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(length=80), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("visibility", sa.String(length=20), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["agent_sessions.id"],
            name="fk_agent_events_session_id_agent_sessions",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["turn_id"],
            ["agent_turns.id"],
            name="fk_agent_events_turn_id_agent_turns",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_agent_events"),
        sa.UniqueConstraint("turn_id", "seq", name="uq_agent_events_turn_seq"),
    )
    op.create_index("ix_agent_events_session_id", "agent_events", ["session_id"])
    op.create_index("ix_agent_events_turn_id", "agent_events", ["turn_id"])
    op.create_index("ix_agent_events_type", "agent_events", ["type"])
    op.create_index("ix_agent_events_visibility", "agent_events", ["visibility"])

    op.create_table(
        "agent_actions",
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("turn_id", sa.String(length=36), nullable=False),
        sa.Column("parent_action_id", sa.String(length=36), nullable=True),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("input", sa.JSON(), nullable=False),
        sa.Column("input_preview", sa.Text(), nullable=True),
        sa.Column("redacted_input", sa.JSON(), nullable=True),
        sa.Column("risk_level", sa.String(length=30), nullable=False),
        sa.Column("risk_reasons", sa.JSON(), nullable=True),
        sa.Column("read_scope", sa.JSON(), nullable=True),
        sa.Column("write_scope", sa.JSON(), nullable=True),
        sa.Column("affected_resources", sa.JSON(), nullable=True),
        sa.Column("permission_decision", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error", sa.JSON(), nullable=True),
        sa.Column("audit_summary", sa.Text(), nullable=True),
        sa.Column("rollback_hint", sa.Text(), nullable=True),
        sa.Column("artifact_policy", sa.JSON(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["parent_action_id"],
            ["agent_actions.id"],
            name="fk_agent_actions_parent_action_id_agent_actions",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["agent_sessions.id"],
            name="fk_agent_actions_session_id_agent_sessions",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["turn_id"],
            ["agent_turns.id"],
            name="fk_agent_actions_turn_id_agent_turns",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_agent_actions"),
    )
    op.create_index("ix_agent_actions_kind", "agent_actions", ["kind"])
    op.create_index("ix_agent_actions_name", "agent_actions", ["name"])
    op.create_index(
        "ix_agent_actions_parent_action_id",
        "agent_actions",
        ["parent_action_id"],
    )
    op.create_index("ix_agent_actions_session_id", "agent_actions", ["session_id"])
    op.create_index("ix_agent_actions_status", "agent_actions", ["status"])
    op.create_index("ix_agent_actions_turn_id", "agent_actions", ["turn_id"])

    op.create_table(
        "agent_artifacts",
        sa.Column("session_id", sa.String(length=36), nullable=False),
        sa.Column("turn_id", sa.String(length=36), nullable=False),
        sa.Column("action_id", sa.String(length=36), nullable=True),
        sa.Column("type", sa.String(length=60), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("file_path", sa.String(length=1000), nullable=True),
        sa.Column("resource_ref", sa.JSON(), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["action_id"],
            ["agent_actions.id"],
            name="fk_agent_artifacts_action_id_agent_actions",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["agent_sessions.id"],
            name="fk_agent_artifacts_session_id_agent_sessions",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["turn_id"],
            ["agent_turns.id"],
            name="fk_agent_artifacts_turn_id_agent_turns",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_agent_artifacts"),
    )
    op.create_index("ix_agent_artifacts_action_id", "agent_artifacts", ["action_id"])
    op.create_index("ix_agent_artifacts_session_id", "agent_artifacts", ["session_id"])
    op.create_index("ix_agent_artifacts_turn_id", "agent_artifacts", ["turn_id"])
    op.create_index("ix_agent_artifacts_type", "agent_artifacts", ["type"])

    op.create_table(
        "agent_memories",
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("session_id", sa.String(length=36), nullable=True),
        sa.Column("scope", sa.String(length=40), nullable=False),
        sa.Column("type", sa.String(length=80), nullable=False),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column("source", sa.JSON(), nullable=True),
        sa.Column("confidence", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_agent_memories_project_id_projects",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["agent_sessions.id"],
            name="fk_agent_memories_session_id_agent_sessions",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name="fk_agent_memories_workspace_id_workspaces",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_agent_memories"),
    )
    op.create_index("ix_agent_memories_project_id", "agent_memories", ["project_id"])
    op.create_index("ix_agent_memories_scope", "agent_memories", ["scope"])
    op.create_index("ix_agent_memories_session_id", "agent_memories", ["session_id"])
    op.create_index("ix_agent_memories_status", "agent_memories", ["status"])
    op.create_index("ix_agent_memories_type", "agent_memories", ["type"])
    op.create_index("ix_agent_memories_workspace_id", "agent_memories", ["workspace_id"])


def downgrade() -> None:
    op.drop_index("ix_agent_memories_workspace_id", table_name="agent_memories")
    op.drop_index("ix_agent_memories_type", table_name="agent_memories")
    op.drop_index("ix_agent_memories_status", table_name="agent_memories")
    op.drop_index("ix_agent_memories_session_id", table_name="agent_memories")
    op.drop_index("ix_agent_memories_scope", table_name="agent_memories")
    op.drop_index("ix_agent_memories_project_id", table_name="agent_memories")
    op.drop_table("agent_memories")

    op.drop_index("ix_agent_artifacts_type", table_name="agent_artifacts")
    op.drop_index("ix_agent_artifacts_turn_id", table_name="agent_artifacts")
    op.drop_index("ix_agent_artifacts_session_id", table_name="agent_artifacts")
    op.drop_index("ix_agent_artifacts_action_id", table_name="agent_artifacts")
    op.drop_table("agent_artifacts")

    op.drop_index("ix_agent_actions_turn_id", table_name="agent_actions")
    op.drop_index("ix_agent_actions_status", table_name="agent_actions")
    op.drop_index("ix_agent_actions_session_id", table_name="agent_actions")
    op.drop_index("ix_agent_actions_parent_action_id", table_name="agent_actions")
    op.drop_index("ix_agent_actions_name", table_name="agent_actions")
    op.drop_index("ix_agent_actions_kind", table_name="agent_actions")
    op.drop_table("agent_actions")

    op.drop_index("ix_agent_events_visibility", table_name="agent_events")
    op.drop_index("ix_agent_events_type", table_name="agent_events")
    op.drop_index("ix_agent_events_turn_id", table_name="agent_events")
    op.drop_index("ix_agent_events_session_id", table_name="agent_events")
    op.drop_table("agent_events")

    op.drop_index("ix_agent_turns_workspace_id", table_name="agent_turns")
    op.drop_index("ix_agent_turns_user_id", table_name="agent_turns")
    op.drop_index("ix_agent_turns_status", table_name="agent_turns")
    op.drop_index("ix_agent_turns_session_id", table_name="agent_turns")
    op.drop_index("ix_agent_turns_project_id", table_name="agent_turns")
    op.drop_table("agent_turns")

    op.drop_index("ix_agent_sessions_workspace_id", table_name="agent_sessions")
    op.drop_index("ix_agent_sessions_user_id", table_name="agent_sessions")
    op.drop_index("ix_agent_sessions_status", table_name="agent_sessions")
    op.drop_index("ix_agent_sessions_project_id", table_name="agent_sessions")
    op.drop_index(
        "ix_agent_sessions_default_model_profile_id",
        table_name="agent_sessions",
    )
    op.drop_table("agent_sessions")

    op.drop_index(
        "ix_llm_model_profiles_workspace_id",
        table_name="llm_model_profiles",
    )
    op.drop_index("ix_llm_model_profiles_user_id", table_name="llm_model_profiles")
    op.drop_index("ix_llm_model_profiles_task_type", table_name="llm_model_profiles")
    op.drop_index("ix_llm_model_profiles_scope", table_name="llm_model_profiles")
    op.drop_index(
        "ix_llm_model_profiles_primary_model_id",
        table_name="llm_model_profiles",
    )
    op.drop_table("llm_model_profiles")

    op.drop_index("ix_llm_models_provider_id", table_name="llm_models")
    op.drop_table("llm_models")

    op.drop_index("ix_llm_providers_workspace_id", table_name="llm_providers")
    op.drop_index("ix_llm_providers_user_id", table_name="llm_providers")
    op.drop_index("ix_llm_providers_scope", table_name="llm_providers")
    op.drop_index("ix_llm_providers_kind", table_name="llm_providers")
    op.drop_table("llm_providers")
