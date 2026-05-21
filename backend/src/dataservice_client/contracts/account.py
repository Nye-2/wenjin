"""Account contracts returned by DataService client methods."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class AccountUserPayload(BaseModel):
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


class AccountAdminStatsPayload(BaseModel):
    total_users: int
    active_users: int
    admin_users: int


class AccountUserListPayload(BaseModel):
    users: list[AccountUserPayload] = Field(default_factory=list)
    total: int


class AccountUserGrowthPayload(BaseModel):
    total_users: int
    new_in_range: int
    time_series: list[dict[str, int | str]] = Field(default_factory=list)


class AccountUserCreatePayload(BaseModel):
    email: str
    hashed_password: str
    name: str
    auto_commit: bool = True


class AccountUserStatusPayload(BaseModel):
    is_active: bool


class AccountUserRolePayload(BaseModel):
    role: str
