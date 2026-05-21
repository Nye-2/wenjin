"""CreditRedeemService — admin batch generate + user-side atomic redemption.

Atomic redeem uses SELECT ... FOR UPDATE to lock the redeem-code row inside a
transaction, preventing over-redemption under concurrent requests.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.dataservice.catalog_api import CatalogDataService
from src.dataservice.credit_api import CreditDataService
from src.services.redeem_code_generator import generate_code


class RedeemError(Exception):
    """User-facing redeem failure."""


class CreditRedeemService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self._credit = CreditDataService(db, autocommit=False)

    async def _record_admin_log(
        self,
        *,
        action: str,
        admin_id: str,
        details: dict[str, object],
    ) -> None:
        await CatalogDataService(self.db, autocommit=False).record_admin_log(
            action=action,
            admin_id=admin_id,
            target_user_id=None,
            details=dict(details),
        )

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
    ) -> list[object]:
        if amount <= 0:
            raise ValueError("amount must be > 0")
        if count <= 0 or count > 10000:
            raise ValueError("count must be 1..10000")
        if max_uses <= 0 or per_user_limit <= 0:
            raise ValueError("max_uses and per_user_limit must be > 0")

        batch_id = str(uuid.uuid4())
        created: list[object] = []

        for _ in range(count):
            for _attempt in range(5):
                code = generate_code()
                try:
                    async with self.db.begin_nested():
                        obj = await self._credit.create_redeem_code(
                            code=code,
                            amount=amount,
                            max_uses=max_uses,
                            per_user_limit=per_user_limit,
                            expires_at=expires_at,
                            batch_id=batch_id,
                            description=description,
                            admin_id=admin_id,
                        )
                except IntegrityError:
                    continue
                created.append(obj)
                break
            else:
                raise RuntimeError("failed to generate non-conflicting code after 5 attempts")

        await self._record_admin_log(
            action="redeem_code_batch_generate",
            admin_id=admin_id,
            details={"batch_id": batch_id, "count": count, "amount": amount},
        )
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
    ) -> list[object]:
        return await self._credit.list_redeem_codes(
            batch_id=batch_id,
            enabled=enabled,
            keyword=keyword,
            limit=limit,
            offset=offset,
        )

    async def disable(self, code_id: str, admin_id: str) -> object:
        code = await self._credit.disable_redeem_code(code_id)
        if code is None:
            raise ValueError("not found")
        await self._record_admin_log(
            action="redeem_code_disable",
            admin_id=admin_id,
            details={"code_id": code_id, "code": code.code},
        )
        await self.db.commit()
        return code

    async def redeem(self, *, code: str, user_id: str) -> object:
        """Atomic redemption.

        Acquires a row-level lock on the redeem code (SELECT ... FOR UPDATE),
        validates all constraints, writes redemption + transaction, increments use_count.
        Any failure raises RedeemError and the transaction is rolled back.
        """
        try:
            return await self._credit.redeem_code(code=code, user_id=user_id)
        except ValueError as exc:
            raise RedeemError(str(exc)) from exc
