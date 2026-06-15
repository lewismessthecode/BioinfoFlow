"""remove builtin ollama catalog seed

Revision ID: 0036_remove_builtin_ollama_catalog
Revises: 0035_agent_turn_execution_leases
Create Date: 2026-06-15

Migrations 0031/0032 seeded a global built-in Ollama provider (fixed UUID
``10000000-0000-4000-8000-000000000006``) plus the ``llama3.3`` and
``deepseek-r1:latest`` models. Because that provider needs no credential it was
always "available", so it shadowed explicitly configured providers (for example
an env-managed vLLM endpoint) in default model selection.

This migration removes the built-in Ollama catalog while preserving any Ollama
provider a user or workspace created by hand. Built-in models referenced by a
profile's ``primary_model_id`` are kept (deleting them would orphan the profile)
and their provider is disabled instead so default selection skips it.
"""

from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op


revision = "0036_remove_builtin_ollama_catalog"
down_revision = "0035_agent_turn_execution_leases"
branch_labels = None
depends_on = None


BUILTIN_OLLAMA_PROVIDER_ID = "10000000-0000-4000-8000-000000000006"
BUILTIN_OLLAMA_MODEL_IDS = (
    "11000000-0000-4000-8000-000000000010",  # llama3.3
    "11000000-0000-4000-8000-000000000011",  # deepseek-r1:latest
)


def _table_exists(bind, table_name: str) -> bool:
    return table_name in sa.inspect(bind).get_table_names()


def _metadata_marks_builtin(raw_metadata: object) -> bool:
    if not raw_metadata:
        return False
    if isinstance(raw_metadata, str):
        try:
            raw_metadata = json.loads(raw_metadata)
        except json.JSONDecodeError:
            return False
    return isinstance(raw_metadata, dict) and bool(raw_metadata.get("builtin"))


def upgrade() -> None:
    bind = op.get_bind()

    # A partially-applied SQLite database may not have the LLM catalog tables yet
    # (they arrive in 0031). Nothing to clean up in that case.
    if not _table_exists(bind, "llm_providers") or not _table_exists(bind, "llm_models"):
        return

    # Identify built-in global Ollama providers: the fixed seed UUID, or any
    # global Ollama provider explicitly flagged ``builtin`` in metadata. User and
    # workspace scoped providers are never matched here.
    provider_rows = bind.execute(
        sa.text(
            """
            SELECT id, metadata
            FROM llm_providers
            WHERE kind = 'ollama'
              AND scope = 'global'
              AND workspace_id IS NULL
              AND user_id IS NULL
            """
        )
    ).mappings().all()

    builtin_provider_ids = {
        str(row["id"])
        for row in provider_rows
        if str(row["id"]) == BUILTIN_OLLAMA_PROVIDER_ID
        or _metadata_marks_builtin(row["metadata"])
    }
    # Always include the fixed seed UUID even if its row drifted (e.g. metadata
    # was cleared) so a partially-mutated deployment still gets cleaned up.
    builtin_provider_ids.add(BUILTIN_OLLAMA_PROVIDER_ID)

    builtin_model_ids: set[str] = set(BUILTIN_OLLAMA_MODEL_IDS)
    if builtin_provider_ids:
        model_rows = bind.execute(
            sa.text(
                "SELECT id FROM llm_models WHERE provider_id IN :provider_ids"
            ).bindparams(sa.bindparam("provider_ids", expanding=True)),
            {"provider_ids": list(builtin_provider_ids)},
        ).mappings().all()
        builtin_model_ids.update(str(row["id"]) for row in model_rows)

    if not builtin_model_ids and not builtin_provider_ids:
        return

    # Drop built-in model references from every profile's fallback list.
    _strip_fallback_references(bind, builtin_model_ids)

    # Keep any built-in model still used as a profile primary; deleting it would
    # leave a dangling primary_model_id. Such providers are disabled below.
    referenced_primary_ids = {
        str(row["primary_model_id"])
        for row in bind.execute(
            sa.text("SELECT primary_model_id FROM llm_model_profiles")
        ).mappings().all()
    }
    deletable_model_ids = builtin_model_ids - referenced_primary_ids

    if deletable_model_ids:
        bind.execute(
            sa.text(
                "DELETE FROM llm_models WHERE id IN :model_ids"
            ).bindparams(sa.bindparam("model_ids", expanding=True)),
            {"model_ids": list(deletable_model_ids)},
        )

    for provider_id in builtin_provider_ids:
        remaining = bind.execute(
            sa.text(
                "SELECT COUNT(*) FROM llm_models WHERE provider_id = :provider_id"
            ),
            {"provider_id": provider_id},
        ).scalar_one()
        if remaining:
            # A referenced primary model still lives here: keep the row but
            # disable it so default selection never falls back onto it.
            bind.execute(
                sa.text(
                    "UPDATE llm_providers SET enabled = 0 WHERE id = :provider_id"
                ),
                {"provider_id": provider_id},
            )
            continue
        bind.execute(
            sa.text(
                "DELETE FROM llm_provider_credentials WHERE provider_id = :provider_id"
            ),
            {"provider_id": provider_id},
        )
        bind.execute(
            sa.text("DELETE FROM llm_providers WHERE id = :provider_id"),
            {"provider_id": provider_id},
        )


def _strip_fallback_references(bind, builtin_model_ids: set[str]) -> None:
    rows = bind.execute(
        sa.text(
            "SELECT id, fallback_model_ids FROM llm_model_profiles "
            "WHERE fallback_model_ids IS NOT NULL"
        )
    ).mappings().all()
    for row in rows:
        raw = row["fallback_model_ids"]
        if isinstance(raw, str):
            try:
                fallback = json.loads(raw)
            except json.JSONDecodeError:
                continue
        else:
            fallback = raw
        if not isinstance(fallback, list):
            continue
        cleaned = [str(item) for item in fallback if str(item) not in builtin_model_ids]
        if len(cleaned) == len(fallback):
            continue
        bind.execute(
            sa.text(
                "UPDATE llm_model_profiles SET fallback_model_ids = :fallback "
                "WHERE id = :id"
            ),
            {
                "fallback": json.dumps(cleaned) if cleaned else None,
                "id": str(row["id"]),
            },
        )


def downgrade() -> None:
    # The built-in Ollama seed was a convenience default, not user data. Removal
    # is intentionally irreversible: re-seeding it would reintroduce the very
    # provider that shadowed explicit configuration.
    pass
