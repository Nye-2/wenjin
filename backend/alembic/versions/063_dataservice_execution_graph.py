"""Add DataService execution events.

Revision ID: 063_dataservice_execution_graph
Revises: 062_dataservice_capability_catalog
Create Date: 2026-05-21
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "063_dataservice_execution_graph"
down_revision: str | None = "062_dataservice_capability_catalog"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _json_type() -> sa.types.TypeEngine:
    return postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "execution_events",
        sa.Column("execution_id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=True),
        sa.Column("node_id", sa.String(length=100), nullable=True),
        sa.Column("event_type", sa.String(length=120), nullable=False),
        sa.Column("sequence_index", sa.Integer(), nullable=False),
        sa.Column("payload_json", _json_type(), server_default="{}", nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["execution_id"], ["executions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_execution_events_execution_sequence",
        "execution_events",
        ["execution_id", "sequence_index"],
        unique=True,
    )
    op.create_index(
        "ix_execution_events_workspace_created",
        "execution_events",
        ["workspace_id", "created_at"],
    )
    op.create_index(
        "ix_execution_events_type_created",
        "execution_events",
        ["event_type", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_execution_events_type_created", table_name="execution_events")
    op.drop_index("ix_execution_events_workspace_created", table_name="execution_events")
    op.drop_index("ix_execution_events_execution_sequence", table_name="execution_events")
    op.drop_table("execution_events")
