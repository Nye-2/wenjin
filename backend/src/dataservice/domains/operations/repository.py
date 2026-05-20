"""Repository for DataService operational metadata."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.dataservice.common.idempotency import IdempotencyScope, make_request_hash, make_scope_hash
from src.dataservice.domains.operations.models import (
    DataServiceIdempotencyKey,
    DataServiceMigrationReport,
    DataServiceOutboxEvent,
)


class OperationsRepository:
    """Persistence helpers for DataService operational tables."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_idempotency_record(
        self,
        *,
        source_service: str,
        command_name: str,
        workspace_id: str | None,
        actor_user_id: str | None,
        idempotency_key: str,
    ) -> DataServiceIdempotencyKey | None:
        scope = IdempotencyScope(
            source_service=source_service,
            command_name=command_name,
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
        )
        statement = select(DataServiceIdempotencyKey).where(
            DataServiceIdempotencyKey.scope_hash == make_scope_hash(scope),
            DataServiceIdempotencyKey.idempotency_key == idempotency_key,
        )
        return await self._scalar_one_or_none(statement)

    def create_idempotency_record(
        self,
        *,
        source_service: str,
        command_name: str,
        workspace_id: str | None,
        actor_user_id: str | None,
        idempotency_key: str,
        request_payload: Any,
        expires_at: datetime | None = None,
    ) -> DataServiceIdempotencyKey:
        scope = IdempotencyScope(
            source_service=source_service,
            command_name=command_name,
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
        )
        record = DataServiceIdempotencyKey(
            source_service=source_service,
            command_name=command_name,
            workspace_id=workspace_id,
            actor_user_id=actor_user_id,
            idempotency_key=idempotency_key,
            scope_hash=make_scope_hash(scope),
            request_hash=make_request_hash(request_payload),
            expires_at=expires_at,
        )
        self.session.add(record)
        return record

    def complete_idempotency_record(
        self,
        record: DataServiceIdempotencyKey,
        *,
        response_json: dict[str, Any] | None = None,
        error_json: dict[str, Any] | None = None,
        status: str = "completed",
    ) -> DataServiceIdempotencyKey:
        record.response_json = response_json
        record.error_json = error_json
        record.status = status
        return record

    def append_outbox_event(
        self,
        *,
        aggregate_kind: str,
        aggregate_id: str,
        event_type: str,
        payload_json: dict[str, Any],
        workspace_id: str | None = None,
    ) -> DataServiceOutboxEvent:
        event = DataServiceOutboxEvent(
            workspace_id=workspace_id,
            aggregate_kind=aggregate_kind,
            aggregate_id=aggregate_id,
            event_type=event_type,
            payload_json=payload_json,
        )
        self.session.add(event)
        return event

    def create_migration_report(
        self,
        *,
        migration_key: str,
        source_module: str,
        target_domain: str,
        status: str,
        summary: str | None = None,
        report_json: dict[str, Any] | None = None,
        completed_at: datetime | None = None,
    ) -> DataServiceMigrationReport:
        report = DataServiceMigrationReport(
            migration_key=migration_key,
            source_module=source_module,
            target_domain=target_domain,
            status=status,
            summary=summary,
            report_json=report_json or {},
            completed_at=completed_at,
        )
        self.session.add(report)
        return report

    async def _scalar_one_or_none(self, statement: Select[tuple[DataServiceIdempotencyKey]]) -> DataServiceIdempotencyKey | None:
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()
