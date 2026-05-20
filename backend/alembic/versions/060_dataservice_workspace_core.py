"""create DataService workspace core tables

Revision ID: 060_dataservice_workspace_core
Revises: 059_dataservice_operations
Create Date: 2026-05-21 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "060_dataservice_workspace_core"
down_revision: str | None = "059_dataservice_operations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "workspace_settings",
        sa.Column(
            "settings_json",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )

    op.create_table(
        "workspace_memberships",
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("role", sa.String(length=32), server_default="owner", nullable=False),
        sa.Column("status", sa.String(length=32), server_default="active", nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "user_id", name="uq_workspace_memberships_workspace_user"),
    )
    op.create_index("ix_workspace_memberships_user_status", "workspace_memberships", ["user_id", "status"], unique=False)
    op.create_index("ix_workspace_memberships_workspace_role", "workspace_memberships", ["workspace_id", "role"], unique=False)

    op.execute(
        """
        insert into workspace_settings (
            workspace_id,
            default_model,
            thinking_enabled,
            sandbox_provider,
            auto_compact_threshold,
            capability_overrides,
            metadata_json,
            settings_json,
            created_at,
            updated_at
        )
        select
            w.id,
            null,
            true,
            'local',
            0.8,
            '{}'::jsonb,
            '{}'::jsonb,
            coalesce(w.config, '{}'::jsonb),
            now(),
            now()
        from workspaces w
        left join workspace_settings ws on ws.workspace_id = w.id
        where ws.workspace_id is null
        """
    )
    op.execute(
        """
        update workspace_settings ws
        set settings_json = coalesce(w.config, '{}'::jsonb),
            updated_at = now()
        from workspaces w
        where ws.workspace_id = w.id
        """
    )
    membership_table = sa.table(
        "workspace_memberships",
        sa.column("id", sa.String(length=36)),
        sa.column("workspace_id", sa.String(length=36)),
        sa.column("user_id", sa.String(length=36)),
        sa.column("role", sa.String(length=32)),
        sa.column("status", sa.String(length=32)),
    )
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            """
            select id, user_id
            from workspaces
            where user_id is not null
            """
        )
    ).mappings()
    memberships = [
        {
            "id": str(uuid4()),
            "workspace_id": str(row["id"]),
            "user_id": str(row["user_id"]),
            "role": "owner",
            "status": "active",
        }
        for row in rows
    ]
    if memberships:
        op.bulk_insert(membership_table, memberships)


def downgrade() -> None:
    op.drop_index("ix_workspace_memberships_workspace_role", table_name="workspace_memberships")
    op.drop_index("ix_workspace_memberships_user_status", table_name="workspace_memberships")
    op.drop_table("workspace_memberships")
    op.drop_column("workspace_settings", "settings_json")
