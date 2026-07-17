"""Credit repository."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.contracts.billing import CreditTransactionType
from src.database.models.credit import CreditTransaction
from src.database.models.credit_grant_rule import CreditGrantRule, CreditGrantRuleType
from src.database.models.credit_redeem_code import CreditRedeemCode
from src.database.models.credit_redemption import CreditRedemption
from src.database.models.credit_reservation import CreditReservation, CreditReservationStatus
from src.database.models.referral import Referral
from src.database.models.user import User


class CreditRepository:
    """DataService-owned persistence operations for credit tables."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def database_now(self) -> datetime:
        return (await self.session.execute(select(func.now()))).scalar_one()

    async def list_grant_rules(self) -> list[CreditGrantRule]:
        result = await self.session.execute(select(CreditGrantRule).order_by(CreditGrantRule.created_at))
        return list(result.scalars().all())

    async def get_grant_rule(self, rule_id: str) -> CreditGrantRule | None:
        result = await self.session.execute(select(CreditGrantRule).where(CreditGrantRule.id == rule_id))
        return result.scalars().first()

    async def get_grant_rule_for_update(
        self,
        rule_id: str,
    ) -> CreditGrantRule | None:
        result = await self.session.execute(
            select(CreditGrantRule)
            .where(CreditGrantRule.id == rule_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

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

    async def get_next_enabled_grant_rule_for_update(
        self,
        rule_type: CreditGrantRuleType,
        *,
        after_rule_id: str | None,
        created_through: datetime,
    ) -> CreditGrantRule | None:
        stmt = select(CreditGrantRule).where(
            CreditGrantRule.rule_type == rule_type,
            CreditGrantRule.enabled == True,  # noqa: E712
            CreditGrantRule.created_at <= created_through,
        )
        if after_rule_id is not None:
            stmt = stmt.where(CreditGrantRule.id > after_rule_id)
        result = await self.session.execute(
            stmt
            .order_by(CreditGrantRule.id)
            .limit(1)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def get_user_for_update(self, user_id: str) -> User | None:
        result = await self.session.execute(select(User).where(User.id == user_id).with_for_update())
        return result.scalar_one_or_none()

    async def list_user_ids_for_periodic_credit_filter(
        self,
        *,
        active_since: Any | None,
        role: str | None,
        created_through: datetime,
        after_user_id: str | None,
        limit: int,
    ) -> list[str]:
        stmt = select(User.id).where(User.created_at <= created_through)
        if active_since is not None:
            stmt = stmt.where(User.last_login >= active_since)
        if role == "user":
            stmt = stmt.where(User.is_superuser == False)  # noqa: E712
        elif role == "admin":
            stmt = stmt.where(User.is_superuser == True)  # noqa: E712
        if after_user_id is not None:
            stmt = stmt.where(User.id > after_user_id)
        result = await self.session.execute(stmt.order_by(User.id).limit(limit))
        return [str(user_id) for user_id in result.scalars().all()]

    async def find_credit_transaction_by_idempotency_key(
        self,
        *,
        user_id: str,
        transaction_type: CreditTransactionType,
        idempotency_key: str,
    ) -> CreditTransaction | None:
        result = await self.session.execute(
            select(CreditTransaction).where(
                CreditTransaction.user_id == user_id,
                CreditTransaction.transaction_type == transaction_type,
                CreditTransaction.idempotency_key == idempotency_key,
            )
        )
        return result.scalar_one_or_none()

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
        result = await self.session.execute(select(CreditReservation).where(CreditReservation.id == reservation_id).with_for_update())
        return result.scalar_one_or_none()

    async def get_mission_reservation_for_update(
        self,
        mission_id: str,
    ) -> CreditReservation | None:
        result = await self.session.execute(
            select(CreditReservation)
            .where(CreditReservation.mission_id == mission_id)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def find_reservation_by_idempotency_key(
        self,
        *,
        idempotency_key: str,
    ) -> CreditReservation | None:
        result = await self.session.execute(
            select(CreditReservation)
            .where(CreditReservation.idempotency_key == idempotency_key)
            .order_by(CreditReservation.created_at)
        )
        return result.scalars().first()

    async def list_expired_mission_reservation_refs(
        self,
        *,
        now: datetime,
        limit: int,
    ) -> list[tuple[str, str]]:
        result = await self.session.execute(
            select(CreditReservation.id, CreditReservation.mission_id)
            .where(
                CreditReservation.status == CreditReservationStatus.RESERVED,
                CreditReservation.expires_at.is_not(None),
                CreditReservation.expires_at <= now,
            )
            .order_by(CreditReservation.expires_at, CreditReservation.id)
            .limit(limit)
        )
        return [(str(row.id), str(row.mission_id)) for row in result]

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
        manual_deductions = int((await self.session.execute(select(func.coalesce(func.sum(func.abs(CreditTransaction.amount)), 0)).where(CreditTransaction.transaction_type == CreditTransactionType.ADMIN_DEDUCT))).scalar() or 0)
        tx_total = int((await self.session.execute(select(func.count()).select_from(CreditTransaction))).scalar() or 0)
        return {
            "total_issued": int(totals.issued),
            "total_spent": int(totals.spent),
            "in_circulation": int(totals.pool),
            "manual_deductions": manual_deductions,
            "overdraft_users": int(overdraft.users),
            "overdraft_credits_total": int(overdraft.credits),
            "total_transactions": tx_total,
        }

    async def get_thread_token_usage_summary(self) -> dict[str, int]:
        usage = (
            await self.session.execute(
                select(
                    func.coalesce(func.sum(User.thread_consumed_tokens), 0),
                    func.count(User.id),
                ).where(User.thread_consumed_tokens > 0)
            )
        ).one()
        transaction_count = int(
            (
                await self.session.execute(
                    select(func.count())
                    .select_from(CreditTransaction)
                    .where(
                        CreditTransaction.transaction_type
                        == CreditTransactionType.THREAD_TOKEN_CONSUME
                    )
                )
            ).scalar_one()
        )
        return {
            "total_tokens": int(usage[0]),
            "transactions": transaction_count,
            "users": int(usage[1]),
        }

    async def aggregate_credit_transactions_by_bucket(
        self,
        *,
        since: Any,
        granularity: str,
    ) -> list[Any]:
        bucket_col = func.date_trunc(granularity, CreditTransaction.created_at).label("bucket")
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
        result = await self.session.execute(base_query.order_by(desc(CreditTransaction.created_at)).offset(offset).limit(limit))
        return list(result.scalars().all()), total

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
        result = await self.session.execute(select(CreditRedeemCode).where(CreditRedeemCode.id == code_id))
        return result.scalars().first()

    async def get_redeem_code_for_update(self, code: str) -> CreditRedeemCode | None:
        result = await self.session.execute(select(CreditRedeemCode).where(CreditRedeemCode.code == code).with_for_update())
        return result.scalars().first()

    async def count_redemptions_for_user(
        self,
        *,
        code_id: str,
        user_id: str,
    ) -> int:
        result = await self.session.execute(select(func.count()).select_from(CreditRedemption).where(CreditRedemption.code_id == code_id).where(CreditRedemption.user_id == user_id))
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
        result = await self.session.execute(select(Referral).where(Referral.referee_user_id == referee_user_id))
        return result.scalars().first()


__all__ = [
    "CreditRepository",
]
