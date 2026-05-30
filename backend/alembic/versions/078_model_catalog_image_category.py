"""add image category to model catalog

Revision ID: 078_model_catalog_image_category
Revises: 077_model_catalog_pricing_reservations
Create Date: 2026-05-30
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "078_model_catalog_image_category"
down_revision: str | None = "077_model_catalog_pricing_reservations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE model_category ADD VALUE IF NOT EXISTS 'image'")


def downgrade() -> None:
    # PostgreSQL enum value removal is destructive; keep existing values.
    pass
