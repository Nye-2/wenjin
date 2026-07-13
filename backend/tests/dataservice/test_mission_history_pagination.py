"""Stable pagination tests for Mission history."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.database.models.mission import MissionRunRecord
from src.dataservice.common.errors import DataServiceValidationError
from src.dataservice.domains.mission.service import MissionStore
from src.dataservice_client.contracts.mission import MissionCreatePayload


@pytest_asyncio.fixture
async def mission_history_session() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as connection:
        await connection.run_sync(
            lambda sync_connection: MissionRunRecord.metadata.create_all(
                sync_connection,
                tables=[MissionRunRecord.__table__],
            )
        )
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


async def _create_run(
    store: MissionStore,
    *,
    index: str,
    user_id: str,
) -> str:
    result = await store.create_run(
        MissionCreatePayload(
            workspace_id="workspace-1",
            thread_id=f"thread-{index}",
            user_id=user_id,
            workspace_type="sci",
            mission_policy_id="sci.research",
            title=f"Mission {index}",
            objective="Test stable Mission history pagination.",
            model_id="gpt-5.6-sol",
            reasoning_effort="xhigh",
            mission_idempotency_key=f"mission-history-{index}",
        )
    )
    return result.mission.mission_id


@pytest.mark.asyncio
async def test_history_cursor_is_stable_at_equal_timestamps_and_scoped_by_user(
    mission_history_session: AsyncSession,
) -> None:
    store = MissionStore(mission_history_session, autocommit=True)
    mission_ids = [
        await _create_run(store, index=str(index), user_id="user-1")
        for index in range(3)
    ]
    foreign_mission_id = await _create_run(
        store,
        index="foreign",
        user_id="user-2",
    )
    shared_updated_at = datetime(2026, 7, 12, 8, 30, tzinfo=UTC)
    await mission_history_session.execute(
        update(MissionRunRecord)
        .where(MissionRunRecord.mission_id.in_([*mission_ids, foreign_mission_id]))
        .values(updated_at=shared_updated_at)
    )
    await mission_history_session.commit()

    first_page = await store.list_runs_summary(
        workspace_id="workspace-1",
        user_id="user-1",
        limit=2,
    )
    assert first_page.next_cursor is not None
    second_page = await store.list_runs_summary(
        workspace_id="workspace-1",
        user_id="user-1",
        limit=2,
        cursor=first_page.next_cursor,
    )

    returned_ids = [
        run.mission_id for run in [*first_page.items, *second_page.items]
    ]
    assert returned_ids == sorted(mission_ids, reverse=True)
    assert len(returned_ids) == len(set(returned_ids)) == 3
    assert foreign_mission_id not in returned_ids
    assert second_page.next_cursor is None


@pytest.mark.asyncio
async def test_history_rejects_invalid_opaque_cursor(
    mission_history_session: AsyncSession,
) -> None:
    store = MissionStore(mission_history_session, autocommit=True)

    with pytest.raises(DataServiceValidationError, match="Invalid Mission history cursor"):
        await store.list_runs_summary(
            workspace_id="workspace-1",
            cursor="not-a-valid-cursor",
        )
