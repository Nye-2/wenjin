"""CreditRedeemService — admin batch generate + user-side atomic redemption.

This runtime service owns business orchestration only. Persistence and atomicity
are delegated to the standalone DataService credit domain.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime

from src.dataservice_client import AsyncDataServiceClient
from src.dataservice_client.contracts.catalog import AdminLogCreatePayload
from src.dataservice_client.contracts.credit import CreditRedeemCodeCreatePayload, CreditRedeemPayload
from src.dataservice_client.errors import DataServiceClientError
from src.dataservice_client.provider import dataservice_client
from src.services.redeem_code_generator import generate_code


class RedeemError(Exception):
    """User-facing redeem failure."""


class CreditRedeemService:
    def __init__(
        self,
        *,
        dataservice: AsyncDataServiceClient | None = None,
    ) -> None:
        self._dataservice = dataservice

    @asynccontextmanager
    async def _client(self) -> AsyncIterator[AsyncDataServiceClient]:
        if self._dataservice is not None:
            yield self._dataservice
            return
        async with dataservice_client() as client:
            yield client

    async def _record_admin_log(
        self,
        *,
        action: str,
        admin_id: str,
        details: dict[str, object],
    ) -> None:
        async with self._client() as client:
            await client.record_catalog_admin_log(
                AdminLogCreatePayload(
                    action=action,
                    admin_id=admin_id,
                    target_user_id=None,
                    details=dict(details),
                )
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
                    async with self._client() as client:
                        obj = await client.create_credit_redeem_code(
                            CreditRedeemCodeCreatePayload(
                                code=code,
                                amount=amount,
                                max_uses=max_uses,
                                per_user_limit=per_user_limit,
                                expires_at=expires_at,
                                batch_id=batch_id,
                                description=description,
                                admin_id=admin_id,
                            )
                        )
                except DataServiceClientError:
                    continue
                if obj is None:
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
        async with self._client() as client:
            return await client.list_credit_redeem_codes(
                batch_id=batch_id,
                enabled=enabled,
                keyword=keyword,
                limit=limit,
                offset=offset,
            )

    async def disable(self, code_id: str, admin_id: str) -> object:
        async with self._client() as client:
            code = await client.disable_credit_redeem_code(code_id)
        if code is None:
            raise ValueError("not found")
        await self._record_admin_log(
            action="redeem_code_disable",
            admin_id=admin_id,
            details={"code_id": code_id, "code": code.code},
        )
        return code

    async def redeem(self, *, code: str, user_id: str) -> object:
        """Redeem through DataService's atomic credit endpoint."""
        try:
            async with self._client() as client:
                return await client.redeem_credit_code(
                    CreditRedeemPayload(code=code, user_id=user_id)
                )
        except (ValueError, DataServiceClientError) as exc:
            raise RedeemError(str(exc)) from exc
