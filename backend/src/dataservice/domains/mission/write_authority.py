"""Transaction-local validation for reviewed Mission writes."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.contracts.mission_write_authority import MissionWriteAuthority
from src.database.models.mission import (
    MissionCommitRecord,
    MissionReviewItemRecord,
    MissionRunRecord,
)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


async def assert_active_mission_write(
    session: AsyncSession,
    *,
    authority: MissionWriteAuthority | None,
    workspace_id: str,
    mission_id: str | None = None,
    mission_review_item_id: str | None = None,
    mission_commit_id: str | None = None,
    required: bool = False,
) -> None:
    """Fence a protected target write in the target's database transaction."""

    expected_identity = any(
        value is not None
        for value in (mission_review_item_id, mission_commit_id)
    )
    if authority is None:
        if required or expected_identity:
            raise ValueError("mission_write_authority_required")
        return
    if mission_id is not None and mission_id != authority.mission_id:
        raise ValueError("mission_write_authority_mission_mismatch")
    if (
        mission_review_item_id is not None
        and mission_review_item_id != authority.mission_review_item_id
    ):
        raise ValueError("mission_write_authority_review_item_mismatch")
    if mission_commit_id is not None and mission_commit_id != authority.mission_commit_id:
        raise ValueError("mission_write_authority_commit_mismatch")

    statement = (
        select(MissionCommitRecord, MissionReviewItemRecord, MissionRunRecord)
        .join(
            MissionReviewItemRecord,
            MissionReviewItemRecord.review_item_id == MissionCommitRecord.review_item_id,
        )
        .join(
            MissionRunRecord,
            MissionRunRecord.mission_id == MissionCommitRecord.mission_id,
        )
        .where(MissionCommitRecord.commit_id == authority.mission_commit_id)
        .with_for_update()
    )
    row = (await session.execute(statement)).one_or_none()
    now_value = (await session.execute(select(func.now()))).scalar_one()
    now = _aware(
        now_value
        if isinstance(now_value, datetime)
        else datetime.fromisoformat(str(now_value))
    )
    if row is None:
        raise ValueError("mission_write_authority_not_found")
    commit, review_item, mission = row
    if (
        mission.mission_id != authority.mission_id
        or mission.workspace_id != workspace_id
        or review_item.mission_id != authority.mission_id
        or review_item.review_item_id != authority.mission_review_item_id
        or review_item.status != "accepted"
        or commit.mission_id != authority.mission_id
        or commit.review_item_id != authority.mission_review_item_id
        or commit.status != "applying"
        or commit.attempt_token != authority.attempt_token
        or commit.attempt_expires_at is None
        or _aware(commit.attempt_expires_at) <= now
    ):
        raise ValueError("mission_write_authority_lost")


__all__ = ["assert_active_mission_write"]
