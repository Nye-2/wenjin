"""enforce one primary workspace Prism project

Revision ID: 057_workspace_prism_primary_unique
Revises: 056_workspace_prism_surface_binding
Create Date: 2026-05-20 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "057_workspace_prism_primary_unique"
down_revision: str | None = "056_workspace_prism_surface_binding"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        with ranked_primary as (
            select
                id,
                row_number() over (
                    partition by workspace_id
                    order by updated_at desc, id desc
                ) as rank
            from latex_projects
            where workspace_id is not null
              and surface_role = 'primary_manuscript'
        )
        update latex_projects
        set surface_role = null
        where id in (
            select id
            from ranked_primary
            where rank > 1
        )
        """
    )
    op.drop_index("ix_latex_projects_workspace_surface_role", table_name="latex_projects")
    op.create_index(
        "uq_latex_projects_workspace_primary_manuscript",
        "latex_projects",
        ["workspace_id"],
        unique=True,
        postgresql_where=sa.text("surface_role = 'primary_manuscript'"),
        sqlite_where=sa.text("surface_role = 'primary_manuscript'"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_latex_projects_workspace_primary_manuscript",
        table_name="latex_projects",
    )
    op.create_index(
        "ix_latex_projects_workspace_surface_role",
        "latex_projects",
        ["workspace_id", "surface_role"],
        unique=False,
    )
