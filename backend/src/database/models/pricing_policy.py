"""Admin-managed pricing policy models."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from sqlalchemy import Boolean, Index, Integer, String
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, TimestampMixin, UUIDMixin


class PricingPolicyKind(StrEnum):
    """Supported pricing policy kinds."""

    GLOBAL_CREDIT = "global_credit"
    MODEL_USAGE = "model_usage"
    CAPABILITY = "capability"
    TOOL = "tool"
    SANDBOX = "sandbox"


class PricingPolicy(Base, UUIDMixin, TimestampMixin):
    """Typed pricing policy stored as validated JSON config."""

    __tablename__ = "pricing_policies"
    __table_args__ = (
        Index("ix_pricing_policies_kind_enabled", "policy_kind", "enabled"),
    )

    policy_key: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    policy_kind: Mapped[PricingPolicyKind] = mapped_column(
        SQLEnum(
            PricingPolicyKind,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
            name="pricing_policy_kind",
        ),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    config_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")
    created_by_admin_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    updated_by_admin_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    def __repr__(self) -> str:
        return f"<PricingPolicy(policy_key={self.policy_key!r}, kind={self.policy_kind!r})>"
