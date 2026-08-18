"""cascade agent sessions when deleting projects

Revision ID: 0063_agent_session_project_delete_cascade
Revises: 0062_agent_model_traces
Create Date: 2026-08-18
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0063_agent_session_project_delete_cascade"
down_revision = "0062_agent_model_traces"
branch_labels = None
depends_on = None


_FK_NAME = "fk_agent_sessions_project_id_projects"
_NAMING_CONVENTION = {
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
}


def _project_foreign_key_name() -> str:
    inspector = sa.inspect(op.get_bind())
    for foreign_key in inspector.get_foreign_keys("agent_sessions"):
        if (
            foreign_key.get("constrained_columns") == ["project_id"]
            and foreign_key.get("referred_table") == "projects"
        ):
            return str(foreign_key.get("name") or _FK_NAME)
    raise RuntimeError("agent_sessions.project_id foreign key was not found")


def _replace_project_foreign_key(*, ondelete: str) -> None:
    existing_name = _project_foreign_key_name()
    with op.batch_alter_table(
        "agent_sessions",
        naming_convention=_NAMING_CONVENTION,
        reflect_kwargs={"resolve_fks": False},
    ) as batch:
        batch.drop_constraint(existing_name, type_="foreignkey")
        batch.create_foreign_key(
            _FK_NAME,
            "projects",
            ["project_id"],
            ["id"],
            ondelete=ondelete,
        )


def upgrade() -> None:
    _replace_project_foreign_key(ondelete="CASCADE")


def downgrade() -> None:
    _replace_project_foreign_key(ondelete="SET NULL")
