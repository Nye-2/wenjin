"""create DataService conversation block tables

Revision ID: 061_dataservice_conversation_blocks
Revises: 060_dataservice_workspace_core
Create Date: 2026-05-21 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "061_dataservice_conversation_blocks"
down_revision: str | None = "060_dataservice_workspace_core"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CANONICAL_BLOCK_KINDS = (
    "text",
    "thinking",
    "status_line",
    "question_card",
    "result_card",
    "tool_invocation",
    "tool_result",
)


def upgrade() -> None:
    op.create_table(
        "thread_messages",
        sa.Column("thread_id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=True),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("content", sa.Text(), server_default="", nullable=False),
        sa.Column("sequence_index", sa.Integer(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("source_json", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["thread_id"], ["threads.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("thread_id", "sequence_index", name="uq_thread_messages_thread_sequence"),
    )
    op.create_index("ix_thread_messages_thread_sequence", "thread_messages", ["thread_id", "sequence_index"], unique=False)
    op.create_index("ix_thread_messages_workspace_created", "thread_messages", ["workspace_id", "created_at"], unique=False)

    op.create_table(
        "message_blocks",
        sa.Column("message_id", sa.String(length=36), nullable=False),
        sa.Column("thread_id", sa.String(length=36), nullable=False),
        sa.Column("block_type", sa.String(length=32), nullable=False),
        sa.Column("sequence_index", sa.Integer(), nullable=False),
        sa.Column("payload_json", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "block_type in (" + ", ".join(f"'{kind}'" for kind in CANONICAL_BLOCK_KINDS) + ")",
            name="ck_message_blocks_block_type",
        ),
        sa.ForeignKeyConstraint(["message_id"], ["thread_messages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["thread_id"], ["threads.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("message_id", "sequence_index", name="uq_message_blocks_message_sequence"),
    )
    op.create_index("ix_message_blocks_thread_sequence", "message_blocks", ["thread_id", "message_id", "sequence_index"], unique=False)

    op.create_table(
        "tool_invocation_records",
        sa.Column("block_id", sa.String(length=36), nullable=False),
        sa.Column("thread_id", sa.String(length=36), nullable=False),
        sa.Column("message_id", sa.String(length=36), nullable=False),
        sa.Column("invocation_ref", sa.String(length=100), nullable=True),
        sa.Column("tool_name", sa.String(length=200), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=True),
        sa.Column("input_json", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["block_id"], ["message_blocks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["message_id"], ["thread_messages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["thread_id"], ["threads.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("block_id", name="uq_tool_invocation_records_block"),
    )
    op.create_index("ix_tool_invocation_records_thread", "tool_invocation_records", ["thread_id", "created_at"], unique=False)

    op.create_table(
        "tool_result_records",
        sa.Column("block_id", sa.String(length=36), nullable=False),
        sa.Column("thread_id", sa.String(length=36), nullable=False),
        sa.Column("message_id", sa.String(length=36), nullable=False),
        sa.Column("invocation_ref", sa.String(length=100), nullable=True),
        sa.Column("tool_name", sa.String(length=200), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("output_json", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["block_id"], ["message_blocks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["message_id"], ["thread_messages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["thread_id"], ["threads.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("block_id", name="uq_tool_result_records_block"),
    )
    op.create_index("ix_tool_result_records_thread", "tool_result_records", ["thread_id", "created_at"], unique=False)

    _backfill_messages_from_threads()


def downgrade() -> None:
    op.drop_index("ix_tool_result_records_thread", table_name="tool_result_records")
    op.drop_table("tool_result_records")
    op.drop_index("ix_tool_invocation_records_thread", table_name="tool_invocation_records")
    op.drop_table("tool_invocation_records")
    op.drop_index("ix_message_blocks_thread_sequence", table_name="message_blocks")
    op.drop_table("message_blocks")
    op.drop_index("ix_thread_messages_workspace_created", table_name="thread_messages")
    op.drop_index("ix_thread_messages_thread_sequence", table_name="thread_messages")
    op.drop_table("thread_messages")


def _backfill_messages_from_threads() -> None:
    bind = op.get_bind()
    thread_rows = bind.execute(
        sa.text(
            """
            select id, user_id, workspace_id, messages
            from threads
            where messages is not null
            """
        )
    ).mappings()

    thread_message_table = _thread_message_table()
    message_block_table = _message_block_table()
    tool_invocation_table = _tool_invocation_table()
    tool_result_table = _tool_result_table()

    for thread in thread_rows:
        messages = thread["messages"]
        if not isinstance(messages, list):
            continue
        for message_index, message in enumerate(messages):
            if not isinstance(message, Mapping):
                continue
            message_id = str(uuid4())
            bind.execute(
                thread_message_table.insert().values(
                    id=message_id,
                    thread_id=str(thread["id"]),
                    workspace_id=str(thread["workspace_id"]) if thread["workspace_id"] else None,
                    user_id=str(thread["user_id"]),
                    role=str(message.get("role") or ""),
                    content=str(message.get("content") or ""),
                    sequence_index=message_index,
                    timestamp=_coerce_timestamp(message.get("timestamp")),
                    metadata_json=dict(message.get("metadata") or {}) if isinstance(message.get("metadata"), Mapping) else {},
                    source_json=dict(message),
                )
            )
            for block_index, block in enumerate(_blocks_from_message(message)):
                block_id = str(uuid4())
                block_type = _canonical_block_kind(block)
                bind.execute(
                    message_block_table.insert().values(
                        id=block_id,
                        message_id=message_id,
                        thread_id=str(thread["id"]),
                        block_type=block_type,
                        sequence_index=block_index,
                        payload_json=block,
                    )
                )
                if block_type == "tool_invocation":
                    bind.execute(
                        tool_invocation_table.insert().values(
                            id=str(uuid4()),
                            block_id=block_id,
                            thread_id=str(thread["id"]),
                            message_id=message_id,
                            invocation_ref=_first_str(block, "invocation_id", "tool_call_id", "call_id", "id"),
                            tool_name=_first_str(block, "tool_name", "name", "tool", "function_name"),
                            status=_first_str(block, "status"),
                            input_json=_first_mapping(block, "input", "args", "arguments", "parameters"),
                        )
                    )
                elif block_type == "tool_result":
                    bind.execute(
                        tool_result_table.insert().values(
                            id=str(uuid4()),
                            block_id=block_id,
                            thread_id=str(thread["id"]),
                            message_id=message_id,
                            invocation_ref=_first_str(block, "invocation_id", "tool_call_id", "call_id", "id"),
                            tool_name=_first_str(block, "tool_name", "name", "tool", "function_name"),
                            status=_first_str(block, "status"),
                            error=_first_str(block, "error"),
                            output_json=_first_mapping(block, "output", "result", "data"),
                        )
                    )


def _thread_message_table() -> sa.Table:
    return sa.table(
        "thread_messages",
        sa.column("id", sa.String(length=36)),
        sa.column("thread_id", sa.String(length=36)),
        sa.column("workspace_id", sa.String(length=36)),
        sa.column("user_id", sa.String(length=36)),
        sa.column("role", sa.String(length=32)),
        sa.column("content", sa.Text()),
        sa.column("sequence_index", sa.Integer()),
        sa.column("timestamp", sa.DateTime(timezone=True)),
        sa.column("metadata_json", postgresql.JSONB(astext_type=sa.Text())),
        sa.column("source_json", postgresql.JSONB(astext_type=sa.Text())),
    )


def _message_block_table() -> sa.Table:
    return sa.table(
        "message_blocks",
        sa.column("id", sa.String(length=36)),
        sa.column("message_id", sa.String(length=36)),
        sa.column("thread_id", sa.String(length=36)),
        sa.column("block_type", sa.String(length=32)),
        sa.column("sequence_index", sa.Integer()),
        sa.column("payload_json", postgresql.JSONB(astext_type=sa.Text())),
    )


def _tool_invocation_table() -> sa.Table:
    return sa.table(
        "tool_invocation_records",
        sa.column("id", sa.String(length=36)),
        sa.column("block_id", sa.String(length=36)),
        sa.column("thread_id", sa.String(length=36)),
        sa.column("message_id", sa.String(length=36)),
        sa.column("invocation_ref", sa.String(length=100)),
        sa.column("tool_name", sa.String(length=200)),
        sa.column("status", sa.String(length=50)),
        sa.column("input_json", postgresql.JSONB(astext_type=sa.Text())),
    )


def _tool_result_table() -> sa.Table:
    return sa.table(
        "tool_result_records",
        sa.column("id", sa.String(length=36)),
        sa.column("block_id", sa.String(length=36)),
        sa.column("thread_id", sa.String(length=36)),
        sa.column("message_id", sa.String(length=36)),
        sa.column("invocation_ref", sa.String(length=100)),
        sa.column("tool_name", sa.String(length=200)),
        sa.column("status", sa.String(length=50)),
        sa.column("error", sa.Text()),
        sa.column("output_json", postgresql.JSONB(astext_type=sa.Text())),
    )


def _canonical_block_kind(block: Mapping[str, object]) -> str:
    raw_kind = str(block.get("kind") or block.get("type") or "").strip()
    if raw_kind in CANONICAL_BLOCK_KINDS:
        return raw_kind
    if raw_kind in {"reasoning", "thought"}:
        return "thinking"
    if raw_kind in {"tool", "tool_call", "tool_use"}:
        return "tool_invocation"
    return "text"


def _normalize_block(block: Mapping[str, object], *, default_text: str | None = None) -> dict[str, object]:
    payload = dict(block)
    kind = _canonical_block_kind(payload)
    previous_kind = payload.get("kind") or payload.get("type")
    payload["kind"] = kind
    payload.pop("type", None)
    if previous_kind and str(previous_kind) != kind:
        payload.setdefault("legacy_kind", str(previous_kind))
    if kind == "text" and "content" not in payload and default_text:
        payload["content"] = default_text
    return payload


def _blocks_from_message(message: Mapping[str, object]) -> list[dict[str, object]]:
    raw_blocks = message.get("blocks")
    if isinstance(raw_blocks, list):
        blocks = [
            _normalize_block(block)
            for block in raw_blocks
            if isinstance(block, Mapping)
        ]
        if blocks:
            return blocks
    content = message.get("content")
    if isinstance(content, str) and content.strip():
        return [_normalize_block({"kind": "text", "content": content}, default_text=content)]
    return []


def _coerce_timestamp(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _first_str(payload: Mapping[str, object], *keys: str) -> str | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _first_mapping(payload: Mapping[str, object], *keys: str) -> dict[str, object]:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, Mapping):
            return dict(value)
        if value is not None:
            return {"value": value}
    return {}
