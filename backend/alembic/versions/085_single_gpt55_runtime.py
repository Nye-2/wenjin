"""converge the LLM catalog on GPT-5.5

Revision ID: 085_single_gpt55_runtime
Revises: 084_gpt55_tool_support
Create Date: 2026-07-10
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "085_single_gpt55_runtime"
down_revision: str | None = "084_gpt55_tool_support"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE model_catalog_entries
        SET is_default = false,
            updated_at = now()
        WHERE category = 'llm'
          AND model_id <> 'gpt-5.5'
          AND is_default = true
          AND EXISTS (
              SELECT 1
              FROM model_catalog_entries
              WHERE model_id = 'gpt-5.5'
                AND category = 'llm'
          )
        """
    )
    op.execute(
        """
        UPDATE model_catalog_entries
        SET enabled = true,
            is_default = true,
            display_name = 'GPT-5.5',
            provider_protocol = 'openai_compatible',
            provider_name = 'OpenAI',
            model_name = 'gpt-5.5',
            base_url = 'https://api.nainai.love/v1',
            supports_streaming = true,
            supports_tools = true,
            supports_reasoning_effort = true,
            max_tokens = 128000,
            temperature = 0.3,
            health_status = 'unknown',
            last_tested_at = NULL,
            last_test_error = NULL,
            config_version = config_version + 1,
            updated_at = now()
        WHERE model_id = 'gpt-5.5'
          AND category = 'llm'
        """
    )
    op.execute(
        """
        DELETE FROM model_catalog_entries
        WHERE category = 'llm'
          AND model_id <> 'gpt-5.5'
          AND EXISTS (
              SELECT 1
              FROM model_catalog_entries
              WHERE model_id = 'gpt-5.5'
                AND category = 'llm'
          )
        """
    )


def downgrade() -> None:
    # Removed catalog secrets cannot be reconstructed by a downgrade.
    pass
