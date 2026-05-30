"""Pricing policy repository placeholder for CRUD-backed policies."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession


class PricingPolicyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
