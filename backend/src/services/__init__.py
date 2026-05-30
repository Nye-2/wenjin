"""Services package for Wenjin.

The package root intentionally exposes service symbols lazily. Several low-level
modules import specific submodules such as ``src.services.model_catalog_cache``;
eager imports here would pull auth, thread, agent, and execution dependencies
into configuration import paths and create circular imports.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

_EXPORTS = {
    "Token": ("src.services.auth", "Token"),
    "TokenData": ("src.services.auth", "TokenData"),
    "create_access_token": ("src.services.auth", "create_access_token"),
    "create_and_persist_tokens": ("src.services.auth", "create_and_persist_tokens"),
    "create_refresh_token": ("src.services.auth", "create_refresh_token"),
    "create_tokens": ("src.services.auth", "create_tokens"),
    "decode_token": ("src.services.auth", "decode_token"),
    "hash_password": ("src.services.auth", "hash_password"),
    "hash_token": ("src.services.auth", "hash_token"),
    "persist_refresh_token": ("src.services.auth", "persist_refresh_token"),
    "revoke_refresh_token": ("src.services.auth", "revoke_refresh_token"),
    "verify_access_token": ("src.services.auth", "verify_access_token"),
    "verify_password": ("src.services.auth", "verify_password"),
    "verify_refresh_token": ("src.services.auth", "verify_refresh_token"),
    "verify_refresh_token_recorded": ("src.services.auth", "verify_refresh_token_recorded"),
    "CreditService": ("src.services.credit_service", "CreditService"),
    "ThreadAccessError": ("src.services.thread_service", "ThreadAccessError"),
    "ThreadService": ("src.services.thread_service", "ThreadService"),
    "UserService": ("src.services.user_service", "UserService"),
}

__all__ = sorted(_EXPORTS)


def __getattr__(name: str) -> Any:
    target = _EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr_name = target
    value = getattr(import_module(module_name), attr_name)
    globals()[name] = value
    return value
