"""Pricing policy repository."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.pricing_policy import PricingPolicy


class PricingPolicyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_policies(
        self,
        *,
        policy_kind: str | None = None,
        enabled_only: bool = False,
    ) -> list[PricingPolicy]:
        query = select(PricingPolicy)
        if policy_kind is not None:
            query = query.where(PricingPolicy.policy_kind == policy_kind)
        if enabled_only:
            query = query.where(PricingPolicy.enabled.is_(True))
        result = await self.session.execute(query.order_by(PricingPolicy.policy_kind, PricingPolicy.policy_key))
        return list(result.scalars().all())

    async def get_policy(self, policy_id_or_key: str) -> PricingPolicy | None:
        result = await self.session.execute(
            select(PricingPolicy).where(
                (PricingPolicy.id == policy_id_or_key) | (PricingPolicy.policy_key == policy_id_or_key)
            )
        )
        return result.scalar_one_or_none()

    async def create_policy(self, values: dict[str, Any]) -> PricingPolicy:
        record = PricingPolicy(**values)
        self.session.add(record)
        return record
