"""Persistence primitives for the Mission Runtime aggregate."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.base import generate_uuid
from src.database.models.mission import (
    MissionCommitRecord,
    MissionItemRecord,
    MissionReviewItemRecord,
    MissionRunRecord,
)

NONTERMINAL_MISSION_STATUSES = ("created", "planning", "running", "waiting")


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _bucket_datetime(value: datetime | str) -> datetime:
    parsed = datetime.fromisoformat(value) if isinstance(value, str) else value
    return _aware(parsed)


class MissionRepository:
    """Low-level SQL operations; lifecycle rules live in MissionStore."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def database_now(self) -> datetime:
        result = await self.session.execute(select(func.now()))
        value = result.scalar_one()
        if not isinstance(value, datetime):
            value = datetime.fromisoformat(str(value))
        return _aware(value)

    def create_run(self, values: dict[str, Any]) -> MissionRunRecord:
        record = MissionRunRecord(mission_id=generate_uuid(), **values)
        self.session.add(record)
        return record

    async def get_run(
        self,
        mission_id: str,
        *,
        for_update: bool = False,
        skip_locked: bool = False,
    ) -> MissionRunRecord | None:
        statement = select(MissionRunRecord).where(MissionRunRecord.mission_id == mission_id)
        if for_update:
            statement = statement.with_for_update(skip_locked=skip_locked)
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def find_by_idempotency_key(
        self,
        *,
        workspace_id: str,
        mission_idempotency_key: str,
    ) -> MissionRunRecord | None:
        result = await self.session.execute(
            select(MissionRunRecord).where(
                MissionRunRecord.workspace_id == workspace_id,
                MissionRunRecord.mission_idempotency_key == mission_idempotency_key,
            )
        )
        return result.scalar_one_or_none()

    async def find_foreground_for_thread(
        self,
        thread_id: str,
    ) -> MissionRunRecord | None:
        result = await self.session.execute(
            select(MissionRunRecord).where(
                MissionRunRecord.thread_id == thread_id,
                MissionRunRecord.status.in_(NONTERMINAL_MISSION_STATUSES),
            )
        )
        return result.scalar_one_or_none()

    async def find_latest_for_thread(
        self,
        thread_id: str,
    ) -> MissionRunRecord | None:
        result = await self.session.execute(
            select(MissionRunRecord)
            .where(MissionRunRecord.thread_id == thread_id)
            .order_by(
                MissionRunRecord.created_at.desc(),
                MissionRunRecord.mission_id.desc(),
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_runs(
        self,
        *,
        workspace_id: str,
        user_id: str | None = None,
        status: list[str] | None = None,
        limit: int = 50,
        before_updated_at: datetime | None = None,
        before_mission_id: str | None = None,
    ) -> list[MissionRunRecord]:
        statement = select(MissionRunRecord).where(MissionRunRecord.workspace_id == workspace_id).order_by(MissionRunRecord.updated_at.desc(), MissionRunRecord.mission_id.desc()).limit(limit)
        if user_id is not None:
            statement = statement.where(MissionRunRecord.user_id == user_id)
        if status:
            statement = statement.where(MissionRunRecord.status.in_(status))
        if before_updated_at is not None and before_mission_id is not None:
            statement = statement.where(
                or_(
                    MissionRunRecord.updated_at < before_updated_at,
                    and_(
                        MissionRunRecord.updated_at == before_updated_at,
                        MissionRunRecord.mission_id < before_mission_id,
                    ),
                )
            )
        result = await self.session.execute(statement)
        return list(result.scalars())

    async def list_runs_updated_after(
        self,
        *,
        workspace_id: str,
        updated_at: datetime,
        mission_id: str,
        limit: int = 100,
    ) -> list[MissionRunRecord]:
        result = await self.session.execute(
            select(MissionRunRecord)
            .where(
                MissionRunRecord.workspace_id == workspace_id,
                or_(
                    MissionRunRecord.updated_at > updated_at,
                    and_(
                        MissionRunRecord.updated_at == updated_at,
                        MissionRunRecord.mission_id > mission_id,
                    ),
                ),
            )
            .order_by(MissionRunRecord.updated_at.asc(), MissionRunRecord.mission_id.asc())
            .limit(limit)
        )
        return list(result.scalars())

    async def aggregate_workspace_runs(
        self,
        *,
        workspace_id: str,
        user_id: str | None = None,
    ) -> list[tuple[str, int, int, int, int]]:
        statement = (
            select(
                MissionRunRecord.status,
                func.count(MissionRunRecord.mission_id),
                func.coalesce(func.sum(MissionRunRecord.pending_review_count), 0),
                func.coalesce(func.sum(MissionRunRecord.evidence_count), 0),
                func.coalesce(func.sum(MissionRunRecord.artifact_count), 0),
            )
            .where(MissionRunRecord.workspace_id == workspace_id)
            .group_by(MissionRunRecord.status)
        )
        if user_id is not None:
            statement = statement.where(MissionRunRecord.user_id == user_id)
        result = await self.session.execute(statement)
        return [
            (str(status), int(count), int(pending), int(evidence), int(artifacts))
            for status, count, pending, evidence, artifacts in result.all()
        ]

    async def aggregate_user_runs(self, *, user_id: str) -> list[tuple[str, int]]:
        result = await self.session.execute(
            select(
                MissionRunRecord.status,
                func.count(MissionRunRecord.mission_id),
            )
            .where(MissionRunRecord.user_id == user_id)
            .group_by(MissionRunRecord.status)
        )
        return [(str(status), int(count)) for status, count in result.all()]

    async def list_user_runs(
        self,
        *,
        user_id: str,
        limit: int,
    ) -> list[MissionRunRecord]:
        result = await self.session.execute(
            select(MissionRunRecord)
            .where(MissionRunRecord.user_id == user_id)
            .order_by(
                MissionRunRecord.updated_at.desc(),
                MissionRunRecord.mission_id.desc(),
            )
            .limit(limit)
        )
        return list(result.scalars())

    async def aggregate_stats(
        self,
        *,
        created_since: datetime,
        granularity: str,
    ) -> list[tuple[datetime, str, str, int]]:
        dialect = self.session.get_bind().dialect.name
        if dialect == "sqlite":
            bucket = (
                func.strftime("%Y-%m-%d 00:00:00", MissionRunRecord.created_at)
                if granularity == "day"
                else func.strftime(
                    "%Y-%m-%d 00:00:00",
                    func.date(MissionRunRecord.created_at, "weekday 0", "-6 days"),
                )
            ).label("bucket")
        else:
            bucket = func.date_trunc(granularity, MissionRunRecord.created_at).label("bucket")
        result = await self.session.execute(
            select(
                bucket,
                MissionRunRecord.status,
                MissionRunRecord.workspace_type,
                func.count(MissionRunRecord.mission_id),
            )
            .where(MissionRunRecord.created_at >= created_since)
            .group_by(bucket, MissionRunRecord.status, MissionRunRecord.workspace_type)
            .order_by(bucket.asc())
        )
        return [
            (_bucket_datetime(bucket_value), str(status), str(workspace_type), int(count))
            for bucket_value, status, workspace_type, count in result.all()
        ]

    async def claim_runnable_rows(
        self,
        *,
        now: datetime,
        limit: int,
    ) -> list[MissionRunRecord]:
        due = or_(
            and_(
                MissionRunRecord.next_wakeup_at.is_not(None),
                MissionRunRecord.next_wakeup_at <= now,
            ),
            and_(
                MissionRunRecord.lease_expires_at.is_not(None),
                MissionRunRecord.lease_expires_at <= now,
            ),
        )
        driver_available = or_(
            MissionRunRecord.lease_owner.is_(None),
            MissionRunRecord.lease_expires_at.is_(None),
            MissionRunRecord.lease_expires_at <= now,
        )
        statement = (
            select(MissionRunRecord)
            .where(
                MissionRunRecord.status.in_(NONTERMINAL_MISSION_STATUSES),
                due,
                driver_available,
                or_(
                    MissionRunRecord.dispatch_owner.is_(None),
                    MissionRunRecord.dispatch_expires_at.is_(None),
                    MissionRunRecord.dispatch_expires_at <= now,
                ),
            )
            .order_by(MissionRunRecord.next_wakeup_at.asc().nulls_last())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        result = await self.session.execute(statement)
        return list(result.scalars())

    def append_item(
        self,
        *,
        mission_id: str,
        seq: int,
        values: dict[str, Any],
        created_at: datetime,
    ) -> MissionItemRecord:
        record = MissionItemRecord(
            id=generate_uuid(),
            mission_id=mission_id,
            seq=seq,
            created_at=created_at,
            **values,
        )
        self.session.add(record)
        return record

    async def get_item(
        self,
        *,
        mission_id: str,
        seq: int,
    ) -> MissionItemRecord | None:
        result = await self.session.execute(
            select(MissionItemRecord).where(
                MissionItemRecord.mission_id == mission_id,
                MissionItemRecord.seq == seq,
            )
        )
        return result.scalar_one_or_none()

    async def list_items_by_seqs(
        self,
        *,
        mission_id: str,
        seqs: tuple[int, ...],
    ) -> list[MissionItemRecord]:
        if not seqs:
            return []
        result = await self.session.execute(
            select(MissionItemRecord)
            .where(
                MissionItemRecord.mission_id == mission_id,
                MissionItemRecord.seq.in_(seqs),
            )
            .order_by(MissionItemRecord.seq.asc())
        )
        return list(result.scalars())

    async def find_item_by_operation(
        self,
        *,
        mission_id: str,
        operation_id: str,
        item_type: str | None = None,
    ) -> MissionItemRecord | None:
        statement = select(MissionItemRecord).where(
            MissionItemRecord.mission_id == mission_id,
            MissionItemRecord.operation_id == operation_id,
        )
        if item_type is not None:
            statement = statement.where(MissionItemRecord.item_type == item_type)
        statement = statement.order_by(MissionItemRecord.seq.asc()).limit(1)
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def list_items_by_operation(
        self,
        *,
        mission_id: str,
        operation_id: str,
        item_type: str | None = None,
    ) -> list[MissionItemRecord]:
        statement = (
            select(MissionItemRecord)
            .where(
                MissionItemRecord.mission_id == mission_id,
                MissionItemRecord.operation_id == operation_id,
            )
            .order_by(MissionItemRecord.seq.asc())
        )
        if item_type is not None:
            statement = statement.where(MissionItemRecord.item_type == item_type)
        result = await self.session.execute(statement)
        return list(result.scalars())

    async def list_items(
        self,
        *,
        mission_id: str,
        after_seq: int = 0,
        limit: int = 100,
        item_type: str | None = None,
        through_seq: int | None = None,
    ) -> list[MissionItemRecord]:
        statement = (
            select(MissionItemRecord)
            .where(
                MissionItemRecord.mission_id == mission_id,
                MissionItemRecord.seq > after_seq,
            )
            .order_by(MissionItemRecord.seq.asc())
            .limit(limit)
        )
        if item_type is not None:
            statement = statement.where(MissionItemRecord.item_type == item_type)
        if through_seq is not None:
            statement = statement.where(MissionItemRecord.seq <= through_seq)
        result = await self.session.execute(statement)
        return list(result.scalars())

    async def list_items_by_types(
        self,
        *,
        mission_id: str,
        item_types: tuple[str, ...],
        after_seq: int = 0,
        limit: int = 50,
    ) -> list[MissionItemRecord]:
        result = await self.session.execute(
            select(MissionItemRecord)
            .where(
                MissionItemRecord.mission_id == mission_id,
                MissionItemRecord.seq > after_seq,
                MissionItemRecord.item_type.in_(item_types),
            )
            .order_by(MissionItemRecord.seq.asc())
            .limit(limit)
        )
        return list(result.scalars())

    def create_review_item(self, values: dict[str, Any]) -> MissionReviewItemRecord:
        record = MissionReviewItemRecord(**values)
        self.session.add(record)
        return record

    async def get_review_item(
        self,
        review_item_id: str,
        *,
        for_update: bool = False,
    ) -> MissionReviewItemRecord | None:
        statement = select(MissionReviewItemRecord).where(MissionReviewItemRecord.review_item_id == review_item_id)
        if for_update:
            statement = statement.with_for_update()
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def list_review_items_by_ids(
        self,
        *,
        mission_id: str,
        review_item_ids: list[str],
        for_update: bool = False,
    ) -> list[MissionReviewItemRecord]:
        if not review_item_ids:
            return []
        statement = select(MissionReviewItemRecord).where(
            MissionReviewItemRecord.mission_id == mission_id,
            MissionReviewItemRecord.review_item_id.in_(review_item_ids),
        )
        if for_update:
            statement = statement.with_for_update()
        result = await self.session.execute(statement)
        return list(result.scalars())

    async def list_review_items(
        self,
        *,
        mission_id: str,
        status: list[str] | None = None,
        output_keys: list[str] | None = None,
        for_update: bool = False,
    ) -> list[MissionReviewItemRecord]:
        statement = select(MissionReviewItemRecord).where(MissionReviewItemRecord.mission_id == mission_id).order_by(MissionReviewItemRecord.created_at.asc())
        if status:
            statement = statement.where(MissionReviewItemRecord.status.in_(status))
        if output_keys:
            statement = statement.where(MissionReviewItemRecord.output_key.in_(output_keys))
        if for_update:
            statement = statement.with_for_update()
        result = await self.session.execute(statement)
        return list(result.scalars())

    async def list_expired_review_previews(
        self,
        *,
        now: datetime,
        limit: int,
        for_update: bool = False,
    ) -> list[MissionReviewItemRecord]:
        statement = (
            select(MissionReviewItemRecord)
            .where(
                MissionReviewItemRecord.preview_expires_at.is_not(None),
                MissionReviewItemRecord.preview_expires_at <= now,
                (MissionReviewItemRecord.preview_ref.is_not(None) | (MissionReviewItemRecord.preview_json != {})),
            )
            .order_by(MissionReviewItemRecord.preview_expires_at.asc())
            .limit(limit)
        )
        if for_update:
            statement = statement.with_for_update(skip_locked=True)
        result = await self.session.execute(statement)
        return list(result.scalars())

    def create_commit(self, values: dict[str, Any]) -> MissionCommitRecord:
        record = MissionCommitRecord(commit_id=generate_uuid(), **values)
        self.session.add(record)
        return record

    async def get_commit(
        self,
        commit_id: str,
        *,
        for_update: bool = False,
    ) -> MissionCommitRecord | None:
        statement = select(MissionCommitRecord).where(MissionCommitRecord.commit_id == commit_id)
        if for_update:
            statement = statement.with_for_update()
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def find_commit_by_key(
        self,
        *,
        mission_id: str,
        commit_key: str,
    ) -> MissionCommitRecord | None:
        result = await self.session.execute(
            select(MissionCommitRecord).where(
                MissionCommitRecord.mission_id == mission_id,
                MissionCommitRecord.commit_key == commit_key,
            )
        )
        return result.scalar_one_or_none()

    async def find_commit_by_review_item(
        self,
        review_item_id: str,
    ) -> MissionCommitRecord | None:
        result = await self.session.execute(select(MissionCommitRecord).where(MissionCommitRecord.review_item_id == review_item_id))
        return result.scalar_one_or_none()

    async def list_commits(self, *, mission_id: str) -> list[MissionCommitRecord]:
        result = await self.session.execute(select(MissionCommitRecord).where(MissionCommitRecord.mission_id == mission_id).order_by(MissionCommitRecord.created_at.asc()))
        return list(result.scalars())


__all__ = ["MissionRepository", "NONTERMINAL_MISSION_STATUSES"]
