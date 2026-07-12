"""Credit reservations for pre-authorized billable work."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base, TimestampMixin, UUIDMixin


class CreditReservationScope(StrEnum):
    """Billable surfaces that can reserve credits."""

    MISSION = "mission"
    SANDBOX_OPERATION = "sandbox_operation"
    THREAD_TURN = "thread_turn"


class CreditReservationStatus(StrEnum):
    """Reservation lifecycle state."""

    RESERVED = "reserved"
    SETTLED = "settled"
    RELEASED = "released"
    EXPIRED = "expired"


class CreditReservation(Base, UUIDMixin, TimestampMixin):
    """Pre-authorization for long-running or resource-backed work."""

    __tablename__ = "credit_reservations"
    __table_args__ = (
        Index("ix_credit_reservations_user_status", "user_id", "status"),
        Index("ix_credit_reservations_mission", "mission_id"),
        Index("ix_credit_reservations_idempotency", "user_id", "scope", "idempotency_key", unique=True),
    )

    user_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    workspace_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    mission_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("mission_runs.mission_id", ondelete="SET NULL"),
        nullable=True,
    )
    mission_item_seq: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    scope: Mapped[CreditReservationScope] = mapped_column(
        SQLEnum(
            CreditReservationScope,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
            name="credit_reservation_scope",
        ),
        nullable=False,
    )
    status: Mapped[CreditReservationStatus] = mapped_column(
        SQLEnum(
            CreditReservationStatus,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
            name="credit_reservation_status",
        ),
        nullable=False,
        default=CreditReservationStatus.RESERVED,
        server_default=CreditReservationStatus.RESERVED.value,
    )
    reserved_credits: Mapped[int] = mapped_column(Integer, nullable=False)
    settled_credits: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    transaction_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(240), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict, server_default="{}")

    def __repr__(self) -> str:
        return f"<CreditReservation(id={self.id!r}, scope={self.scope!r}, status={self.status!r})>"
