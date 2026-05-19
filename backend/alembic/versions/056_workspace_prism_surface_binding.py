"""add explicit workspace Prism binding

Revision ID: 056_workspace_prism_surface_binding
Revises: 055_credit_grant_rules_and_redeem_codes
Create Date: 2026-05-19 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "056_workspace_prism_surface_binding"
down_revision: str | None = "055_credit_grant_rules_and_redeem_codes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "latex_projects",
        sa.Column("workspace_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "latex_projects",
        sa.Column("surface_role", sa.String(length=64), nullable=True),
    )
    op.create_foreign_key(
        "fk_latex_projects_workspace_id_workspaces",
        "latex_projects",
        "workspaces",
        ["workspace_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_latex_projects_workspace_id",
        "latex_projects",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        "ix_latex_projects_surface_role",
        "latex_projects",
        ["surface_role"],
        unique=False,
    )
    op.create_index(
        "ix_latex_projects_workspace_surface_role",
        "latex_projects",
        ["workspace_id", "surface_role"],
        unique=False,
    )
    op.execute(
        """
        update latex_projects
        set workspace_id = llm_config->>'workspace_id',
            surface_role = 'primary_manuscript'
        where llm_config is not null
          and llm_config->>'bridge' = 'workspace_latex_project'
          and coalesce(llm_config->>'workspace_id', '') <> ''
        """
    )


def downgrade() -> None:
    op.drop_index("ix_latex_projects_workspace_surface_role", table_name="latex_projects")
    op.drop_index("ix_latex_projects_surface_role", table_name="latex_projects")
    op.drop_index("ix_latex_projects_workspace_id", table_name="latex_projects")
    op.drop_constraint(
        "fk_latex_projects_workspace_id_workspaces",
        "latex_projects",
        type_="foreignkey",
    )
    op.drop_column("latex_projects", "surface_role")
    op.drop_column("latex_projects", "workspace_id")
