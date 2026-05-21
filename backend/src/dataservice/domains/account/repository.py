"""Account repository."""

from __future__ import annotations

from typing import Any

from sqlalchemy import desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.user import User


class AccountRepository:
    """DataService-owned persistence operations for users."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def create_user(self, values: dict[str, Any]) -> User:
        user = User(**values)
        self.session.add(user)
        return user

    async def get_user(self, user_id: str) -> User | None:
        return await self.session.get(User, user_id)

    async def get_by_email(self, email: str) -> User | None:
        result = await self.session.execute(
            select(User).where(User.email == email.lower().strip())
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, user_id: str) -> User | None:
        result = await self.session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def get_admin_stats(self) -> dict[str, int]:
        total = int(
            (await self.session.execute(select(func.count()).select_from(User))).scalar()
            or 0
        )
        active = int(
            (
                await self.session.execute(
                    select(func.count()).where(User.is_active == True)  # noqa: E712
                )
            ).scalar()
            or 0
        )
        admins = int(
            (
                await self.session.execute(
                    select(func.count()).where(User.is_superuser == True)  # noqa: E712
                )
            ).scalar()
            or 0
        )
        return {
            "total_users": total,
            "active_users": active,
            "admin_users": admins,
        }

    async def list_users(
        self,
        *,
        keyword: str | None,
        is_active: bool | None,
        is_superuser: bool | None,
        limit: int,
        offset: int,
    ) -> tuple[list[User], int]:
        base_query = select(User)
        if keyword:
            pattern = f"%{keyword}%"
            base_query = base_query.where(
                or_(
                    User.email.ilike(pattern),
                    User.name.ilike(pattern),
                )
            )
        if is_active is not None:
            base_query = base_query.where(User.is_active == is_active)
        if is_superuser is not None:
            base_query = base_query.where(User.is_superuser == is_superuser)

        total = int(
            (
                await self.session.execute(
                    select(func.count()).select_from(base_query.subquery())
                )
            ).scalar()
            or 0
        )
        result = await self.session.execute(
            base_query.order_by(desc(User.created_at)).offset(offset).limit(limit)
        )
        return list(result.scalars().all()), total

    async def count_active_admins(self) -> int:
        return int(
            (
                await self.session.execute(
                    select(func.count())
                    .where(User.is_superuser == True)  # noqa: E712
                    .where(User.is_active == True)  # noqa: E712
                )
            ).scalar()
            or 0
        )

    async def aggregate_user_growth(
        self,
        *,
        since: Any,
        granularity: str,
    ) -> tuple[list[Any], int]:
        bucket_col = func.date_trunc(granularity, User.created_at).label("bucket")
        rows = (
            await self.session.execute(
                select(bucket_col, func.count().label("signups"))
                .where(User.created_at >= since)
                .group_by(bucket_col)
                .order_by(bucket_col)
            )
        ).all()
        total_users = int(
            (await self.session.execute(select(func.count()).select_from(User))).scalar()
            or 0
        )
        return list(rows), total_users


__all__ = ["AccountRepository"]
