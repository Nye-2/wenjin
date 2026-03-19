"""Compatibility re-exports for legacy academic database session imports."""

from src.database.session import (
    async_session_factory,
    close_db,
    engine,
    get_db_session,
    init_db,
)

__all__ = [
    "engine",
    "async_session_factory",
    "get_db_session",
    "init_db",
    "close_db",
]
