"""Persistence operations for chat-turn billing authorizations."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.thread_turn_billing import ThreadTurnBilling


class ThreadTurnBillingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def database_now(self) -> datetime:
        value = (await self.session.execute(select(func.now()))).scalar_one()
        return value

    def create(self, values: dict[str, Any]) -> ThreadTurnBilling:
        billing = ThreadTurnBilling(**values)
        self.session.add(billing)
        return billing

    async def get_for_update(
        self,
        billing_id: str,
    ) -> ThreadTurnBilling | None:
        result = await self.session.execute(
            select(ThreadTurnBilling)
            .where(ThreadTurnBilling.id == billing_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def get_by_idempotency_key_for_update(
        self,
        idempotency_key: str,
    ) -> ThreadTurnBilling | None:
        result = await self.session.execute(
            select(ThreadTurnBilling)
            .where(ThreadTurnBilling.idempotency_key == idempotency_key)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def list_expired_authorizations(
        self,
        *,
        now: datetime,
        limit: int,
    ) -> list[tuple[str, str]]:
        result = await self.session.execute(
            select(ThreadTurnBilling.id, ThreadTurnBilling.user_id)
            .where(
                ThreadTurnBilling.status == "authorized",
                ThreadTurnBilling.expires_at <= now,
            )
            .order_by(ThreadTurnBilling.expires_at, ThreadTurnBilling.id)
            .limit(limit)
        )
        return [(str(row.id), str(row.user_id)) for row in result]

    async def list_authorized_for_thread_for_update(
        self,
        thread_id: str,
    ) -> list[ThreadTurnBilling]:
        result = await self.session.execute(
            select(ThreadTurnBilling)
            .where(
                ThreadTurnBilling.thread_id == thread_id,
                ThreadTurnBilling.status == "authorized",
            )
            .order_by(ThreadTurnBilling.id)
            .with_for_update()
        )
        return list(result.scalars().all())

    async def list_expired_for_user_for_update(
        self,
        *,
        user_id: str,
        billing_ids: list[str],
        now: datetime,
    ) -> list[ThreadTurnBilling]:
        if not billing_ids:
            return []
        result = await self.session.execute(
            select(ThreadTurnBilling)
            .where(
                ThreadTurnBilling.id.in_(billing_ids),
                ThreadTurnBilling.user_id == user_id,
                ThreadTurnBilling.status == "authorized",
                ThreadTurnBilling.expires_at <= now,
            )
            .order_by(ThreadTurnBilling.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return list(result.scalars().all())


__all__ = ["ThreadTurnBillingRepository"]
