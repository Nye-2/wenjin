"""用户认证服务 - JWT 令牌管理

Migrated from AcademiaGPT v1 backend/services/auth.py
"""

import hashlib
from datetime import UTC, datetime, timedelta

from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel

from src.config.app_config import jwt_settings

# 密码哈希上下文
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


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
    return pwd_context.verify(plain_password, hashed_password)


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
    password_bytes = password.encode('utf-8')
    if len(password_bytes) > 72:
        raise ValueError("密码过长，请使用不超过72字节的密码")
    if len(password) < 8:
        raise ValueError("密码过短，请使用至少8个字符的密码")

    return pwd_context.hash(password)


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

    return jwt.encode(
        to_encode,
        jwt_settings.secret_key,
        algorithm="HS256"
    )


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
        "exp": expire,
        "type": "refresh"
    }

    return jwt.encode(
        to_encode,
        jwt_settings.secret_key,
        algorithm="HS256"
    )


def create_tokens(user_id: str, email: str, role: str = "user") -> Token:
    """创建访问令牌和刷新令牌"""
    access_token = create_access_token(user_id, email, role)
    refresh_token = create_refresh_token(user_id)

    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=jwt_settings.access_token_expire_minutes * 60
    )


def decode_token(token: str) -> dict | None:
    """解码令牌"""
    try:
        payload = jwt.decode(
            token,
            jwt_settings.secret_key,
            algorithms=["HS256"]
        )
        return payload
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

    if not user_id or not email:
        return None

    return TokenData(
        user_id=user_id,
        email=email,
        role=role,
        exp=datetime.fromtimestamp(payload.get("exp", 0))
    )


def verify_refresh_token(token: str) -> str | None:
    """验证刷新令牌，返回 user_id"""
    payload = decode_token(token)
    if not payload:
        return None

    if payload.get("type") != "refresh":
        return None

    return payload.get("sub")
