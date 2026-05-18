"""CreditRedeemService — admin batch generate + user-side atomic redemption.

Atomic redeem uses SELECT ... FOR UPDATE to lock the redeem-code row inside a
transaction, preventing over-redemption under concurrent requests.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import (
    AdminLog,
    CreditRedeemCode,
    CreditRedemption,
    CreditTransaction,
    CreditTransactionType,
    User,
)
from src.services.redeem_code_generator import generate_code


class RedeemError(Exception):
    """User-facing redeem failure."""


class CreditRedeemService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def batch_generate(
        self,
        *,
        amount: int,
        count: int,
        max_uses: int,
        per_user_limit: int,
        expires_at: datetime | None,
        description: str | None,
        admin_id: str,
    ) -> list[CreditRedeemCode]:
        if amount <= 0:
            raise ValueError("amount must be > 0")
        if count <= 0 or count > 10000:
            raise ValueError("count must be 1..10000")
        if max_uses <= 0 or per_user_limit <= 0:
            raise ValueError("max_uses and per_user_limit must be > 0")

        batch_id = str(uuid.uuid4())
        created: list[CreditRedeemCode] = []

        for _ in range(count):
            for _attempt in range(5):
                code = generate_code()
                obj = CreditRedeemCode(
                    code=code, amount=amount, max_uses=max_uses,
                    use_count=0, per_user_limit=per_user_limit,
                    expires_at=expires_at, valid_from=None, enabled=True,
                    batch_id=batch_id, description=description,
                    created_by_admin_id=admin_id,
                )
                async with self.db.begin_nested():
                    self.db.add(obj)
                    try:
                        await self.db.flush()
                    except IntegrityError:
                        continue  # savepoint auto-rolled-back; retry with new code
                created.append(obj)
                break
            else:
                raise RuntimeError("failed to generate non-conflicting code after 5 attempts")

        self.db.add(AdminLog(
            action="redeem_code_batch_generate",
            admin_id=admin_id, target_user_id=None,
            details={"batch_id": batch_id, "count": count, "amount": amount},
        ))
        await self.db.commit()
        return created

    async def list_by_filter(
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
        stmt = stmt.limit(limit).offset(offset)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def disable(self, code_id: str, admin_id: str) -> CreditRedeemCode:
        result = await self.db.execute(select(CreditRedeemCode).where(CreditRedeemCode.id == code_id))
        code = result.scalars().first()
        if code is None:
            raise ValueError("not found")
        code.enabled = False
        self.db.add(AdminLog(
            action="redeem_code_disable", admin_id=admin_id, target_user_id=None,
            details={"code_id": code_id, "code": code.code},
        ))
        await self.db.commit()
        return code

    async def redeem(self, *, code: str, user_id: str) -> CreditTransaction:
        """Atomic redemption.

        Acquires a row-level lock on the redeem code (SELECT ... FOR UPDATE),
        validates all constraints, writes redemption + transaction, increments use_count.
        Any failure raises RedeemError and the transaction is rolled back.
        """
        async with self.db.begin():
            stmt = (
                select(CreditRedeemCode)
                .where(CreditRedeemCode.code == code)
                .with_for_update()
            )
            result = await self.db.execute(stmt)
            row = result.scalars().first()

            if row is None:
                raise RedeemError("code not found")
            if not row.enabled:
                raise RedeemError("code disabled")
            now = datetime.now(UTC)
            if row.expires_at and row.expires_at < now:
                raise RedeemError("code expired")
            if row.valid_from and row.valid_from > now:
                raise RedeemError("code not yet valid")
            if row.use_count >= row.max_uses:
                raise RedeemError("code exhausted")

            user_uses_result = await self.db.execute(
                select(func.count())
                .select_from(CreditRedemption)
                .where(CreditRedemption.code_id == row.id)
                .where(CreditRedemption.user_id == user_id)
            )
            user_uses = int(user_uses_result.scalar_one())
            if user_uses >= row.per_user_limit:
                raise RedeemError("per-user limit reached")

            user_result = await self.db.execute(select(User).where(User.id == user_id))
            user = user_result.scalars().first()
            if user is None:
                raise RedeemError("user not found")

            new_balance = (user.credits or 0) + row.amount
            user.credits = new_balance
            user.total_credits_earned = (user.total_credits_earned or 0) + row.amount

            txn = CreditTransaction(
                user_id=user_id,
                transaction_type=CreditTransactionType.REDEEM_CODE,
                amount=row.amount,
                balance_after=new_balance,
                description=f"兑换码 {row.code[:9]}***",
            )
            self.db.add(txn)
            await self.db.flush()

            redemption = CreditRedemption(
                code_id=row.id, user_id=user_id, transaction_id=txn.id,
            )
            self.db.add(redemption)
            row.use_count += 1

        return txn
