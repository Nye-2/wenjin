"""Credit repository."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.credit import CreditTransaction, CreditTransactionType
from src.database.models.credit_grant_rule import CreditGrantRule, CreditGrantRuleType
from src.database.models.credit_redeem_code import CreditRedeemCode
from src.database.models.credit_redemption import CreditRedemption
from src.database.models.credit_reservation import (
    CreditReservation,
    CreditReservationScope,
    CreditReservationStatus,
)
from src.database.models.referral import Referral
from src.database.models.user import User


class CreditRepository:
    """DataService-owned persistence operations for credit tables."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_grant_rules(self) -> list[CreditGrantRule]:
        result = await self.session.execute(
            select(CreditGrantRule).order_by(CreditGrantRule.created_at)
        )
        return list(result.scalars().all())

    async def get_grant_rule(self, rule_id: str) -> CreditGrantRule | None:
        result = await self.session.execute(
            select(CreditGrantRule).where(CreditGrantRule.id == rule_id)
        )
        return result.scalars().first()

    def create_grant_rule(self, values: dict[str, Any]) -> CreditGrantRule:
        rule = CreditGrantRule(**values)
        self.session.add(rule)
        return rule

    async def delete_grant_rule(self, rule: CreditGrantRule) -> None:
        await self.session.delete(rule)

    async def get_active_grant_rule(
        self,
        rule_type: CreditGrantRuleType,
    ) -> CreditGrantRule | None:
        result = await self.session.execute(
            select(CreditGrantRule)
            .where(CreditGrantRule.rule_type == rule_type)
            .where(CreditGrantRule.enabled == True)  # noqa: E712
            .order_by(CreditGrantRule.created_at)
        )
        return result.scalars().first()

    async def list_enabled_grant_rules(
        self,
        rule_type: CreditGrantRuleType,
    ) -> list[CreditGrantRule]:
        result = await self.session.execute(
            select(CreditGrantRule)
            .where(CreditGrantRule.rule_type == rule_type)
            .where(CreditGrantRule.enabled == True)  # noqa: E712
        )
        return list(result.scalars().all())

    async def get_user_for_update(self, user_id: str) -> User | None:
        result = await self.session.execute(
            select(User).where(User.id == user_id).with_for_update()
        )
        return result.scalar_one_or_none()

    async def list_users_for_periodic_credit_filter(
        self,
        *,
        active_since: Any | None,
        role: str | None,
    ) -> list[User]:
        stmt = select(User)
        if active_since is not None:
            stmt = stmt.where(User.last_login >= active_since)
        if role == "user":
            stmt = stmt.where(User.is_superuser == False)  # noqa: E712
        elif role == "admin":
            stmt = stmt.where(User.is_superuser == True)  # noqa: E712
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    def create_credit_transaction(self, values: dict[str, Any]) -> CreditTransaction:
        tx = CreditTransaction(**values)
        self.session.add(tx)
        return tx

    def create_credit_reservation(self, values: dict[str, Any]) -> CreditReservation:
        reservation = CreditReservation(**values)
        self.session.add(reservation)
        return reservation

    async def get_reservation_for_update(
        self,
        reservation_id: str,
    ) -> CreditReservation | None:
        result = await self.session.execute(
            select(CreditReservation)
            .where(CreditReservation.id == reservation_id)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def find_reservation_by_idempotency_key(
        self,
        *,
        user_id: str,
        scope: CreditReservationScope,
        idempotency_key: str,
    ) -> CreditReservation | None:
        result = await self.session.execute(
            select(CreditReservation)
            .where(
                CreditReservation.user_id == user_id,
                CreditReservation.scope == scope,
                CreditReservation.idempotency_key == idempotency_key,
            )
            .order_by(CreditReservation.created_at)
        )
        return result.scalars().first()

    async def list_expired_reserved_reservations(
        self,
        *,
        now: datetime,
    ) -> list[CreditReservation]:
        result = await self.session.execute(
            select(CreditReservation)
            .where(
                CreditReservation.status == CreditReservationStatus.RESERVED,
                CreditReservation.expires_at.is_not(None),
                CreditReservation.expires_at <= now,
            )
            .with_for_update()
        )
        return list(result.scalars().all())

    async def get_admin_credit_summary(self) -> dict[str, int]:
        totals_result = await self.session.execute(
            select(
                func.coalesce(func.sum(User.total_credits_earned), 0).label("issued"),
                func.coalesce(func.sum(User.total_credits_spent), 0).label("spent"),
                func.coalesce(func.sum(User.credits), 0).label("pool"),
            )
        )
        totals = totals_result.one()
        overdraft_result = await self.session.execute(
            select(
                func.count().label("users"),
                func.coalesce(func.sum(func.abs(User.credits)), 0).label("credits"),
            ).where(User.credits < 0)
        )
        overdraft = overdraft_result.one()
        manual_deductions = int(
            (
                await self.session.execute(
                    select(func.coalesce(func.sum(func.abs(CreditTransaction.amount)), 0)).where(
                        CreditTransaction.transaction_type == CreditTransactionType.ADMIN_DEDUCT
                    )
                )
            ).scalar()
            or 0
        )
        tx_total = int(
            (
                await self.session.execute(
                    select(func.count()).select_from(CreditTransaction)
                )
            ).scalar()
            or 0
        )
        return {
            "total_issued": int(totals.issued),
            "total_spent": int(totals.spent),
            "in_circulation": int(totals.pool),
            "manual_deductions": manual_deductions,
            "overdraft_users": int(overdraft.users),
            "overdraft_credits_total": int(overdraft.credits),
            "total_transactions": tx_total,
        }

    async def list_thread_token_transactions(self) -> list[CreditTransaction]:
        result = await self.session.execute(
            select(CreditTransaction).where(
                CreditTransaction.transaction_type.in_(
                    [
                        CreditTransactionType.THREAD_TOKEN_CONSUME,
                        CreditTransactionType.REFUND,
                    ]
                )
            )
        )
        return list(result.scalars().all())

    async def aggregate_credit_transactions_by_bucket(
        self,
        *,
        since: Any,
        granularity: str,
    ) -> list[Any]:
        bucket_col = func.date_trunc(granularity, CreditTransaction.created_at).label(
            "bucket"
        )
        ttype_col = CreditTransaction.transaction_type
        result = await self.session.execute(
            select(
                bucket_col,
                ttype_col.label("ttype"),
                func.sum(CreditTransaction.amount).label("total"),
            )
            .where(CreditTransaction.created_at >= since)
            .group_by(bucket_col, ttype_col)
            .order_by(bucket_col)
        )
        return list(result.all())

    async def get_credit_transaction(self, transaction_id: str) -> CreditTransaction | None:
        return await self.session.get(CreditTransaction, transaction_id)

    async def get_user_credit_balance(self, user_id: str) -> int | None:
        result = await self.session.execute(select(User.credits).where(User.id == user_id))
        balance = result.scalar_one_or_none()
        return int(balance) if balance is not None else None

    async def get_user(self, user_id: str) -> User | None:
        return await self.session.get(User, user_id)

    async def list_credit_transactions(
        self,
        *,
        user_id: str | None = None,
        transaction_type: CreditTransactionType | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[CreditTransaction], int]:
        base_query = select(CreditTransaction)
        if user_id:
            base_query = base_query.where(CreditTransaction.user_id == user_id)
        if transaction_type:
            base_query = base_query.where(CreditTransaction.transaction_type == transaction_type)
        count_query = select(func.count()).select_from(base_query.subquery())
        total = int((await self.session.execute(count_query)).scalar() or 0)
        result = await self.session.execute(
            base_query
            .order_by(desc(CreditTransaction.created_at))
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all()), total

    async def list_token_accounting_transactions(
        self,
        *,
        user_id: str,
        consume_type: CreditTransactionType,
    ) -> list[CreditTransaction]:
        result = await self.session.execute(
            select(CreditTransaction).where(
                CreditTransaction.user_id == user_id,
                CreditTransaction.transaction_type.in_(
                    [
                        consume_type,
                        CreditTransactionType.REFUND,
                    ]
                ),
            )
        )
        return list(result.scalars().all())

    async def find_refund_for_original(
        self,
        *,
        user_id: str,
        original_transaction_id: str,
    ) -> CreditTransaction | None:
        result = await self.session.execute(
            select(CreditTransaction).where(
                CreditTransaction.user_id == user_id,
                CreditTransaction.transaction_type == CreditTransactionType.REFUND,
                CreditTransaction.tx_metadata["original_transaction_id"].as_string()
                == original_transaction_id,
            )
        )
        return result.scalar_one_or_none()

    async def find_consumption_by_idempotency_key(
        self,
        *,
        user_id: str,
        transaction_type: CreditTransactionType,
        idempotency_key: str,
    ) -> CreditTransaction | None:
        result = await self.session.execute(
            select(CreditTransaction)
            .where(
                CreditTransaction.user_id == user_id,
                CreditTransaction.transaction_type == transaction_type,
                CreditTransaction.tx_metadata["idempotency_key"].as_string()
                == idempotency_key,
            )
            .order_by(CreditTransaction.created_at)
        )
        return result.scalars().first()

    def create_redeem_code(self, values: dict[str, Any]) -> CreditRedeemCode:
        code = CreditRedeemCode(**values)
        self.session.add(code)
        return code

    async def list_redeem_codes(
        self,
        *,
        batch_id: str | None = None,
        enabled: bool | None = None,
        keyword: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[CreditRedeemCode]:
        stmt = select(CreditRedeemCode).order_by(CreditRedeemCode.created_at.desc())
        if batch_id:
            stmt = stmt.where(CreditRedeemCode.batch_id == batch_id)
        if enabled is not None:
            stmt = stmt.where(CreditRedeemCode.enabled == enabled)
        if keyword:
            stmt = stmt.where(CreditRedeemCode.code.ilike(f"%{keyword}%"))
        result = await self.session.execute(stmt.limit(limit).offset(offset))
        return list(result.scalars().all())

    async def get_redeem_code(self, code_id: str) -> CreditRedeemCode | None:
        result = await self.session.execute(
            select(CreditRedeemCode).where(CreditRedeemCode.id == code_id)
        )
        return result.scalars().first()

    async def get_redeem_code_for_update(self, code: str) -> CreditRedeemCode | None:
        result = await self.session.execute(
            select(CreditRedeemCode)
            .where(CreditRedeemCode.code == code)
            .with_for_update()
        )
        return result.scalars().first()

    async def count_redemptions_for_user(
        self,
        *,
        code_id: str,
        user_id: str,
    ) -> int:
        result = await self.session.execute(
            select(func.count())
            .select_from(CreditRedemption)
            .where(CreditRedemption.code_id == code_id)
            .where(CreditRedemption.user_id == user_id)
        )
        return int(result.scalar_one())

    def create_redemption(self, values: dict[str, Any]) -> CreditRedemption:
        redemption = CreditRedemption(**values)
        self.session.add(redemption)
        return redemption

    def create_referral(self, values: dict[str, Any]) -> Referral:
        referral = Referral(**values)
        self.session.add(referral)
        return referral

    async def get_referral_by_referee(self, referee_user_id: str) -> Referral | None:
        result = await self.session.execute(
            select(Referral).where(Referral.referee_user_id == referee_user_id)
        )
        return result.scalars().first()


__all__ = [
    "CreditGrantRuleType",
    "CreditRepository",
    "CreditTransactionType",
]
