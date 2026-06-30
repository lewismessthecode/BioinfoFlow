"""support stored remote connection credentials

Revision ID: 0042_remote_connection_stored_credentials
Revises: 0041_run_module_invariants
Create Date: 2026-06-30
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0042_remote_connection_stored_credentials"
down_revision = "0041_run_module_invariants"
branch_labels = None
depends_on = None


AUTH_METHOD_SQL = "('password', 'private_key', 'ssh_config', 'key_file', 'agent')"
LEGACY_AUTH_METHOD_SQL = "('ssh_config', 'key_file', 'agent')"


def upgrade() -> None:
    with op.batch_alter_table(
        "remote_connections",
        reflect_kwargs={"resolve_fks": False},
    ) as batch:
        batch.add_column(sa.Column("encrypted_password", sa.Text(), nullable=True))
        batch.add_column(sa.Column("encrypted_private_key", sa.Text(), nullable=True))
        batch.add_column(sa.Column("encrypted_passphrase", sa.Text(), nullable=True))
        batch.drop_constraint("ck_remote_connections_auth_method", type_="check")
        batch.create_check_constraint(
            "ck_remote_connections_auth_method",
            f"auth_method IN {AUTH_METHOD_SQL}",
        )


def downgrade() -> None:
    op.execute(
        """
        UPDATE remote_connections
        SET auth_method = 'agent',
            encrypted_password = NULL,
            encrypted_private_key = NULL,
            encrypted_passphrase = NULL
        WHERE auth_method IN ('password', 'private_key')
        """
    )
    with op.batch_alter_table(
        "remote_connections",
        reflect_kwargs={"resolve_fks": False},
    ) as batch:
        batch.drop_constraint("ck_remote_connections_auth_method", type_="check")
        batch.create_check_constraint(
            "ck_remote_connections_auth_method",
            f"auth_method IN {LEGACY_AUTH_METHOD_SQL}",
        )
        batch.drop_column("encrypted_passphrase")
        batch.drop_column("encrypted_private_key")
        batch.drop_column("encrypted_password")
