"""Drop vestigial result_card_template from capabilities.

Field was never consumed end-to-end: frontend ResultCard renders by output.kind,
not template name. See spec §2.2 and decisions table.

Revision ID: 050_capability_drop_result_card_template
Revises: 049_capability_add_ui_meta
Create Date: 2026-05-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "050_capability_drop_result_card_template"
down_revision: str | None = "049_capability_add_ui_meta"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("capabilities", "result_card_template")


def downgrade() -> None:
    op.add_column(
        "capabilities",
        sa.Column("result_card_template", sa.String(length=100), nullable=False, server_default=""),
    )
