"""Public in-process account API for DataService."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.dataservice.domains.account.contracts import (
    AccountAdminStatsRecord,
    AccountUserGrowthRecord,
    AccountUserListResult,
    AccountUserRecord,
)
from src.dataservice.domains.account.service import DataServiceAccountService


class AccountDataService:
    """Account aggregate API exposed by DataService to runtime modules."""

    def __init__(self, session: AsyncSession, *, autocommit: bool = True) -> None:
        self._domain = DataServiceAccountService(session, autocommit=autocommit)

    async def create_user(self, **kwargs: Any) -> Any:
        return await self._domain.create_user(**kwargs)

    async def get_by_email(self, email: str) -> Any | None:
        return await self._domain.get_by_email(email)

    async def get_by_id(self, user_id: str) -> Any | None:
        return await self._domain.get_by_id(user_id)

    async def update_last_login(self, user_id: str) -> Any | None:
        return await self._domain.update_last_login(user_id)

    async def get_user_record(self, user_id: str) -> AccountUserRecord | None:
        return await self._domain.get_user_record(user_id)

    async def get_admin_stats(self) -> AccountAdminStatsRecord:
        return await self._domain.get_admin_stats()

    async def list_users(self, **kwargs: Any) -> AccountUserListResult:
        return await self._domain.list_users(**kwargs)

    async def count_active_admins(self) -> int:
        return await self._domain.count_active_admins()

    async def update_user_status(self, **kwargs: Any) -> AccountUserRecord | None:
        return await self._domain.update_user_status(**kwargs)

    async def update_user_role(self, **kwargs: Any) -> AccountUserRecord | None:
        return await self._domain.update_user_role(**kwargs)

    async def aggregate_user_growth(self, **kwargs: Any) -> AccountUserGrowthRecord:
        return await self._domain.aggregate_user_growth(**kwargs)


__all__ = [
    "AccountAdminStatsRecord",
    "AccountDataService",
    "AccountUserGrowthRecord",
    "AccountUserListResult",
    "AccountUserRecord",
]
