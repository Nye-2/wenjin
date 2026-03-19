"""Services package for AcademiaGPT v2."""

from .auth import (
    Token,
    TokenData,
    create_and_persist_tokens,
    create_access_token,
    create_refresh_token,
    create_tokens,
    decode_token,
    hash_password,
    hash_token,
    persist_refresh_token,
    revoke_refresh_token,
    verify_access_token,
    verify_password,
    verify_refresh_token,
    verify_refresh_token_recorded,
)
from .chat_thread_service import ChatThreadAccessError, ChatThreadService
from .credit_service import CreditService, InsufficientCreditsError
from .user_service import UserService

__all__ = [
    "Token",
    "TokenData",
    "create_and_persist_tokens",
    "create_access_token",
    "create_refresh_token",
    "create_tokens",
    "decode_token",
    "verify_access_token",
    "verify_refresh_token",
    "verify_refresh_token_recorded",
    "verify_password",
    "hash_password",
    "hash_token",
    "persist_refresh_token",
    "revoke_refresh_token",
    "ChatThreadAccessError",
    "ChatThreadService",
    "CreditService",
    "InsufficientCreditsError",
    "UserService",
]
