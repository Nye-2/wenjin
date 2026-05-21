"""ReferralService facade backed by CreditDataService."""

from __future__ import annotations

from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.dataservice.credit_api import CreditDataService


class ReferralService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self._credit = CreditDataService(db)

    async def record(self, *, referrer_user_id: str, referee_user_id: str) -> Any:
        if referrer_user_id == referee_user_id:
            raise ValueError("cannot refer self")
        try:
            return await self._credit.record_referral(
                referrer_user_id=referrer_user_id,
                referee_user_id=referee_user_id,
            )
        except IntegrityError as exc:
            await self.db.rollback()
            raise ValueError("referee already has a referrer") from exc

    async def get_by_referee(self, referee_user_id: str) -> Any | None:
        return await self._credit.get_referral_by_referee(referee_user_id)

    async def fire_referee_on_signup(self, referee_user_id: str) -> Any | None:
        return await self._credit.apply_referee_signup_bonus(
            referee_user_id=referee_user_id
        )

    async def fire_first_task_for_referrer(self, referee_user_id: str) -> Any | None:
        return await self._credit.apply_referrer_first_task_bonus(
            referee_user_id=referee_user_id
        )
