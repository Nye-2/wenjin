"""Schema-level contracts for the four Mission Runtime tables."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.database.models.mission import (
    MissionCommitRecord,
    MissionItemImmutableError,
    MissionItemRecord,
    MissionReviewItemRecord,
    MissionRunRecord,
)


def test_mission_metadata_has_canonical_runtime_tables() -> None:
    table_names = {
        MissionRunRecord.__tablename__,
        MissionItemRecord.__tablename__,
        MissionReviewItemRecord.__tablename__,
        MissionCommitRecord.__tablename__,
    }
    assert table_names == {
        "mission_runs",
        "mission_items",
        "mission_review_items",
        "mission_commits",
    }
    assert not any(token in name for name in table_names for token in ("event", "tool", "subagent"))


def test_mission_indexes_encode_foreground_scheduler_and_idempotency_contracts() -> None:
    run_indexes = {index.name: index for index in MissionRunRecord.__table__.indexes}
    assert "uq_mission_runs_thread_foreground" in run_indexes
    assert run_indexes["uq_mission_runs_thread_foreground"].unique is True
    assert "uq_mission_runs_workspace_idempotency" in run_indexes
    assert run_indexes["uq_mission_runs_workspace_idempotency"].unique is True
    assert "ix_mission_runs_due_wakeup" in run_indexes
    assert "ix_mission_runs_expired_driver" in run_indexes
    run_constraints = {
        constraint.name for constraint in MissionRunRecord.__table__.constraints
    }
    assert "ck_mission_runs_lease_pair" in run_constraints
    assert "ck_mission_runs_dispatch_pair" in run_constraints
    assert "ck_mission_runs_terminal_quiescent" in run_constraints

    commit_constraints = {
        constraint.name for constraint in MissionCommitRecord.__table__.constraints
    }
    assert "uq_mission_commits_key" in commit_constraints
    assert "uq_mission_commits_review_item" in commit_constraints


@pytest.mark.asyncio
async def test_orm_rejects_mutating_an_appended_mission_item() -> None:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    tables = [
        MissionRunRecord.__table__,
        MissionItemRecord.__table__,
        MissionReviewItemRecord.__table__,
        MissionCommitRecord.__table__,
    ]
    async with engine.begin() as connection:
        await connection.run_sync(
            lambda sync_connection: MissionRunRecord.metadata.create_all(
                sync_connection, tables=tables
            )
        )
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    now = datetime.now(UTC)
    async with factory() as session:
        run = MissionRunRecord(
            mission_id="mission-1",
            workspace_id="workspace-1",
            user_id="user-1",
            workspace_type="sci",
            title="title",
            objective="objective",
            status="created",
            review_mode="balanced_default",
            model_id="gpt-5.6-sol",
            reasoning_effort="xhigh",
            snapshot_json={},
            runtime_context_json={},
            next_wakeup_at=now,
            created_at=now,
            updated_at=now,
        )
        item = MissionItemRecord(
            id="item-1",
            mission_id="mission-1",
            seq=1,
            item_type="plan",
            phase="completed",
            payload_json={},
            created_at=now,
        )
        session.add_all([run, item])
        await session.commit()

        item.summary = "mutated"
        with pytest.raises(MissionItemImmutableError):
            await session.flush()
        await session.rollback()
    await engine.dispose()
