"""CreditRedeemCode ORM model — admin-issued redemption codes."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, UUIDMixin


class CreditRedeemCode(Base, UUIDMixin):
    __tablename__ = "credit_redeem_codes"
    __table_args__ = (Index("idx_redeem_codes_batch", "batch_id"),)

    code: Mapped[str] = mapped_column(String(20), nullable=False, unique=True, index=True)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    max_uses: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    use_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    per_user_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    batch_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    created_by_admin_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
