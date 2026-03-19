"""Bootstrap Alembic migrations for legacy databases.

This module handles a migration edge case:
- legacy deployments created tables via SQLAlchemy ``create_all``;
- no ``alembic_version`` table exists;
- a direct ``alembic upgrade head`` fails on duplicate table creation.

When that layout is detected, we stamp to ``head`` first and then run
``upgrade head`` for idempotent convergence.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from enum import StrEnum

import asyncpg

LEGACY_STAMP_REVISION = "007_chat_thread_model_default"


class MigrationBootstrapMode(StrEnum):
    """How migrations should be bootstrapped for the current database state."""

    UPGRADE_ONLY = "upgrade_only"
    STAMP_THEN_UPGRADE = "stamp_then_upgrade"


def decide_bootstrap_mode(table_names: set[str]) -> MigrationBootstrapMode:
    """Decide whether to stamp before running Alembic upgrade."""
    if "alembic_version" in table_names:
        return MigrationBootstrapMode.UPGRADE_ONLY

    if not table_names:
        return MigrationBootstrapMode.UPGRADE_ONLY

    if "users" in table_names:
        return MigrationBootstrapMode.STAMP_THEN_UPGRADE

    raise ValueError(
        "Database has existing tables but no alembic_version/users marker; "
        "refusing to auto-stamp unknown schema."
    )


def _to_asyncpg_url(database_url: str) -> str:
    """Convert SQLAlchemy async URL into an asyncpg-compatible DSN."""
    if database_url.startswith("postgresql+asyncpg://"):
        return database_url.replace("postgresql+asyncpg://", "postgresql://", 1)
    return database_url


async def _fetch_public_tables(database_url: str) -> set[str]:
    """Fetch public schema tables from PostgreSQL."""
    connection = await asyncpg.connect(_to_asyncpg_url(database_url))
    try:
        rows = await connection.fetch(
            """
            SELECT tablename
            FROM pg_tables
            WHERE schemaname = 'public'
            """
        )
    finally:
        await connection.close()

    return {row["tablename"] for row in rows}


def _run_alembic(*args: str) -> None:
    """Execute Alembic command with the current Python runtime."""
    cmd = [sys.executable, "-m", "alembic", *args]
    print(f"[migration-bootstrap] Running: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)


def main() -> int:
    """Bootstrap and run Alembic migrations safely."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is required")

    table_names = asyncio.run(_fetch_public_tables(database_url))
    mode = decide_bootstrap_mode(table_names)

    if mode is MigrationBootstrapMode.STAMP_THEN_UPGRADE:
        print(
            "[migration-bootstrap] Legacy schema detected without alembic_version; "
            f"stamping {LEGACY_STAMP_REVISION} before upgrade."
        )
        _run_alembic("stamp", LEGACY_STAMP_REVISION)

    _run_alembic("upgrade", "head")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
