"""seed ollama deepseek r1 model

Revision ID: 0032_seed_ollama_deepseek_r1
Revises: 0031_llm_provider_credentials
Create Date: 2026-06-09
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0032_seed_ollama_deepseek_r1"
down_revision = "0031_llm_provider_credentials"
branch_labels = None
depends_on = None


OLLAMA_PROVIDER_ID = "10000000-0000-4000-8000-000000000006"
DEEPSEEK_R1_MODEL_ID = "11000000-0000-4000-8000-000000000011"


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            INSERT INTO llm_models
              (id, provider_id, model_id, display_name, context_length,
               max_output_tokens, supports_tools, supports_streaming,
               supports_vision, supports_json_schema, supports_reasoning,
               default_temperature, default_top_p, cost_metadata, metadata)
            SELECT
              :id, :provider_id, 'deepseek-r1:latest', 'DeepSeek R1',
              128000, 8192, 0, 1, 0, 0, 1, NULL, NULL, NULL, NULL
            WHERE EXISTS (
              SELECT 1 FROM llm_providers WHERE id = :provider_id
            )
            AND NOT EXISTS (
              SELECT 1 FROM llm_models
              WHERE provider_id = :provider_id
                AND model_id = 'deepseek-r1:latest'
            )
            """
        ),
        {"id": DEEPSEEK_R1_MODEL_ID, "provider_id": OLLAMA_PROVIDER_ID},
    )


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            DELETE FROM llm_models
            WHERE id = :id
              AND provider_id = :provider_id
              AND model_id = 'deepseek-r1:latest'
            """
        ),
        {"id": DEEPSEEK_R1_MODEL_ID, "provider_id": OLLAMA_PROVIDER_ID},
    )
