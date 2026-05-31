"""workspace sandbox convergence

Revision ID: 079_workspace_sandbox_convergence
Revises: 078_model_catalog_image_category
Create Date: 2026-05-31
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "079_workspace_sandbox_convergence"
down_revision: str | None = "078_model_catalog_image_category"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _json_type() -> sa.types.TypeEngine:
    return postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.add_column(
        "sandbox_job_records",
        sa.Column("operation", sa.String(length=50), server_default="run_python", nullable=False),
    )
    op.add_column(
        "sandbox_job_records",
        sa.Column("billable", sa.Boolean(), server_default=sa.true(), nullable=False),
    )
    op.create_table(
        "sandbox_leases",
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("sandbox_environment_id", sa.String(length=36), nullable=True),
        sa.Column("holder_job_id", sa.String(length=36), nullable=False),
        sa.Column("holder_execution_id", sa.String(length=36), nullable=True),
        sa.Column("lease_token", sa.String(length=100), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata_json", _json_type(), server_default="{}", nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sandbox_environment_id"], ["sandbox_environments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("uq_sandbox_leases_workspace", "sandbox_leases", ["workspace_id"], unique=True)
    op.create_index("ix_sandbox_leases_expires_at", "sandbox_leases", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_sandbox_leases_expires_at", table_name="sandbox_leases")
    op.drop_index("uq_sandbox_leases_workspace", table_name="sandbox_leases")
    op.drop_table("sandbox_leases")
    op.drop_column("sandbox_job_records", "billable")
    op.drop_column("sandbox_job_records", "operation")
