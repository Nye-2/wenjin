"""Add ui_meta JSONB column to capabilities.

Revision ID: 049_capability_add_ui_meta
Revises: 048_drop_execution_sessions_legacy
Create Date: 2026-05-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "049_capability_add_ui_meta"
down_revision: str | None = "048_drop_execution_sessions_legacy"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "capabilities",
        sa.Column("ui_meta", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )


def downgrade() -> None:
    op.drop_column("capabilities", "ui_meta")
