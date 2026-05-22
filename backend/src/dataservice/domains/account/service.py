"""Account command/query service."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.user import User
from src.dataservice.domains.account.contracts import (
    AccountAdminStatsRecord,
    AccountUserGrowthRecord,
    AccountUserListResult,
    AccountUserRecord,
)
from src.dataservice.domains.account.repository import AccountRepository


class DataServiceAccountService:
    """DataService-owned account operations."""

    def __init__(self, session: AsyncSession, *, autocommit: bool = True) -> None:
        self.session = session
        self.autocommit = autocommit
        self.repository = AccountRepository(session)

    async def create_user(
        self,
        *,
        email: str,
        hashed_password: str,
        name: str,
        auto_commit: bool = True,
    ) -> User:
        user = self.repository.create_user(
            {
                "email": email.lower().strip(),
                "name": name,
                "hashed_password": hashed_password,
                "is_active": True,
                "is_superuser": False,
            }
        )
        await self.session.flush()
        if auto_commit:
            await self.session.commit()
            await self.session.refresh(user)
        return user

    async def get_by_email(self, email: str) -> User | None:
        return await self.repository.get_by_email(email)

    async def get_by_id(self, user_id: str) -> User | None:
        return await self.repository.get_by_id(user_id)

    async def update_last_login(self, user_id: str) -> User | None:
        user = await self.repository.get_by_id(user_id)
        if user is None:
            return None
        user.last_login = datetime.now(UTC)
        await self._finish(user)
        return user

    async def get_user_record(self, user_id: str) -> AccountUserRecord | None:
        user = await self.repository.get_user(user_id)
        return self.to_record(user) if user is not None else None

    async def get_auth_user_by_id(self, user_id: str) -> AccountUserRecord | None:
        user = await self.repository.get_by_id(user_id)
        return self.to_auth_record(user) if user is not None else None

    async def get_auth_user_by_email(self, email: str) -> AccountUserRecord | None:
        user = await self.repository.get_by_email(email)
        return self.to_auth_record(user) if user is not None else None

    async def update_refresh_token(
        self,
        *,
        user_id: str,
        refresh_token_hash: str | None,
        refresh_token_expires_at: datetime | None,
    ) -> AccountUserRecord | None:
        user = await self.repository.get_by_id(user_id)
        if user is None:
            return None
        user.refresh_token_hash = refresh_token_hash
        user.refresh_token_expires_at = refresh_token_expires_at
        await self._finish(user)
        return self.to_auth_record(user)

    async def get_admin_stats(self) -> AccountAdminStatsRecord:
        return AccountAdminStatsRecord(**await self.repository.get_admin_stats())

    async def list_users(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        keyword: str | None = None,
        is_active: bool | None = None,
        is_superuser: bool | None = None,
    ) -> AccountUserListResult:
        page = max(1, page)
        page_size = min(max(1, page_size), 100)
        offset = (page - 1) * page_size
        users, total = await self.repository.list_users(
            keyword=keyword,
            is_active=is_active,
            is_superuser=is_superuser,
            limit=page_size,
            offset=offset,
        )
        return AccountUserListResult(
            users=[self.to_record(user) for user in users],
            total=total,
        )

    async def count_active_admins(self) -> int:
        return await self.repository.count_active_admins()

    async def update_user_status(
        self,
        *,
        user_id: str,
        is_active: bool,
    ) -> AccountUserRecord | None:
        user = await self.repository.get_user(user_id)
        if user is None:
            return None
        if not is_active and user.is_superuser and user.is_active:
            active_admins = await self.repository.count_active_admins()
            if active_admins <= 1:
                raise ValueError("Cannot disable the last active admin")
        user.is_active = is_active
        await self._finish(user)
        return self.to_record(user)

    async def update_user_role(
        self,
        *,
        user_id: str,
        role: str,
    ) -> AccountUserRecord | None:
        role = role.lower().strip()
        if role not in {"user", "admin"}:
            raise ValueError("Unsupported role")
        user = await self.repository.get_user(user_id)
        if user is None:
            return None
        if role == "user" and user.is_superuser and user.is_active:
            active_admins = await self.repository.count_active_admins()
            if active_admins <= 1:
                raise ValueError("Cannot demote the last active admin")
        user.is_superuser = role == "admin"
        await self._finish(user)
        return self.to_record(user)

    async def aggregate_user_growth(
        self,
        *,
        since: datetime,
        granularity: str,
    ) -> AccountUserGrowthRecord:
        rows, total_users = await self.repository.aggregate_user_growth(
            since=since,
            granularity=granularity,
        )
        signups_map = {row.bucket.isoformat(): int(row.signups) for row in rows}
        return AccountUserGrowthRecord(
            total_users=total_users,
            new_in_range=sum(signups_map.values()),
            time_series=[
                {"date": bucket, "signups": signups_map.get(bucket, 0)}
                for bucket in sorted(signups_map)
            ],
        )

    @staticmethod
    def to_record(user: User) -> AccountUserRecord:
        return AccountUserRecord(
            id=str(user.id),
            email=user.email,
            name=user.name,
            role="admin" if user.is_superuser else "user",
            is_active=bool(user.is_active),
            is_superuser=bool(user.is_superuser),
            credits=int(user.credits),
            total_credits_earned=int(user.total_credits_earned),
            total_credits_spent=int(user.total_credits_spent),
            created_at=user.created_at,
            updated_at=getattr(user, "updated_at", None),
            last_login=getattr(user, "last_login", None),
        )

    @staticmethod
    def to_auth_record(user: User) -> AccountUserRecord:
        record = DataServiceAccountService.to_record(user)
        record.hashed_password = user.hashed_password
        record.refresh_token_hash = getattr(user, "refresh_token_hash", None)
        record.refresh_token_expires_at = getattr(user, "refresh_token_expires_at", None)
        return record

    async def _finish(self, record: Any | None = None) -> None:
        if self.autocommit:
            await self.session.commit()
            if record is not None:
                await self.session.refresh(record)
            return
        await self.session.flush()
        if record is not None:
            await self.session.refresh(record)
