"""ReferralService — owns invitation relationship + downstream credit firing."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import (
    CreditGrantRuleType,
    CreditTransaction,
    CreditTransactionType,
    Referral,
    User,
)


class ReferralService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def record(self, *, referrer_user_id: str, referee_user_id: str) -> Referral:
        if referrer_user_id == referee_user_id:
            raise ValueError("cannot refer self")
        ref = Referral(referrer_user_id=referrer_user_id, referee_user_id=referee_user_id)
        self.db.add(ref)
        try:
            await self.db.commit()
        except IntegrityError as e:
            await self.db.rollback()
            raise ValueError("referee already has a referrer") from e
        return ref

    async def get_by_referee(self, referee_user_id: str) -> Referral | None:
        result = await self.db.execute(
            select(Referral).where(Referral.referee_user_id == referee_user_id)
        )
        return result.scalars().first()

    async def fire_referee_on_signup(self, referee_user_id: str) -> CreditTransaction | None:
        ref = await self.get_by_referee(referee_user_id)
        if ref is None:
            return None
        from src.services.credit_grant_rule_service import CreditGrantRuleService
        rule_svc = CreditGrantRuleService(self.db)
        rule = await rule_svc.get_active_rule(CreditGrantRuleType.REFERRAL_REFERRED)
        if rule is None:
            return None
        if rule.config.get("trigger") != "on_signup":
            return None
        return await self._grant(
            user_id=referee_user_id, amount=rule.amount,
            description="邀请奖励：作为被邀请者",
            mark_field="referee_credited_at", referral=ref,
        )

    async def fire_first_task_for_referrer(self, referee_user_id: str) -> CreditTransaction | None:
        ref = await self.get_by_referee(referee_user_id)
        if ref is None:
            return None
        if ref.referee_first_task_at is not None:
            return None  # already fired
        ref.referee_first_task_at = datetime.now(UTC)

        from src.services.credit_grant_rule_service import CreditGrantRuleService
        rule_svc = CreditGrantRuleService(self.db)
        rule = await rule_svc.get_active_rule(CreditGrantRuleType.REFERRAL_REFERRER)
        if rule is None:
            return None
        if rule.config.get("trigger") != "on_first_task":
            return None
        return await self._grant(
            user_id=ref.referrer_user_id, amount=rule.amount,
            description=f"邀请奖励：被邀请者 {referee_user_id[:8]}*** 首次完成任务",
            mark_field="referrer_credited_at", referral=ref,
        )

    async def _grant(
        self, *, user_id: str, amount: int, description: str,
        mark_field: str, referral: Referral,
    ) -> CreditTransaction:
        result = await self.db.execute(select(User).where(User.id == user_id))
        user = result.scalars().first()
        if user is None:
            raise ValueError(f"user {user_id} not found")
        user.credits = (user.credits or 0) + amount
        user.total_credits_earned = (user.total_credits_earned or 0) + amount
        txn = CreditTransaction(
            user_id=user_id,
            transaction_type=CreditTransactionType.REFERRAL_BONUS,
            amount=amount,
            balance_after=user.credits,
            description=description,
        )
        self.db.add(txn)
        setattr(referral, mark_field, datetime.now(UTC))
        return txn
