"""Credit models for user balance and transaction history."""

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy import (
    Enum as SQLEnum,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base, UUIDMixin

if TYPE_CHECKING:
    from .user import User


class CreditTransactionType(StrEnum):
    """Supported credit transaction types."""

    ADMIN_GRANT = "admin_grant"
    ADMIN_DEDUCT = "admin_deduct"
    WORKFLOW_CONSUME = "workflow_consume"
    THREAD_TOKEN_CONSUME = "thread_token_consume"
    REGISTRATION_BONUS = "registration_bonus"
    REFUND = "refund"


class CreditTransaction(Base, UUIDMixin):
    """User credit transaction ledger."""

    __tablename__ = "credit_transactions"
    __table_args__ = (
        Index("idx_credit_user_created", "user_id", "created_at"),
        Index("idx_credit_type_created", "transaction_type", "created_at"),
    )

    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    transaction_type: Mapped[CreditTransactionType] = mapped_column(
        SQLEnum(
            CreditTransactionType,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
            name="credit_transaction_type",
        ),
        nullable=False,
        index=True,
    )
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    balance_after: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    feature_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    workspace_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("workspaces.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    task_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    admin_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # Keep DB column name as "metadata" but avoid reserved Declarative attribute name.
    tx_metadata: Mapped[dict] = mapped_column(
        "metadata",
        JSON().with_variant(JSONB, "postgresql"),
        nullable=False,
        default=dict,
        server_default="{}",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )

    user: Mapped["User"] = relationship(
        "User",
        back_populates="credit_transactions",
        foreign_keys=[user_id],
    )
    admin: Mapped["User | None"] = relationship("User", foreign_keys=[admin_id])

    def __repr__(self) -> str:
        return (
            "<CreditTransaction("
            f"id={self.id}, user_id={self.user_id}, type={self.transaction_type}, amount={self.amount}"
            ")>"
        )
