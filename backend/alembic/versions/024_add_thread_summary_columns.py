"""add denormalized thread summary columns

Revision ID: 024_add_thread_summary_columns
Revises: 023_rename_chat_threads_table_to_threads
Create Date: 2026-04-14
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "024_add_thread_summary_columns"
down_revision: str | None = "023_rename_chat_threads_table_to_threads"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _truncate_preview(content: object, limit: int = 120) -> str | None:
    text = str(content or "").strip()
    if not text:
        return None
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3].rstrip() + "..."


def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())
    if table_name not in table_names:
        return False
    columns = {item["name"] for item in inspector.get_columns(table_name)}
    return column_name in columns


def _has_index(table_name: str, index_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    table_names = set(inspector.get_table_names())
    if table_name not in table_names:
        return False
    indexes = {item["name"] for item in inspector.get_indexes(table_name)}
    return index_name in indexes


def upgrade() -> None:
    """Add denormalized summary fields used by thread listing surfaces."""
    if not _has_column("threads", "message_count"):
        op.add_column(
            "threads",
            sa.Column(
                "message_count",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
        )
    if not _has_column("threads", "last_message_preview"):
        op.add_column(
            "threads",
            sa.Column(
                "last_message_preview",
                sa.String(length=255),
                nullable=True,
            ),
        )
    if not _has_column("threads", "last_message_role"):
        op.add_column(
            "threads",
            sa.Column(
                "last_message_role",
                sa.String(length=32),
                nullable=True,
            ),
        )
    if not _has_index("threads", "ix_threads_user_workspace_updated"):
        op.create_index(
            "ix_threads_user_workspace_updated",
            "threads",
            ["user_id", "workspace_id", "updated_at"],
        )

    bind = op.get_bind()
    threads = sa.table(
        "threads",
        sa.column("id", sa.String()),
        sa.column("messages", sa.JSON()),
        sa.column("message_count", sa.Integer()),
        sa.column("last_message_preview", sa.String(length=255)),
        sa.column("last_message_role", sa.String(length=32)),
    )
    rows = bind.execute(
        sa.select(
            threads.c.id,
            threads.c.messages,
        )
    ).mappings()
    for row in rows:
        raw_messages = row.get("messages")
        messages = raw_messages if isinstance(raw_messages, list) else []
        last_message = messages[-1] if messages else {}
        content = last_message.get("content") if isinstance(last_message, dict) else None
        role = last_message.get("role") if isinstance(last_message, dict) else None
        bind.execute(
            sa.update(threads)
            .where(threads.c.id == row["id"])
            .values(
                message_count=len(messages),
                last_message_preview=_truncate_preview(content),
                last_message_role=str(role).strip() or None if role is not None else None,
            )
        )


def downgrade() -> None:
    """Remove denormalized summary fields from threads."""
    if _has_index("threads", "ix_threads_user_workspace_updated"):
        op.drop_index("ix_threads_user_workspace_updated", table_name="threads")
    if _has_column("threads", "last_message_role"):
        op.drop_column("threads", "last_message_role")
    if _has_column("threads", "last_message_preview"):
        op.drop_column("threads", "last_message_preview")
    if _has_column("threads", "message_count"):
        op.drop_column("threads", "message_count")
