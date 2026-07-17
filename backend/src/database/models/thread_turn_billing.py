"""Durable financial authorization for one transient chat turn."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.contracts.billing import ThreadTurnBillingStatus
from src.database.base import Base, TimestampMixin, UUIDMixin


class ThreadTurnBilling(Base, UUIDMixin, TimestampMixin):
    """One bounded credit/free-token hold anchored to a user message."""

    __tablename__ = "thread_turn_billings"
    __table_args__ = (
        CheckConstraint(
            "status IN ('authorized', 'settled', 'released', 'expired')",
            name="ck_thread_turn_billings_status",
        ),
        CheckConstraint(
            "reserved_credits >= 0 AND settled_credits >= 0 "
            "AND reserved_free_tokens >= 0 "
            "AND settled_credits <= reserved_credits",
            name="ck_thread_turn_billings_nonnegative_money",
        ),
        CheckConstraint(
            "input_tokens >= 0 AND cached_input_tokens >= 0 "
            "AND output_tokens >= 0 AND reasoning_tokens >= 0 "
            "AND total_tokens >= 0 "
            "AND cached_input_tokens <= input_tokens "
            "AND reasoning_tokens <= output_tokens "
            "AND total_tokens >= input_tokens + output_tokens",
            name="ck_thread_turn_billings_nonnegative_usage",
        ),
        CheckConstraint(
            "(status = 'authorized' AND settled_at IS NULL AND released_at IS NULL) "
            "OR (status = 'settled' AND settled_at IS NOT NULL AND released_at IS NULL) "
            "OR (status IN ('released', 'expired') AND settled_at IS NULL "
            "AND released_at IS NOT NULL)",
            name="ck_thread_turn_billings_state_timestamps",
        ),
        CheckConstraint(
            "(status = 'settled' AND total_tokens > 0) "
            "OR (status <> 'settled' AND input_tokens = 0 "
            "AND cached_input_tokens = 0 AND output_tokens = 0 "
            "AND reasoning_tokens = 0 AND total_tokens = 0)",
            name="ck_thread_turn_billings_usage_state",
        ),
        CheckConstraint(
            "(status = 'settled' AND transaction_id IS NOT NULL) "
            "OR (status <> 'settled' AND transaction_id IS NULL)",
            name="ck_thread_turn_billings_transaction_state",
        ),
        Index("ix_thread_turn_billings_user_id", "user_id"),
        Index("ix_thread_turn_billings_thread_id", "thread_id"),
        Index("ix_thread_turn_billings_workspace_id", "workspace_id"),
        Index(
            "ix_thread_turn_billings_authorized_expiry",
            "expires_at",
            "id",
            postgresql_where=text("status = 'authorized'"),
            sqlite_where=text("status = 'authorized'"),
        ),
    )

    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    workspace_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="SET NULL"),
        nullable=True,
    )
    thread_id: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
    )
    user_message_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("thread_messages.id", ondelete="SET NULL"),
        nullable=True,
        unique=True,
    )
    assistant_message_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("thread_messages.id", ondelete="SET NULL"),
        nullable=True,
        unique=True,
    )
    idempotency_key: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        unique=True,
    )
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    model_id: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=ThreadTurnBillingStatus.AUTHORIZED.value,
        server_default=ThreadTurnBillingStatus.AUTHORIZED.value,
    )
    reserved_credits: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    reserved_free_tokens: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
        server_default="0",
    )
    settled_credits: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    input_tokens: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0"
    )
    cached_input_tokens: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0"
    )
    output_tokens: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0"
    )
    reasoning_tokens: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0"
    )
    total_tokens: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0"
    )
    pricing_snapshot_json: Mapped[dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
        default=dict,
        server_default="{}",
    )
    transaction_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("credit_transactions.id", ondelete="RESTRICT"),
        nullable=True,
        unique=True,
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    settled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    released_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    release_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


__all__ = ["ThreadTurnBilling"]
