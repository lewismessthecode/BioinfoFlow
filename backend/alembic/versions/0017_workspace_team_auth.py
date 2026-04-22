"""add single-workspace team auth scaffolding

Revision ID: 0017_workspace_team_auth
Revises: 0016_project_is_default
Create Date: 2026-04-08
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0017_workspace_team_auth"
down_revision = "0016_project_is_default"
branch_labels = None
depends_on = None

DEFAULT_WORKSPACE_ID = "00000000-0000-0000-0000-000000000001"
DEFAULT_WORKSPACE_NAME = "Bioinfoflow Team"
DEFAULT_WORKSPACE_SLUG = "bioinfoflow-team"


def upgrade() -> None:
    op.create_table(
        "workspaces",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column(
            "is_default",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("slug", name="uq_workspaces_slug"),
    )
    op.create_table(
        "workspace_memberships",
        sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column(
            "role",
            sa.String(length=20),
            nullable=False,
            server_default="member",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "user_id",
            name="uq_workspace_memberships_workspace_user",
        ),
    )
    op.create_index(
        "ix_workspace_memberships_workspace_id",
        "workspace_memberships",
        ["workspace_id"],
    )
    op.create_index(
        "ix_workspace_memberships_user_id",
        "workspace_memberships",
        ["user_id"],
    )

    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            INSERT INTO workspaces (id, name, slug, is_default)
            VALUES (:id, :name, :slug, 1)
            """
        ),
        {
            "id": DEFAULT_WORKSPACE_ID,
            "name": DEFAULT_WORKSPACE_NAME,
            "slug": DEFAULT_WORKSPACE_SLUG,
        },
    )

    op.add_column(
        "projects",
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "projects",
        sa.Column(
            "workspace_id",
            sa.String(length=36),
            nullable=False,
            server_default=DEFAULT_WORKSPACE_ID,
        ),
    )
    op.create_index(
        "ix_projects_created_by_user_id",
        "projects",
        ["created_by_user_id"],
    )
    op.create_index("ix_projects_workspace_id", "projects", ["workspace_id"])

    op.add_column(
        "conversations",
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
    )
    op.create_index(
        "ix_conversations_created_by_user_id",
        "conversations",
        ["created_by_user_id"],
    )

    conn.execute(
        sa.text(
            """
            UPDATE projects
            SET created_by_user_id = COALESCE(created_by_user_id, user_id),
                workspace_id = :workspace_id
            """
        ),
        {"workspace_id": DEFAULT_WORKSPACE_ID},
    )
    conn.execute(
        sa.text(
            """
            UPDATE conversations
            SET created_by_user_id = COALESCE(created_by_user_id, user_id)
            """
        )
    )

    op.execute("DROP INDEX IF EXISTS uq_projects_one_default_per_user")

    # Old auth created one default project per user. Keep the oldest default
    # project as the shared workspace default and demote the rest.
    conn.execute(
        sa.text(
            """
            UPDATE projects
            SET is_default = 0
            WHERE is_default = 1
              AND id NOT IN (
                SELECT id
                FROM projects
                WHERE is_default = 1
                ORDER BY created_at ASC, id ASC
                LIMIT 1
              )
            """
        )
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_projects_one_default_per_workspace "
        "ON projects (workspace_id) WHERE is_default = 1"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_projects_one_default_per_workspace")
    op.execute(
        "CREATE UNIQUE INDEX uq_projects_one_default_per_user "
        "ON projects (user_id) WHERE is_default = 1"
    )

    op.drop_index("ix_conversations_created_by_user_id", table_name="conversations")
    op.drop_column("conversations", "created_by_user_id")

    op.drop_index("ix_projects_workspace_id", table_name="projects")
    op.drop_index("ix_projects_created_by_user_id", table_name="projects")
    op.drop_column("projects", "workspace_id")
    op.drop_column("projects", "created_by_user_id")

    op.drop_index("ix_workspace_memberships_user_id", table_name="workspace_memberships")
    op.drop_index(
        "ix_workspace_memberships_workspace_id",
        table_name="workspace_memberships",
    )
    op.drop_table("workspace_memberships")
    op.drop_table("workspaces")
