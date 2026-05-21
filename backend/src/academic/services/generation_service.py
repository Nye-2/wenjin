"""Generation usage service facade backed by DataService."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.dataservice.execution_api import (
    ExecutionDataService,
    GenerationRecordProjection,
)


class GenerationService:
    """Compatibility facade for legacy academic generation usage callers."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self._executions = ExecutionDataService(db)

    async def create(
        self,
        workspace_id: str,
        skill_name: str,
        thread_id: str | None = None,
        model_name: str | None = None,
        input_summary: str | None = None,
        output_summary: str | None = None,
        duration_ms: int | None = None,
        token_usage: dict[str, Any] | None = None,
        status: str = "success",
        error_message: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> GenerationRecordProjection:
        return await self._executions.create_generation_usage(
            workspace_id=workspace_id,
            skill_name=skill_name,
            thread_id=thread_id,
            model_name=model_name,
            input_summary=input_summary,
            output_summary=output_summary,
            duration_ms=duration_ms,
            token_usage=token_usage,
            status=status,
            error_message=error_message,
            metadata=metadata,
        )

    async def get(self, record_id: str) -> GenerationRecordProjection | None:
        return await self._executions.get_generation_record(record_id)

    async def list_by_workspace(
        self,
        workspace_id: str,
        skill_name: str | None = None,
        status: str | None = None,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[GenerationRecordProjection]:
        return await self._executions.list_generation_records(
            workspace_id=workspace_id,
            skill_name=skill_name,
            status=status,
            since=since,
            limit=limit,
        )

    async def list_by_thread(
        self,
        thread_id: str,
    ) -> list[GenerationRecordProjection]:
        return await self._executions.list_generation_records_by_thread(thread_id)

    async def get_usage_stats(
        self,
        workspace_id: str,
        since: datetime | None = None,
    ) -> dict[str, Any]:
        return await self._executions.get_generation_usage_stats(
            workspace_id=workspace_id,
            since=since,
        )

    async def cleanup_old_records(
        self,
        days_old: int = 90,
        workspace_id: str | None = None,
    ) -> int:
        return await self._executions.cleanup_old_generation_records(
            days_old=days_old,
            workspace_id=workspace_id,
        )
