"""task_structural_fields

Revision ID: c41ed149a3b5
Revises: 013_add_chat_token_consume_type
Create Date: 2026-03-28 04:26:17.231566+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c41ed149a3b5'
down_revision: Union[str, None] = '013_add_chat_token_consume_type'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade database schema."""
    op.add_column("task_records", sa.Column("workspace_id", sa.String(), nullable=True))
    op.add_column("task_records", sa.Column("feature_id", sa.String(), nullable=True))
    op.add_column("task_records", sa.Column("thread_id", sa.String(), nullable=True))
    op.add_column("task_records", sa.Column("action", sa.String(), nullable=True))
    op.create_index("ix_task_records_workspace_id", "task_records", ["workspace_id"])
    op.create_index("ix_task_records_feature_id", "task_records", ["feature_id"])
    op.create_index("ix_task_records_thread_id", "task_records", ["thread_id"])
    op.create_index("ix_task_workspace_feature_status", "task_records", ["workspace_id", "feature_id", "status"])


def downgrade() -> None:
    """Downgrade database schema."""
    op.drop_index("ix_task_workspace_feature_status", "task_records")
    op.drop_index("ix_task_records_thread_id", "task_records")
    op.drop_index("ix_task_records_feature_id", "task_records")
    op.drop_index("ix_task_records_workspace_id", "task_records")
    op.drop_column("task_records", "action")
    op.drop_column("task_records", "thread_id")
    op.drop_column("task_records", "feature_id")
    op.drop_column("task_records", "workspace_id")
