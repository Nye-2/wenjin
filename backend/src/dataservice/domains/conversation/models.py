"""Conversation storage models owned by DataService."""

from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.database.base import Base, TimestampMixin, UUIDMixin
from src.dataservice.domains.conversation.block_protocol import CANONICAL_BLOCK_KINDS

CONVERSATION_JSON_TYPE = JSON().with_variant(JSONB, "postgresql")

CONVERSATION_JSON_DEFAULT = "'{}'"


class ThreadMessage(Base, UUIDMixin, TimestampMixin):
    """Canonical message row for a persisted thread."""

    __tablename__ = "thread_messages"
    __table_args__ = (
        UniqueConstraint("thread_id", "sequence_index", name="uq_thread_messages_thread_sequence"),
        Index("ix_thread_messages_thread_sequence", "thread_id", "sequence_index"),
        Index("ix_thread_messages_workspace_created", "workspace_id", "created_at"),
    )

    thread_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("threads.id", ondelete="CASCADE"),
        nullable=False,
    )
    workspace_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="SET NULL"),
        nullable=True,
    )
    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    sequence_index: Mapped[int] = mapped_column(Integer, nullable=False)
    timestamp: Mapped[Any | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(
        CONVERSATION_JSON_TYPE,
        nullable=False,
        default=dict,
        server_default=CONVERSATION_JSON_DEFAULT,
    )
    source_json: Mapped[dict[str, Any]] = mapped_column(
        CONVERSATION_JSON_TYPE,
        nullable=False,
        default=dict,
        server_default=CONVERSATION_JSON_DEFAULT,
    )


class MessageBlock(Base, UUIDMixin, TimestampMixin):
    """Canonical ordered UI/protocol block for a thread message."""

    __tablename__ = "message_blocks"
    __table_args__ = (
        UniqueConstraint("message_id", "sequence_index", name="uq_message_blocks_message_sequence"),
        Index("ix_message_blocks_thread_sequence", "thread_id", "message_id", "sequence_index"),
        CheckConstraint(
            "block_type in (" + ", ".join(f"'{kind}'" for kind in CANONICAL_BLOCK_KINDS) + ")",
            name="ck_message_blocks_block_type",
        ),
    )

    message_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("thread_messages.id", ondelete="CASCADE"),
        nullable=False,
    )
    thread_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("threads.id", ondelete="CASCADE"),
        nullable=False,
    )
    block_type: Mapped[str] = mapped_column(String(32), nullable=False)
    sequence_index: Mapped[int] = mapped_column(Integer, nullable=False)
    payload_json: Mapped[dict[str, Any]] = mapped_column(
        CONVERSATION_JSON_TYPE,
        nullable=False,
        default=dict,
        server_default=CONVERSATION_JSON_DEFAULT,
    )


class ToolInvocationRecord(Base, UUIDMixin, TimestampMixin):
    """Tool invocation metadata extracted from a canonical block."""

    __tablename__ = "tool_invocation_records"
    __table_args__ = (
        UniqueConstraint("block_id", name="uq_tool_invocation_records_block"),
        Index("ix_tool_invocation_records_thread", "thread_id", "created_at"),
    )

    block_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("message_blocks.id", ondelete="CASCADE"),
        nullable=False,
    )
    thread_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("threads.id", ondelete="CASCADE"),
        nullable=False,
    )
    message_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("thread_messages.id", ondelete="CASCADE"),
        nullable=False,
    )
    invocation_ref: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tool_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    input_json: Mapped[dict[str, Any]] = mapped_column(
        CONVERSATION_JSON_TYPE,
        nullable=False,
        default=dict,
        server_default=CONVERSATION_JSON_DEFAULT,
    )


class ToolResultRecord(Base, UUIDMixin, TimestampMixin):
    """Tool result metadata extracted from a canonical block."""

    __tablename__ = "tool_result_records"
    __table_args__ = (
        UniqueConstraint("block_id", name="uq_tool_result_records_block"),
        Index("ix_tool_result_records_thread", "thread_id", "created_at"),
    )

    block_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("message_blocks.id", ondelete="CASCADE"),
        nullable=False,
    )
    thread_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("threads.id", ondelete="CASCADE"),
        nullable=False,
    )
    message_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("thread_messages.id", ondelete="CASCADE"),
        nullable=False,
    )
    invocation_ref: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tool_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_json: Mapped[dict[str, Any]] = mapped_column(
        CONVERSATION_JSON_TYPE,
        nullable=False,
        default=dict,
        server_default=CONVERSATION_JSON_DEFAULT,
    )
