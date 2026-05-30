"""Authentication-related FastAPI dependencies."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.dataservice_client import AsyncDataServiceClient
from src.gateway.deps.core import get_dataservice_client
from src.services.auth import verify_access_token
from src.services.user_service import UserService

security = HTTPBearer(auto_error=False)


@dataclass(slots=True)
class AccountAuthSubject:
    """Application-facing authenticated account projection."""

    id: str
    email: str
    name: str | None
    role: str
    is_active: bool
    is_superuser: bool
    credits: int = 0
    total_credits_earned: int = 0
    total_credits_spent: int = 0
    created_at: datetime | None = None
    last_login: datetime | None = None
    refresh_token_hash: str | None = None
    refresh_token_expires_at: datetime | None = None

    @classmethod
    def from_record(cls, user: Any) -> "AccountAuthSubject":
        role = getattr(user, "role", None)
        role_value = getattr(role, "value", role)
        is_superuser = bool(getattr(user, "is_superuser", False))
        return cls(
            id=str(user.id),
            email=str(user.email),
            name=getattr(user, "name", None),
            role=str(role_value or ("admin" if is_superuser else "user")),
            is_active=bool(getattr(user, "is_active", False)),
            is_superuser=is_superuser,
            credits=int(getattr(user, "credits", 0) or 0),
            total_credits_earned=int(getattr(user, "total_credits_earned", 0) or 0),
            total_credits_spent=int(getattr(user, "total_credits_spent", 0) or 0),
            created_at=getattr(user, "created_at", None),
            last_login=getattr(user, "last_login", None),
            refresh_token_hash=getattr(user, "refresh_token_hash", None),
            refresh_token_expires_at=getattr(user, "refresh_token_expires_at", None),
        )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> AccountAuthSubject:
    """Get current authenticated user from JWT token."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token_data = verify_access_token(credentials.credentials)
    if token_data is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_service = UserService(dataservice=dataservice)
    user = await user_service.get_by_id(token_data.user_id)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is disabled",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return AccountAuthSubject.from_record(user)


async def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    dataservice: AsyncDataServiceClient = Depends(get_dataservice_client),
) -> AccountAuthSubject | None:
    """Get current user if authenticated, otherwise return None."""
    if credentials is None:
        return None

    token_data = verify_access_token(credentials.credentials)
    if token_data is None:
        return None

    user_service = UserService(dataservice=dataservice)
    user = await user_service.get_by_id(token_data.user_id)
    if user is None or not user.is_active:
        return None

    return AccountAuthSubject.from_record(user)


async def get_current_admin(
    current_user: AccountAuthSubject = Depends(get_current_user),
) -> AccountAuthSubject:
    """Get current authenticated user and verify admin privileges."""
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )
    return current_user
