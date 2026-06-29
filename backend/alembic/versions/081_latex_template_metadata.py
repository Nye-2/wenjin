"""add latex template metadata

Revision ID: 081_latex_template_metadata
Revises: 080_skill_execution_strategy_defaults
Create Date: 2026-06-29
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "081_latex_template_metadata"
down_revision: str | None = "080_skill_execution_strategy_defaults"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _json_type() -> sa.types.TypeEngine:
    return postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.add_column(
        "latex_templates",
        sa.Column(
            "metadata_json",
            _json_type(),
            server_default="{}",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("latex_templates", "metadata_json")
