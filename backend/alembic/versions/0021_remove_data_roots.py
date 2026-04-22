"""remove project data_roots column

Revision ID: 0021_remove_data_roots
Revises: 0020_path_contract_v2
Create Date: 2026-04-16

"""
from typing import Sequence, Union

from alembic import op

revision: str = "0021_remove_data_roots"
down_revision: Union[str, None] = "0020_path_contract_v2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("projects") as batch_op:
        batch_op.drop_column("data_roots")


def downgrade() -> None:
    # Irreversible: ``data_roots`` held per-project reference path lists
    # that are not reconstructable from the new columns. Re-adding the
    # column with NULL/default (as the original downgrade did) silently
    # drops operator-configured data paths, so we refuse instead.
    # Restore from a pre-0021 backup to roll back.
    raise RuntimeError(
        "Migration 0021_remove_data_roots is irreversible. "
        "Restore from a pre-0021 backup to roll back."
    )
