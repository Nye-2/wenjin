from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.database.models.credit_reservation import CreditReservation
from src.database.models.mission import (
    MissionCommitRecord,
    MissionItemRecord,
    MissionReviewItemRecord,
    MissionRunRecord,
)
from src.dataservice.domains.mission.service import MissionStore
from src.dataservice_client.contracts.mission import (
    MissionItemDraftPayload,
    MissionItemPhase,
    MissionStatus,
)
from src.mission_runtime.contracts import MissionSliceLimits, MissionSliceOutcome
from src.mission_runtime.runtime import MissionRuntime

from .conftest import (
    FakeEvents,
    FakeQuality,
    FakeReviewCandidates,
    FakeStartContext,
    FakeSubagents,
    FakeTools,
    FakeWakeups,
    MutableClock,
    ScriptedAgent,
    start_request,
)
from .test_runtime import complete_decision, continue_decision

MISSION_TABLES = [
    MissionRunRecord.__table__,
    CreditReservation.__table__,
    MissionItemRecord.__table__,
    MissionReviewItemRecord.__table__,
    MissionCommitRecord.__table__,
]


class DirectMissionStoreAdapter:
    """Exercise MissionRuntime against the real transactional store contract."""

    def __init__(self, store: MissionStore) -> None:
        self.store = store

    async def admit(self, command):
        created = await self.store.create_run(command)
        if not created.created:
            return created
        snapshot = dict(created.mission.snapshot_json)
        snapshot["billing"] = {"state": "ready", "free_policy": True}
        mission = await self.store.apply_initial_admission(
            created.mission.mission_id,
            status=MissionStatus.PLANNING,
            snapshot_json=snapshot,
            item=MissionItemDraftPayload(
                item_type="status_update",
                phase=MissionItemPhase.COMPLETED,
                producer="mission_admission",
                summary="Mission admitted for integration test",
            ),
        )
        return created.model_copy(update={"mission": mission})

    async def get(self, mission_id):
        return await self.store.load_run_snapshot(mission_id)

    async def claim_lease(self, mission_id, command):
        return await self.store.claim_run_lease(mission_id, command)

    async def heartbeat_lease(self, mission_id, command):
        return await self.store.heartbeat_run_lease(mission_id, command)

    async def release_lease(self, mission_id, command):
        return await self.store.release_run_lease(mission_id, command)

    async def claim_runnable(self, command):
        return await self.store.claim_runnable_batch_skip_locked(command)

    async def append_items(self, mission_id, command):
        return await self.store.append_items_and_update_snapshot(mission_id, command)

    async def list_items(self, mission_id, **kwargs):
        return await self.store.list_items_page(mission_id, **kwargs)

    async def list_model_call_states(self, mission_id):
        return await self.store.list_model_call_states(mission_id)

    async def list_unapplied_commands(self, mission_id, **kwargs):
        return await self.store.list_unapplied_commands(mission_id, **kwargs)

    async def apply_commands(self, mission_id, command):
        return await self.store.apply_commands_and_advance_cursor(mission_id, command)

    async def resume(self, mission_id, command):
        return await self.store.resume_run(mission_id, command)

    async def create_review_items(self, mission_id, command):
        return await self.store.create_review_items(mission_id, command)


@pytest_asyncio.fixture
async def mission_session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as connection:
        await connection.run_sync(
            lambda sync_connection: MissionRunRecord.metadata.create_all(
                sync_connection,
                tables=MISSION_TABLES,
            )
        )
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_runtime_drives_real_mission_store_across_two_slices(
    mission_session: AsyncSession,
) -> None:
    adapter = DirectMissionStoreAdapter(MissionStore(mission_session, autocommit=True))
    limits = MissionSliceLimits(
        wall_time_seconds=10,
        shutdown_margin_seconds=1,
        lease_ttl_seconds=20,
        heartbeat_interval_seconds=2,
        max_model_turns=1,
        max_tool_steps=4,
    )
    runtime = MissionRuntime(
        store=adapter,
        agent=ScriptedAgent([continue_decision("plan-1"), complete_decision()]),
        start_context=FakeStartContext(),
        tools=FakeTools(),
        subagents=FakeSubagents(),
        quality=FakeQuality(),
        review_candidates=FakeReviewCandidates(),
        events=FakeEvents(),
        wakeups=FakeWakeups(),
        limits=limits,
        clock=MutableClock(),
    )
    receipt = await runtime.start(start_request())

    first = await runtime.run_slice(receipt.mission_id, worker_id="worker-1")
    second = await runtime.run_slice(receipt.mission_id, worker_id="worker-2")
    run = await adapter.get(receipt.mission_id)
    items = await adapter.list_items(receipt.mission_id, after_seq=0, limit=100)

    assert first.outcome == MissionSliceOutcome.YIELDED
    assert second.outcome == MissionSliceOutcome.COMPLETED
    assert run is not None and run.status.value == "completed"
    assert run.lease_epoch == 2
    assert [item.seq for item in items] == list(range(1, len(items) + 1))
    assert any(item.item_type == "context_checkpoint" for item in items)
