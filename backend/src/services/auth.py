"""用户认证服务 - JWT 令牌管理"""

import hashlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol, cast
from uuid import uuid4

import bcrypt
from jose import JWTError, jwt
from pydantic import BaseModel

from src.config.app_config import jwt_settings
from src.dataservice_client import AsyncDataServiceClient
from src.dataservice_client.contracts.account import AccountRefreshTokenPayload
from src.dataservice_client.provider import dataservice_client

type JwtPayload = dict[str, object]


class RefreshTokenUser(Protocol):
    """User fields required for refresh-token persistence and verification."""

    id: str
    refresh_token_hash: str | None
    refresh_token_expires_at: datetime | None


@asynccontextmanager
async def _account_client(
    dataservice: AsyncDataServiceClient | None,
) -> AsyncIterator[AsyncDataServiceClient]:
    if dataservice is not None:
        yield dataservice
        return
    async with dataservice_client() as client:
        yield client

class TokenData(BaseModel):
    """令牌数据"""
    user_id: str
    email: str
    role: str = "user"
    exp: datetime | None = None


class Token(BaseModel):
    """令牌响应"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # 秒


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码"""
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("ascii"))
    except (TypeError, ValueError):
        return False


def hash_password(password: str) -> str:
    """哈希密码

    Args:
        password: 原始密码

    Returns:
        哈希后的密码

    Raises:
        ValueError: 密码长度不符合要求

    Note:
        bcrypt 算法限制密码最长 72 字节，超过此长度将拒绝而非截断
    """
    # 清理密码（去除首尾空格和换行符）
    password = password.strip()

    # 检查密码长度
    password_bytes = password.encode("utf-8")
    if len(password_bytes) > 72:
        raise ValueError("密码过长，请使用不超过72字节的密码")
    if len(password) < 8:
        raise ValueError("密码过短，请使用至少8个字符的密码")

    return bcrypt.hashpw(password_bytes, bcrypt.gensalt()).decode("ascii")


def hash_token(token: str) -> str:
    """哈希令牌（用于存储在数据库中）"""
    return hashlib.sha256(token.encode()).hexdigest()


def create_access_token(
    user_id: str,
    email: str,
    role: str = "user",
    expires_delta: timedelta | None = None
) -> str:
    """创建访问令牌"""
    if expires_delta:
        expire = datetime.now(UTC) + expires_delta
    else:
        expire = datetime.now(UTC) + timedelta(
            minutes=jwt_settings.access_token_expire_minutes
        )

    to_encode = {
        "sub": user_id,
        "email": email,
        "role": role,
        "exp": expire,
        "type": "access"
    }

    return cast(str, jwt.encode(
        to_encode,
        jwt_settings.secret_key,
        algorithm="HS256"
    ))


def create_refresh_token(
    user_id: str,
    expires_delta: timedelta | None = None
) -> str:
    """创建刷新令牌"""
    if expires_delta:
        expire = datetime.now(UTC) + expires_delta
    else:
        expire = datetime.now(UTC) + timedelta(
            days=jwt_settings.refresh_token_expire_days
        )

    to_encode = {
        "sub": user_id,
        "jti": uuid4().hex,
        "iat": datetime.now(UTC),
        "exp": expire,
        "type": "refresh"
    }

    return cast(str, jwt.encode(
        to_encode,
        jwt_settings.secret_key,
        algorithm="HS256"
    ))


def create_tokens(user_id: str, email: str, role: str = "user") -> Token:
    """创建访问令牌和刷新令牌"""
    access_token = create_access_token(user_id, email, role)
    refresh_token = create_refresh_token(user_id)

    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=jwt_settings.access_token_expire_minutes * 60
    )


def decode_token(token: str) -> JwtPayload | None:
    """解码令牌"""
    try:
        payload = jwt.decode(
            token,
            jwt_settings.secret_key,
            algorithms=["HS256"]
        )
        return cast(JwtPayload, payload) if isinstance(payload, dict) else None
    except JWTError:
        return None


