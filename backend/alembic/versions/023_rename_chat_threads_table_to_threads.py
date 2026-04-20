"""rename chat_threads table to threads

Revision ID: 023_rename_chat_threads_table_to_threads
Revises: 022_rename_chat_credit_types_to_thread
Create Date: 2026-04-14
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "023_rename_chat_threads_table_to_threads"
down_revision: str | None = "022_rename_chat_credit_types_to_thread"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _rename_indexes(
    table_name: str,
    *,
    old_to_new: dict[str, str],
) -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())
    if table_name not in table_names:
        return
    index_names = {item["name"] for item in inspector.get_indexes(table_name)}
    for old_name, new_name in old_to_new.items():
        if old_name in index_names and new_name not in index_names:
            op.drop_index(old_name, table_name=table_name)
            if new_name == "ix_threads_user_updated":
                op.create_index(new_name, table_name, ["user_id", "updated_at"])
            elif new_name == "ix_threads_user_id":
                op.create_index(new_name, table_name, ["user_id"])
            elif new_name == "ix_threads_workspace_id":
                op.create_index(new_name, table_name, ["workspace_id"])


def upgrade() -> None:
    """Rename persisted thread table/indexes from chat to thread semantics."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    if "chat_threads" in table_names and "threads" not in table_names:
        op.rename_table("chat_threads", "threads")

    _rename_indexes(
        "threads",
        old_to_new={
            "ix_chat_threads_user_id": "ix_threads_user_id",
            "ix_chat_threads_workspace_id": "ix_threads_workspace_id",
            "ix_chat_threads_user_updated": "ix_threads_user_updated",
        },
    )


def downgrade() -> None:
    """Restore chat_threads naming for table/indexes."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())

    if "threads" in table_names and "chat_threads" not in table_names:
        op.rename_table("threads", "chat_threads")

    _rename_indexes(
        "chat_threads",
        old_to_new={
            "ix_threads_user_id": "ix_chat_threads_user_id",
            "ix_threads_workspace_id": "ix_chat_threads_workspace_id",
            "ix_threads_user_updated": "ix_chat_threads_user_updated",
        },
    )
