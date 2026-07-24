"""add remote connection jump host

Revision ID: 0053_remote_connection_jump_host
Revises: 0052_agent_user_custom_instructions
Create Date: 2026-07-23
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0053_remote_connection_jump_host"
down_revision = "0052_agent_user_custom_instructions"
branch_labels = None
depends_on = None


DIRECT_AUTH_METHOD_SQL = "('password', 'private_key', 'ssh_config', 'key_file', 'agent')"
AUTH_METHOD_SQL = "('password', 'private_key', 'ssh_config', 'key_file', 'agent', 'jump')"


def upgrade() -> None:
    with op.batch_alter_table(
        "remote_connections",
        reflect_kwargs={"resolve_fks": False},
    ) as batch:
        batch.add_column(sa.Column("jump_connection_id", sa.String(length=36), nullable=True))
        batch.create_foreign_key(
            "fk_remote_connections_jump_connection_id",
            "remote_connections",
            ["jump_connection_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch.drop_constraint("ck_remote_connections_auth_method", type_="check")
        batch.create_check_constraint(
            "ck_remote_connections_auth_method",
            f"auth_method IN {AUTH_METHOD_SQL}",
        )
        batch.create_index(
            "ix_remote_connections_jump_connection_id",
            ["jump_connection_id"],
        )


def downgrade() -> None:
    op.execute(
        """
        UPDATE remote_connections
        SET auth_method = 'agent',
            jump_connection_id = NULL
        WHERE auth_method = 'jump'
        """
    )
    with op.batch_alter_table(
        "remote_connections",
        reflect_kwargs={"resolve_fks": False},
    ) as batch:
        batch.drop_index("ix_remote_connections_jump_connection_id")
        batch.drop_constraint("ck_remote_connections_auth_method", type_="check")
        batch.create_check_constraint(
            "ck_remote_connections_auth_method",
            f"auth_method IN {DIRECT_AUTH_METHOD_SQL}",
        )
        batch.drop_constraint(
            "fk_remote_connections_jump_connection_id",
            type_="foreignkey",
        )
        batch.drop_column("jump_connection_id")
