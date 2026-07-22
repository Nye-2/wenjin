"""Persistence primitives for the Mission Runtime aggregate."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import and_, case, exists, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from src.database.base import generate_uuid
from src.database.models.mission import (
    MissionCommitRecord,
    MissionItemRecord,
    MissionReviewItemRecord,
    MissionRunRecord,
)

NONTERMINAL_MISSION_STATUSES = ("created", "planning", "running", "waiting")


@dataclass(frozen=True, slots=True)
class ArtifactProjectionRevisionRow:
    review_item_id: str
    source_item_seq: int
    title: str
    target_kind: str
    summary: str | None
    review_status: str
    preview_ref: str | None
    preview_expires_at: datetime | None
    artifact_kind: str | None
    materialization_operation: str | None
    commit_status: str | None


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _bucket_datetime(value: datetime | str) -> datetime:
    parsed = datetime.fromisoformat(value) if isinstance(value, str) else value
    return _aware(parsed)


def _workspace_execution_lock_key(workspace_id: str) -> int:
    digest = hashlib.sha256(
        f"mission-workspace-slot:{workspace_id}".encode()
    ).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=True)


def _mission_due_at(record: Any = MissionRunRecord):
    wakeup = record.next_wakeup_at
    lease_expiry = record.lease_expires_at
    return case(
        (wakeup.is_(None), lease_expiry),
        (lease_expiry.is_(None), wakeup),
        (wakeup <= lease_expiry, wakeup),
        else_=lease_expiry,
    )


def _current_review_rows(mission_id: str):
    return (
        select(
            MissionReviewItemRecord.review_item_id.label("review_item_id"),
            MissionReviewItemRecord.status.label("status"),
            func.row_number()
            .over(
                partition_by=MissionReviewItemRecord.output_key,
                order_by=(
                    MissionReviewItemRecord.created_at.desc(),
                    MissionReviewItemRecord.review_item_id.desc(),
                ),
            )
            .label("review_rank"),
        )
        .where(
            MissionReviewItemRecord.mission_id == mission_id,
            MissionReviewItemRecord.status != "superseded",
        )
        .subquery()
    )


def _artifact_destination_partition():
    materialization = MissionReviewItemRecord.preview_json["materialization"]
    operation = materialization["operation"].as_string()
    path = func.trim(materialization["payload"]["path"].as_string())
    has_target_ref = and_(
        MissionReviewItemRecord.target_ref.is_not(None),
        MissionReviewItemRecord.target_ref != "",
    )
    is_new_document = and_(
        operation == "documents.upsert_prism_file",
        path.is_not(None),
        path != "",
    )
    room = func.coalesce(MissionReviewItemRecord.target_room, "")
    return (
        case(
            (has_target_ref, "existing"),
            (is_new_document, "new"),
            else_="output",
        ),
        case(
            (
                has_target_ref,
                MissionReviewItemRecord.target_kind,
            ),
            else_=case(
                (is_new_document, MissionReviewItemRecord.target_kind),
                else_="",
            ),
        ),
        case(
            (has_target_ref, room),
            else_=case(
                (is_new_document, room),
                else_="",
            ),
        ),
        case(
            (
                has_target_ref,
                MissionReviewItemRecord.target_ref,
            ),
            (is_new_document, path),
            else_=MissionReviewItemRecord.output_key,
        ),
    )


def _current_artifact_rows(mission_id: str):
    current = _current_review_rows(mission_id)
    return (
        select(
            MissionReviewItemRecord.review_item_id.label("review_item_id"),
            MissionReviewItemRecord.source_item_seq.label("source_item_seq"),
            func.row_number()
            .over(
                partition_by=_artifact_destination_partition(),
                order_by=(
                    MissionReviewItemRecord.created_at.desc(),
                    MissionReviewItemRecord.review_item_id.desc(),
                ),
            )
            .label("artifact_rank"),
        )
        .join(
            current,
            current.c.review_item_id == MissionReviewItemRecord.review_item_id,
        )
        .where(
            current.c.review_rank == 1,
            MissionReviewItemRecord.target_kind.in_(("document", "workspace_asset")),
            MissionReviewItemRecord.status.in_(("pending", "accepted", "committed")),
            MissionReviewItemRecord.source_item_seq.is_not(None),
        )
        .subquery()
    )


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

    async def get_run_state_version(self, mission_id: str) -> int | None:
        result = await self.session.execute(
            select(MissionRunRecord.state_version).where(
                MissionRunRecord.mission_id == mission_id
            )
        )
        value = result.scalar_one_or_none()
        return int(value) if value is not None else None

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
        active_workspace_run = aliased(MissionRunRecord)
        workspace_driver_active = exists(
            select(1).where(
                active_workspace_run.workspace_id == MissionRunRecord.workspace_id,
                active_workspace_run.mission_id != MissionRunRecord.mission_id,
                active_workspace_run.status.in_(NONTERMINAL_MISSION_STATUSES),
                active_workspace_run.lease_owner.is_not(None),
                active_workspace_run.lease_expires_at.is_not(None),
                active_workspace_run.lease_expires_at > now,
            )
        )
        dispatched_workspace_run = aliased(MissionRunRecord)
        workspace_dispatch_active = exists(
            select(1).where(
                dispatched_workspace_run.workspace_id
                == MissionRunRecord.workspace_id,
                dispatched_workspace_run.mission_id
                != MissionRunRecord.mission_id,
                dispatched_workspace_run.status.in_(NONTERMINAL_MISSION_STATUSES),
                dispatched_workspace_run.dispatch_owner.is_not(None),
                dispatched_workspace_run.dispatch_expires_at.is_not(None),
                dispatched_workspace_run.dispatch_expires_at > now,
            )
        )
        earlier_workspace_run = aliased(MissionRunRecord)
        earlier_due = or_(
            and_(
                earlier_workspace_run.next_wakeup_at.is_not(None),
                earlier_workspace_run.next_wakeup_at <= now,
            ),
            and_(
                earlier_workspace_run.lease_expires_at.is_not(None),
                earlier_workspace_run.lease_expires_at <= now,
            ),
        )
        earlier_due_at = _mission_due_at(earlier_workspace_run)
        current_due_at = _mission_due_at()
        workspace_has_earlier_runnable = exists(
            select(1).where(
                earlier_workspace_run.workspace_id
                == MissionRunRecord.workspace_id,
                earlier_workspace_run.mission_id
                != MissionRunRecord.mission_id,
                earlier_workspace_run.status.in_(NONTERMINAL_MISSION_STATUSES),
                earlier_due,
                or_(
                    earlier_workspace_run.lease_owner.is_(None),
                    earlier_workspace_run.lease_expires_at.is_(None),
                    earlier_workspace_run.lease_expires_at <= now,
                ),
                or_(
                    earlier_workspace_run.dispatch_owner.is_(None),
                    earlier_workspace_run.dispatch_expires_at.is_(None),
                    earlier_workspace_run.dispatch_expires_at <= now,
                ),
                or_(
                    earlier_due_at < current_due_at,
                    and_(
                        earlier_due_at == current_due_at,
                        earlier_workspace_run.mission_id
                        < MissionRunRecord.mission_id,
                    ),
                ),
            )
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
                ~workspace_driver_active,
                ~workspace_dispatch_active,
                ~workspace_has_earlier_runnable,
            )
            .order_by(
                _mission_due_at().asc().nulls_last(),
                MissionRunRecord.mission_id.asc(),
            )
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        result = await self.session.execute(statement)
        return list(result.scalars())

    async def lock_workspace_execution_slot(self, workspace_id: str) -> None:
        """Serialize Mission lease claims for one workspace transactionally."""

        if self.session.get_bind().dialect.name != "postgresql":
            return
        await self.session.execute(
            text("SELECT pg_advisory_xact_lock(:lock_key)"),
            {"lock_key": _workspace_execution_lock_key(workspace_id)},
        )

    async def try_lock_workspace_execution_slot(self, workspace_id: str) -> bool:
        """Try to serialize a batch dispatch without risking lock-order waits."""

        if self.session.get_bind().dialect.name != "postgresql":
            return True
        acquired = await self.session.scalar(
            text("SELECT pg_try_advisory_xact_lock(:lock_key)"),
            {"lock_key": _workspace_execution_lock_key(workspace_id)},
        )
        return bool(acquired)

    async def find_active_workspace_lease(
        self,
        *,
        workspace_id: str,
        excluding_mission_id: str,
        now: datetime,
    ) -> MissionRunRecord | None:
        result = await self.session.execute(
            select(MissionRunRecord)
            .where(
                MissionRunRecord.workspace_id == workspace_id,
                MissionRunRecord.mission_id != excluding_mission_id,
                MissionRunRecord.status.in_(NONTERMINAL_MISSION_STATUSES),
                MissionRunRecord.lease_owner.is_not(None),
                MissionRunRecord.lease_expires_at.is_not(None),
                MissionRunRecord.lease_expires_at > now,
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def find_active_workspace_dispatch(
        self,
        *,
        workspace_id: str,
        excluding_mission_id: str,
        now: datetime,
    ) -> MissionRunRecord | None:
        result = await self.session.execute(
            select(MissionRunRecord)
            .where(
                MissionRunRecord.workspace_id == workspace_id,
                MissionRunRecord.mission_id != excluding_mission_id,
                MissionRunRecord.status.in_(NONTERMINAL_MISSION_STATUSES),
                MissionRunRecord.dispatch_owner.is_not(None),
                MissionRunRecord.dispatch_expires_at.is_not(None),
                MissionRunRecord.dispatch_expires_at > now,
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def find_oldest_dispatchable_workspace_run(
        self,
        *,
        workspace_id: str,
        now: datetime,
    ) -> MissionRunRecord | None:
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
        result = await self.session.execute(
            select(MissionRunRecord)
            .where(
                MissionRunRecord.workspace_id == workspace_id,
                MissionRunRecord.status.in_(NONTERMINAL_MISSION_STATUSES),
                due,
                or_(
                    MissionRunRecord.lease_owner.is_(None),
                    MissionRunRecord.lease_expires_at.is_(None),
                    MissionRunRecord.lease_expires_at <= now,
                ),
                or_(
                    MissionRunRecord.dispatch_owner.is_(None),
                    MissionRunRecord.dispatch_expires_at.is_(None),
                    MissionRunRecord.dispatch_expires_at <= now,
                ),
            )
            .order_by(
                _mission_due_at().asc().nulls_last(),
                MissionRunRecord.mission_id.asc(),
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

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
        after_seq: int = 0,
        limit: int = 100,
    ) -> list[MissionItemRecord]:
        statement = (
            select(MissionItemRecord)
            .where(
                MissionItemRecord.mission_id == mission_id,
                MissionItemRecord.operation_id == operation_id,
                MissionItemRecord.seq > after_seq,
            )
            .order_by(MissionItemRecord.seq.asc())
            .limit(limit)
        )
        if item_type is not None:
            statement = statement.where(MissionItemRecord.item_type == item_type)
        result = await self.session.execute(statement)
        return list(result.scalars())

    async def list_activity_with_subagent_projection(
        self,
        *,
        mission_id: str,
        after_seq: int,
        activity_limit: int,
        operation_id: str | None = None,
    ) -> tuple[list[MissionItemRecord], list[MissionItemRecord]]:
        """Load recent activity and bounded worker projection in one query."""

        selected_operation_id = operation_id
        if selected_operation_id is None:
            selected_operation_id = (
                select(MissionItemRecord.operation_id)
                .where(
                    MissionItemRecord.mission_id == mission_id,
                    MissionItemRecord.item_type == "subagent_spawned",
                    MissionItemRecord.operation_id.is_not(None),
                )
                .order_by(MissionItemRecord.seq.desc())
                .limit(1)
                .scalar_subquery()
            )
        job_id = MissionItemRecord.payload_json["job_id"].as_string()
        base_filters = (
            MissionItemRecord.mission_id == mission_id,
            MissionItemRecord.operation_id == selected_operation_id,
            MissionItemRecord.item_type == "subagent_progress",
            job_id.is_not(None),
        )
        latest_ranked = (
            select(
                MissionItemRecord.id.label("item_id"),
                func.row_number()
                .over(
                    partition_by=job_id,
                    order_by=MissionItemRecord.seq.desc(),
                )
                .label("projection_rank"),
            )
            .where(*base_filters)
            .subquery()
        )
        public_ranked = (
            select(
                MissionItemRecord.id.label("item_id"),
                func.row_number()
                .over(
                    partition_by=job_id,
                    order_by=MissionItemRecord.seq.desc(),
                )
                .label("projection_rank"),
            )
            .where(
                *base_filters,
                MissionItemRecord.payload_json["public_summary"]
                .as_string()
                .is_not(None),
            )
            .subquery()
        )
        projection_ids = (
            select(latest_ranked.c.item_id)
            .where(latest_ranked.c.projection_rank == 1)
            .union(
                select(public_ranked.c.item_id).where(
                    public_ranked.c.projection_rank <= 7
                )
            )
            .subquery()
        )
        activity_ids = (
            select(MissionItemRecord.id.label("item_id"))
            .where(
                MissionItemRecord.mission_id == mission_id,
                MissionItemRecord.seq > after_seq,
            )
            .order_by(MissionItemRecord.seq.asc())
            .limit(activity_limit)
            .subquery()
        )
        combined_ids = (
            select(activity_ids.c.item_id)
            .union(select(projection_ids.c.item_id))
            .subquery()
        )
        is_subagent_projection = MissionItemRecord.id.in_(
            select(projection_ids.c.item_id)
        ).label("is_subagent_projection")
        result = await self.session.execute(
            select(MissionItemRecord, is_subagent_projection)
            .where(
                MissionItemRecord.id.in_(select(combined_ids.c.item_id)),
            )
            .order_by(MissionItemRecord.seq.asc())
        )
        rows = list(result.all())
        activity = [record for record, _is_projection in rows if record.seq > after_seq]
        projection = [record for record, is_projection in rows if is_projection]
        return activity, projection

    async def list_operation_receipt_items(
        self,
        *,
        mission_id: str,
        operation_id: str,
    ) -> list[MissionItemRecord]:
        """Load the latest claim/terminal pair without a history-page cutoff."""

        result = await self.session.execute(
            select(MissionItemRecord)
            .where(
                MissionItemRecord.mission_id == mission_id,
                MissionItemRecord.operation_id == operation_id,
                MissionItemRecord.item_type.in_(
                    ("operation_claim", "operation_terminal")
                ),
            )
            .order_by(MissionItemRecord.seq.desc())
            .limit(2)
        )
        records = list(result.scalars())
        records.reverse()
        return records

    async def list_model_ledger_items(
        self,
        *,
        mission_id: str,
        operation_ids: tuple[str, ...] | None = None,
    ) -> list[MissionItemRecord]:
        if operation_ids == ():
            return []
        statement = select(MissionItemRecord).where(
                MissionItemRecord.mission_id == mission_id,
                MissionItemRecord.item_type.in_(
                    (
                        "model_call_started",
                        "usage_receipt",
                        "model_call_terminal",
                    )
                ),
            )
        if operation_ids is not None:
            statement = statement.where(
                MissionItemRecord.operation_id.in_(operation_ids)
            )
        result = await self.session.execute(
            statement.order_by(MissionItemRecord.seq.asc())
        )
        return list(result.scalars())

    async def list_subagent_progress_items(
        self,
        *,
        mission_id: str,
        operation_ids: tuple[str, ...],
    ) -> list[MissionItemRecord]:
        if not operation_ids:
            return []
        result = await self.session.execute(
            select(MissionItemRecord)
            .where(
                MissionItemRecord.mission_id == mission_id,
                MissionItemRecord.item_type == "subagent_progress",
                MissionItemRecord.operation_id.in_(operation_ids),
            )
            .order_by(MissionItemRecord.seq.asc())
        )
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

    async def list_unique_evidence_items(
        self,
        *,
        mission_id: str,
        after_seq: int = 0,
        limit: int = 50,
    ) -> list[MissionItemRecord]:
        """Project one stable ledger item per Mission evidence reference."""

        reference_id = MissionItemRecord.payload_json["reference_id"].as_string()
        reference_identity = case(
            (
                and_(reference_id.is_not(None), reference_id != ""),
                reference_id,
            ),
            else_=MissionItemRecord.id,
        )
        ranked = (
            select(
                MissionItemRecord.id.label("item_id"),
                MissionItemRecord.seq.label("item_seq"),
                func.row_number()
                .over(
                    partition_by=reference_identity,
                    order_by=MissionItemRecord.seq.asc(),
                )
                .label("reference_rank"),
            )
            .where(
                MissionItemRecord.mission_id == mission_id,
                MissionItemRecord.item_type == "evidence",
            )
            .subquery()
        )
        result = await self.session.execute(
            select(MissionItemRecord)
            .join(ranked, ranked.c.item_id == MissionItemRecord.id)
            .where(
                ranked.c.reference_rank == 1,
                ranked.c.item_seq > after_seq,
            )
            .order_by(ranked.c.item_seq.asc())
            .limit(limit)
        )
        return list(result.scalars())

    async def list_existing_semantic_references(
        self,
        *,
        mission_id: str,
        reference_keys: tuple[tuple[str, str], ...],
    ) -> dict[tuple[str, str], MissionItemRecord]:
        if not reference_keys:
            return {}
        categories = {category for category, _reference_id in reference_keys}
        reference_ids = {
            reference_id for _category, reference_id in reference_keys
        }
        reference_id_value = (
            MissionItemRecord.payload_json["reference_id"].as_string()
        )
        result = await self.session.execute(
            select(MissionItemRecord)
            .where(
                MissionItemRecord.mission_id == mission_id,
                MissionItemRecord.item_type.in_(categories),
                reference_id_value.in_(reference_ids),
            )
            .order_by(MissionItemRecord.seq.asc())
        )
        requested = set(reference_keys)
        existing: dict[tuple[str, str], MissionItemRecord] = {}
        for record in result.scalars():
            key = (
                str(record.item_type),
                str(record.payload_json.get("reference_id") or ""),
            )
            if key in requested:
                existing.setdefault(key, record)
        return existing

    async def count_items(
        self,
        *,
        mission_id: str,
        item_type: str | None = None,
        operation_id: str | None = None,
    ) -> int:
        statement = select(func.count(MissionItemRecord.id)).where(
            MissionItemRecord.mission_id == mission_id
        )
        if item_type is not None:
            statement = statement.where(MissionItemRecord.item_type == item_type)
        if operation_id is not None:
            statement = statement.where(
                MissionItemRecord.operation_id == operation_id
            )
        result = await self.session.execute(statement)
        return int(result.scalar_one())

    async def list_review_items(
        self,
        *,
        mission_id: str,
        status: list[str] | None = None,
        output_keys: list[str] | None = None,
        after_created_at: datetime | None = None,
        after_review_item_id: str | None = None,
        limit: int = 100,
        for_update: bool = False,
    ) -> list[MissionReviewItemRecord]:
        statement = (
            select(MissionReviewItemRecord)
            .where(MissionReviewItemRecord.mission_id == mission_id)
            .order_by(
                MissionReviewItemRecord.created_at.asc(),
                MissionReviewItemRecord.review_item_id.asc(),
            )
            .limit(limit)
        )
        if status:
            statement = statement.where(MissionReviewItemRecord.status.in_(status))
        if output_keys:
            statement = statement.where(MissionReviewItemRecord.output_key.in_(output_keys))
        if after_created_at is not None and after_review_item_id is not None:
            statement = statement.where(
                or_(
                    MissionReviewItemRecord.created_at > after_created_at,
                    and_(
                        MissionReviewItemRecord.created_at == after_created_at,
                        MissionReviewItemRecord.review_item_id > after_review_item_id,
                    ),
                )
            )
        if for_update:
            statement = statement.with_for_update()
        result = await self.session.execute(statement)
        return list(result.scalars())

    async def count_review_items(
        self,
        *,
        mission_id: str,
        status: list[str] | None = None,
    ) -> int:
        statement = select(func.count(MissionReviewItemRecord.review_item_id)).where(
            MissionReviewItemRecord.mission_id == mission_id
        )
        if status:
            statement = statement.where(MissionReviewItemRecord.status.in_(status))
        result = await self.session.execute(statement)
        return int(result.scalar_one())

    async def list_current_review_items(
        self,
        *,
        mission_id: str,
        after_created_at: datetime | None = None,
        after_review_item_id: str | None = None,
        limit: int,
    ) -> list[MissionReviewItemRecord]:
        current = _current_review_rows(mission_id)
        statement = (
            select(MissionReviewItemRecord)
            .join(
                current,
                current.c.review_item_id == MissionReviewItemRecord.review_item_id,
            )
            .where(current.c.review_rank == 1)
            .order_by(
                MissionReviewItemRecord.created_at.asc(),
                MissionReviewItemRecord.review_item_id.asc(),
            )
            .limit(limit)
        )
        if after_created_at is not None and after_review_item_id is not None:
            statement = statement.where(
                or_(
                    MissionReviewItemRecord.created_at > after_created_at,
                    and_(
                        MissionReviewItemRecord.created_at == after_created_at,
                        MissionReviewItemRecord.review_item_id
                        > after_review_item_id,
                    ),
                )
            )
        result = await self.session.execute(statement)
        return list(result.scalars())

    async def count_current_review_items(self, *, mission_id: str) -> int:
        current = _current_review_rows(mission_id)
        result = await self.session.execute(
            select(func.count(current.c.review_item_id)).where(
                current.c.review_rank == 1
            )
        )
        return int(result.scalar_one())

    async def aggregate_current_review_statuses(
        self,
        *,
        mission_id: str,
    ) -> list[tuple[str, int]]:
        current = _current_review_rows(mission_id)
        result = await self.session.execute(
            select(current.c.status, func.count(current.c.review_item_id))
            .where(current.c.review_rank == 1)
            .group_by(current.c.status)
        )
        return [(str(status), int(count)) for status, count in result.all()]

    async def list_current_artifact_review_items(
        self,
        *,
        mission_id: str,
        after_seq: int = 0,
        after_review_item_id: str = "",
        limit: int,
    ) -> list[MissionReviewItemRecord]:
        artifacts = _current_artifact_rows(mission_id)
        result = await self.session.execute(
            select(MissionReviewItemRecord)
            .join(
                artifacts,
                artifacts.c.review_item_id == MissionReviewItemRecord.review_item_id,
            )
            .where(
                artifacts.c.artifact_rank == 1,
                or_(
                    artifacts.c.source_item_seq > after_seq,
                    and_(
                        artifacts.c.source_item_seq == after_seq,
                        artifacts.c.review_item_id > after_review_item_id,
                    ),
                ),
            )
            .order_by(
                artifacts.c.source_item_seq.asc(),
                artifacts.c.review_item_id.asc(),
            )
            .limit(limit)
        )
        return list(result.scalars())

    async def list_artifact_projection_revision_rows(
        self,
        *,
        mission_id: str,
    ) -> list[ArtifactProjectionRevisionRow]:
        """Return the compact, ordered inputs that define the public artifact view."""

        artifacts = _current_artifact_rows(mission_id)
        artifact_kind = MissionReviewItemRecord.preview_json["artifact_kind"].as_string()
        materialization_operation = MissionReviewItemRecord.preview_json[
            "materialization"
        ]["operation"].as_string()
        result = await self.session.execute(
            select(
                MissionReviewItemRecord.review_item_id,
                MissionReviewItemRecord.source_item_seq,
                MissionReviewItemRecord.title,
                MissionReviewItemRecord.target_kind,
                MissionReviewItemRecord.summary,
                MissionReviewItemRecord.status.label("review_status"),
                MissionReviewItemRecord.preview_ref,
                MissionReviewItemRecord.preview_expires_at,
                artifact_kind.label("artifact_kind"),
                materialization_operation.label("materialization_operation"),
                MissionCommitRecord.status.label("commit_status"),
            )
            .join(
                artifacts,
                artifacts.c.review_item_id
                == MissionReviewItemRecord.review_item_id,
            )
            .outerjoin(
                MissionCommitRecord,
                and_(
                    MissionCommitRecord.mission_id
                    == MissionReviewItemRecord.mission_id,
                    MissionCommitRecord.review_item_id
                    == MissionReviewItemRecord.review_item_id,
                ),
            )
            .where(artifacts.c.artifact_rank == 1)
            .order_by(
                artifacts.c.source_item_seq.asc(),
                artifacts.c.review_item_id.asc(),
            )
        )
        return [
            ArtifactProjectionRevisionRow(
                review_item_id=str(row.review_item_id),
                source_item_seq=int(row.source_item_seq),
                title=str(row.title),
                target_kind=str(row.target_kind),
                summary=str(row.summary) if row.summary is not None else None,
                review_status=str(row.review_status),
                preview_ref=(
                    str(row.preview_ref) if row.preview_ref is not None else None
                ),
                preview_expires_at=row.preview_expires_at,
                artifact_kind=(
                    str(row.artifact_kind) if row.artifact_kind is not None else None
                ),
                materialization_operation=(
                    str(row.materialization_operation)
                    if row.materialization_operation is not None
                    else None
                ),
                commit_status=(
                    str(row.commit_status) if row.commit_status is not None else None
                ),
            )
            for row in result.all()
        ]

    async def list_review_items_for_replacement(
        self,
        *,
        mission_id: str,
        output_keys: list[str],
        destinations: list[tuple[str, ...]],
        for_update: bool = False,
    ) -> list[MissionReviewItemRecord]:
        destination_filters = []
        materialization = MissionReviewItemRecord.preview_json["materialization"]
        operation = materialization["operation"].as_string()
        path = func.trim(materialization["payload"]["path"].as_string())
        for destination in destinations:
            if destination[0] == "existing":
                _, target_kind, target_room, target_ref = destination
                destination_filters.append(
                    and_(
                        MissionReviewItemRecord.target_kind == target_kind,
                        func.coalesce(MissionReviewItemRecord.target_room, "")
                        == target_room,
                        MissionReviewItemRecord.target_ref == target_ref,
                    )
                )
            elif destination[0] == "new":
                _, target_kind, target_room, target_operation, target_path = destination
                destination_filters.append(
                    and_(
                        MissionReviewItemRecord.target_kind == target_kind,
                        func.coalesce(MissionReviewItemRecord.target_room, "")
                        == target_room,
                        MissionReviewItemRecord.target_ref.is_(None),
                        operation == target_operation,
                        path == target_path,
                    )
                )
        matches = [MissionReviewItemRecord.output_key.in_(output_keys)]
        matches.extend(destination_filters)
        statement = select(MissionReviewItemRecord).where(
            MissionReviewItemRecord.mission_id == mission_id,
            MissionReviewItemRecord.status.not_in(("committed", "superseded")),
            or_(*matches),
        ).order_by(
            MissionReviewItemRecord.created_at.asc(),
            MissionReviewItemRecord.review_item_id.asc(),
        )
        if for_update:
            statement = statement.with_for_update()
        result = await self.session.execute(statement)
        return list(result.scalars())

    async def list_expired_review_previews(
        self,
        *,
        mission_id: str,
        now: datetime,
        limit: int,
        for_update: bool = False,
    ) -> list[MissionReviewItemRecord]:
        statement = (
            select(MissionReviewItemRecord)
            .where(
                MissionReviewItemRecord.mission_id == mission_id,
                MissionReviewItemRecord.preview_expires_at.is_not(None),
                MissionReviewItemRecord.preview_expires_at <= now,
                (
                    MissionReviewItemRecord.preview_ref.is_not(None)
                    | (MissionReviewItemRecord.preview_json != {})
                ),
            )
            .order_by(
                MissionReviewItemRecord.preview_expires_at.asc(),
                MissionReviewItemRecord.review_item_id.asc(),
            )
            .limit(limit)
        )
        if for_update:
            statement = statement.with_for_update(skip_locked=True)
        result = await self.session.execute(statement)
        return list(result.scalars())

    async def list_mission_ids_with_expired_previews(
        self,
        *,
        now: datetime,
        limit: int,
    ) -> list[str]:
        statement = (
            select(MissionReviewItemRecord.mission_id)
            .where(
                MissionReviewItemRecord.preview_expires_at.is_not(None),
                MissionReviewItemRecord.preview_expires_at <= now,
                (
                    MissionReviewItemRecord.preview_ref.is_not(None)
                    | (MissionReviewItemRecord.preview_json != {})
                ),
            )
            .distinct()
            .order_by(MissionReviewItemRecord.mission_id.asc())
            .limit(limit)
        )
        result = await self.session.execute(statement)
        return [str(value) for value in result.scalars().all()]

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
        *,
        mission_id: str,
        review_item_id: str,
    ) -> MissionCommitRecord | None:
        result = await self.session.execute(
            select(MissionCommitRecord).where(
                MissionCommitRecord.mission_id == mission_id,
                MissionCommitRecord.review_item_id == review_item_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_commits_by_review_item_ids(
        self,
        *,
        mission_id: str,
        review_item_ids: list[str],
    ) -> list[MissionCommitRecord]:
        if not review_item_ids:
            return []
        result = await self.session.execute(
            select(MissionCommitRecord).where(
                MissionCommitRecord.mission_id == mission_id,
                MissionCommitRecord.review_item_id.in_(review_item_ids),
            )
        )
        return list(result.scalars())

    async def list_commits(
        self,
        *,
        mission_id: str,
        after_created_at: datetime | None = None,
        after_commit_id: str | None = None,
        limit: int = 100,
    ) -> list[MissionCommitRecord]:
        statement = (
            select(MissionCommitRecord)
            .where(MissionCommitRecord.mission_id == mission_id)
            .order_by(
                MissionCommitRecord.created_at.asc(),
                MissionCommitRecord.commit_id.asc(),
            )
            .limit(limit)
        )
        if after_created_at is not None and after_commit_id is not None:
            statement = statement.where(
                or_(
                    MissionCommitRecord.created_at > after_created_at,
                    and_(
                        MissionCommitRecord.created_at == after_created_at,
                        MissionCommitRecord.commit_id > after_commit_id,
                    ),
                )
            )
        result = await self.session.execute(statement)
        return list(result.scalars())

    async def aggregate_commit_statuses(
        self,
        *,
        mission_id: str,
    ) -> list[tuple[str, int]]:
        result = await self.session.execute(
            select(MissionCommitRecord.status, func.count(MissionCommitRecord.commit_id))
            .where(MissionCommitRecord.mission_id == mission_id)
            .group_by(MissionCommitRecord.status)
        )
        return [(str(status), int(count)) for status, count in result.all()]

    async def count_commits(self, *, mission_id: str) -> int:
        result = await self.session.execute(
            select(func.count(MissionCommitRecord.commit_id)).where(
                MissionCommitRecord.mission_id == mission_id
            )
        )
        return int(result.scalar_one())


__all__ = [
    "ArtifactProjectionRevisionRow",
    "MissionRepository",
    "NONTERMINAL_MISSION_STATUSES",
]
