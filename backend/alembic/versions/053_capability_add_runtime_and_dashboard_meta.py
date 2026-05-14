"""Add runtime + dashboard_meta JSONB columns to capabilities.

Revision ID: 053_capability_add_runtime_and_dashboard_meta
Revises: 050_capability_drop_result_card_template
Create Date: 2026-05-21
"""

from __future__ import annotations
from collections.abc import Sequence
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "053_capability_add_runtime_and_dashboard_meta"
down_revision: str | None = "050_capability_drop_result_card_template"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("capabilities", sa.Column(
        "runtime", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
    ))
    op.add_column("capabilities", sa.Column(
        "dashboard_meta", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
    ))


def downgrade() -> None:
    op.drop_column("capabilities", "dashboard_meta")
    op.drop_column("capabilities", "runtime")
