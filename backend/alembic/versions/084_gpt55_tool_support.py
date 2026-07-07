"""mark gpt-5.5 as tool capable

Revision ID: 084_gpt55_tool_support
Revises: 083_execution_node_unique_upsert
Create Date: 2026-07-07
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "084_gpt55_tool_support"
down_revision: str | None = "083_execution_node_unique_upsert"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE model_catalog_entries
        SET supports_tools = true,
            updated_at = now()
        WHERE model_id = 'gpt-5.5'
          AND provider_protocol = 'openai_compatible'
          AND enabled = true
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE model_catalog_entries
        SET supports_tools = false,
            updated_at = now()
        WHERE model_id = 'gpt-5.5'
          AND provider_protocol = 'openai_compatible'
        """
    )
