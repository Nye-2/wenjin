"""ReferralService facade backed by CreditDataService."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy.exc import IntegrityError

from src.dataservice_client import AsyncDataServiceClient
from src.dataservice_client.contracts.credit import CreditReferralCreatePayload
from src.dataservice_client.errors import DataServiceClientError
from src.dataservice_client.provider import dataservice_client


class ReferralService:
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

    async def record(self, *, referrer_user_id: str, referee_user_id: str) -> Any:
        if referrer_user_id == referee_user_id:
            raise ValueError("cannot refer self")
        try:
            async with self._client() as client:
                return await client.record_credit_referral(
                    CreditReferralCreatePayload(
                        referrer_user_id=referrer_user_id,
                        referee_user_id=referee_user_id,
                    )
                )
        except (IntegrityError, DataServiceClientError) as exc:
            raise ValueError("referee already has a referrer") from exc

    async def get_by_referee(self, referee_user_id: str) -> Any | None:
        async with self._client() as client:
            return await client.get_credit_referral_by_referee(referee_user_id)

    async def fire_referee_on_signup(self, referee_user_id: str) -> Any | None:
        async with self._client() as client:
            return await client.apply_credit_referee_signup_bonus(referee_user_id)

    async def fire_first_task_for_referrer(self, referee_user_id: str) -> Any | None:
        async with self._client() as client:
            return await client.apply_credit_referrer_first_task_bonus(referee_user_id)
