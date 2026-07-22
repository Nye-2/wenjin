"""PostgreSQL verification for the per-workspace Mission execution slot."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from src.dataservice.domains.mission.repository import MissionRepository

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_workspace_execution_slot_serializes_concurrent_transactions(
    postgres_110_database: Any,
) -> None:
    engine = create_async_engine(
        postgres_110_database.async_url,
        pool_size=2,
        max_overflow=0,
        pool_pre_ping=True,
    )
    sessions = async_sessionmaker(
        engine,
        expire_on_commit=False,
        autoflush=False,
    )
    first_has_slot = asyncio.Event()
    second_pid: asyncio.Queue[int] = asyncio.Queue(maxsize=1)
    second_acquired = asyncio.Event()

    async def hold_first_slot() -> None:
        async with sessions() as session:
            async with session.begin():
                await session.execute(text("SET LOCAL statement_timeout = '10s'"))
                await MissionRepository(session).lock_workspace_execution_slot(
                    "release-workspace-slot"
                )
                first_has_slot.set()
                blocked_pid = await asyncio.wait_for(second_pid.get(), timeout=2)
                for _ in range(200):
                    wait_event_type = (
                        await session.execute(
                            text(
                                "SELECT wait_event_type FROM pg_stat_activity "
                                "WHERE pid = :blocked_pid"
                            ),
                            {"blocked_pid": blocked_pid},
                        )
                    ).scalar_one_or_none()
                    if wait_event_type == "Lock":
                        break
                    await asyncio.sleep(0.01)
                else:
                    raise AssertionError(
                        "second Mission transaction never waited on the workspace slot"
                    )
                assert not second_acquired.is_set()

    async def wait_for_same_slot() -> None:
        await first_has_slot.wait()
        async with sessions() as session:
            async with session.begin():
                await session.execute(text("SET LOCAL statement_timeout = '10s'"))
                pid = (
                    await session.execute(text("SELECT pg_backend_pid()"))
                ).scalar_one()
                repository = MissionRepository(session)
                assert not await repository.try_lock_workspace_execution_slot(
                    "release-workspace-slot"
                )
                await second_pid.put(pid)
                await repository.lock_workspace_execution_slot(
                    "release-workspace-slot"
                )
                second_acquired.set()

    try:
        await asyncio.gather(hold_first_slot(), wait_for_same_slot())
        assert second_acquired.is_set()
    finally:
        await engine.dispose()
