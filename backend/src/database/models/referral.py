"""Referral ORM model — invitation relationship."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, UUIDMixin


class Referral(Base, UUIDMixin):
    __tablename__ = "referrals"

    referrer_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    referee_user_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    referrer_credited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    referee_credited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    referee_first_task_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