def verify_access_token(token: str) -> TokenData | None:
    """验证访问令牌"""
    payload = decode_token(token)
    if not payload:
        return None

    if payload.get("type") != "access":
        return None

    user_id = payload.get("sub")
    email = payload.get("email")
    role = payload.get("role", "user")

    if not isinstance(user_id, str) or not isinstance(email, str):
        return None

    return TokenData(
        user_id=user_id,
        email=email,
        role=role if isinstance(role, str) else "user",
        exp=_coerce_expiry(payload.get("exp")),
    )


def verify_refresh_token(token: str) -> str | None:
    """验证刷新令牌，返回 user_id"""
    payload = decode_token(token)
    if not payload:
        return None

    if payload.get("type") != "refresh":
        return None

    user_id = payload.get("sub")
    return user_id if isinstance(user_id, str) else None


def _coerce_expiry(value: object) -> datetime | None:
    """Convert a JWT exp value to a timezone-aware datetime."""
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=UTC)

    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, UTC)

    return None


async def _get_user_record(
    user_id: str,
    *,
    dataservice: AsyncDataServiceClient | None = None,
) -> Any | None:
    """Load the concrete user record through the Account DataService boundary."""
    async with _account_client(dataservice) as client:
        return await client.get_account_auth_user(user_id)


async def persist_refresh_token(
    *,
    user: RefreshTokenUser,
    refresh_token: str,
    dataservice: AsyncDataServiceClient | None = None,
) -> None:
    """Persist the currently active refresh token hash for a user."""
    payload = decode_token(refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise ValueError("Invalid refresh token payload")

    hashed = hash_token(refresh_token)
    expires_at = _coerce_expiry(payload.get("exp"))
    async with _account_client(dataservice) as client:
        await client.update_account_refresh_token(
            str(user.id),
            AccountRefreshTokenPayload(
                refresh_token_hash=hashed,
                refresh_token_expires_at=expires_at,
            ),
        )
    user.refresh_token_hash = hashed
    user.refresh_token_expires_at = expires_at


async def revoke_refresh_token(
    *,
    user: RefreshTokenUser,
    dataservice: AsyncDataServiceClient | None = None,
) -> None:
    """Revoke the currently active refresh token for a user."""
    async with _account_client(dataservice) as client:
        await client.update_account_refresh_token(
            str(user.id),
            AccountRefreshTokenPayload(
                refresh_token_hash=None,
                refresh_token_expires_at=None,
            ),
        )
    user.refresh_token_hash = None
    user.refresh_token_expires_at = None


async def create_and_persist_tokens(
    *,
    user_id: str,
    email: str,
    role: str = "user",
    user: RefreshTokenUser | None = None,
    dataservice: AsyncDataServiceClient | None = None,
) -> Token:
    """Create JWTs and persist the active refresh token hash."""
    tokens = create_tokens(user_id=user_id, email=email, role=role)
    if user is None:
        user = await _get_user_record(user_id, dataservice=dataservice)
        if user is None:
            raise ValueError("User not found")

    await persist_refresh_token(
        user=user,
        refresh_token=tokens.refresh_token,
        dataservice=dataservice,
    )
    return tokens


async def verify_refresh_token_recorded(
    token: str,
    *,
    dataservice: AsyncDataServiceClient | None = None,
) -> Any | None:
    """Verify refresh token against its persisted hash and expiry."""
    user_id = verify_refresh_token(token)
    if not user_id:
        return None

    user = await _get_user_record(user_id, dataservice=dataservice)
    if user is None:
        return None

    if not user.refresh_token_hash or user.refresh_token_hash != hash_token(token):
        return None

    expires_at = user.refresh_token_expires_at
    if expires_at is None:
        return None

    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)

    if expires_at <= datetime.now(UTC):
        return None

    return user
