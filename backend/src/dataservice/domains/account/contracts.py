"""Account domain contracts."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class AccountUserRecord(BaseModel):
    """User projection owned by Account DataService."""

    id: str
    email: str
    name: str
    role: str
    is_active: bool
    is_superuser: bool
    credits: int
    total_credits_earned: int
    total_credits_spent: int
    created_at: datetime | None = None
    updated_at: datetime | None = None
    last_login: datetime | None = None


class AccountAdminStatsRecord(BaseModel):
    """Admin-facing account summary."""

    total_users: int
    active_users: int
    admin_users: int


class AccountUserListResult(BaseModel):
    """Paginated account user list."""

    users: list[AccountUserRecord] = Field(default_factory=list)
    total: int


class AccountUserGrowthRecord(BaseModel):
    """User growth analytics projection."""

    total_users: int
    new_in_range: int
    time_series: list[dict[str, int | str]] = Field(default_factory=list)
