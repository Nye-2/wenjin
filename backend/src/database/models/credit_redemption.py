"""CreditRedemption ORM model — per-user redemption ledger."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, UUIDMixin


class CreditRedemption(Base, UUIDMixin):
    __tablename__ = "credit_redemptions"
    __table_args__ = (Index("idx_redemption_code_user", "code_id", "user_id"),)

    code_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("credit_redeem_codes.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    transaction_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("credit_transactions.id", ondelete="SET NULL"), nullable=True
    )
    redeemed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
