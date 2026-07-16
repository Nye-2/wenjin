"""replace obsolete workspace thinking flag with typed reasoning effort

Revision ID: 101_workspace_reasoning_effort_cutover
Revises: 100_review_output_key_cutover
"""

import sqlalchemy as sa

from alembic import op

revision = "101_workspace_reasoning_effort_cutover"
down_revision = "100_review_output_key_cutover"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "workspace_settings",
        sa.Column(
            "reasoning_effort",
            sa.String(length=16),
            nullable=False,
            server_default="xhigh",
        ),
    )
    op.execute(
        """
        UPDATE workspace_settings
        SET reasoning_effort = CASE
            WHEN thinking_enabled THEN 'xhigh'
            ELSE 'low'
        END
        """
    )
    op.create_check_constraint(
        "ck_workspace_settings_reasoning_effort",
        "workspace_settings",
        "reasoning_effort IN ('low', 'medium', 'high', 'xhigh')",
    )
    op.drop_column("workspace_settings", "thinking_enabled")


def downgrade() -> None:
    raise RuntimeError("101 is an irreversible development cutover; reseed instead")
