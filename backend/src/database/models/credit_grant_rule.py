"""CreditGrantRule ORM model — admin-configured auto-grant rules."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, UUIDMixin


class CreditGrantRuleType(StrEnum):
    REGISTRATION_BONUS = "registration_bonus"
    REFERRAL_REFERRER = "referral_referrer"
    REFERRAL_REFERRED = "referral_referred"
    PERIODIC = "periodic"


class CreditGrantRule(Base, UUIDMixin):
    __tablename__ = "credit_grant_rules"
    __table_args__ = (Index("idx_credit_grant_rules_type_enabled", "rule_type", "enabled"),)

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    rule_type: Mapped[CreditGrantRuleType] = mapped_column(
        SQLEnum(
            CreditGrantRuleType,
            values_callable=lambda enum_cls: [m.value for m in enum_cls],
            name="credit_grant_rule_type",
        ),
        nullable=False,
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    last_triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    created_by_admin_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
