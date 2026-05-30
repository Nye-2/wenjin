"""Generation usage service facade backed by DataService."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from src.dataservice_client import AsyncDataServiceClient
from src.dataservice_client.contracts.execution import (
    GenerationRecordCreatePayload,
    GenerationRecordPayload,
)
from src.dataservice_client.provider import dataservice_client


class GenerationService:
    """Facade for academic generation usage records owned by DataService."""

    def __init__(
        self,
        *,
        dataservice: AsyncDataServiceClient | None = None,
    ) -> None:
        self._dataservice = dataservice

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
    ) -> GenerationRecordPayload:
        if self._dataservice is not None:
            return await self._dataservice.create_generation_record(
                GenerationRecordCreatePayload(
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
                    metadata=dict(metadata or {}),
                )
            )
        async with dataservice_client() as client:
            return await client.create_generation_record(
                GenerationRecordCreatePayload(
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
                    metadata=dict(metadata or {}),
                )
            )

    async def get(self, record_id: str) -> GenerationRecordPayload | None:
        if self._dataservice is not None:
            return await self._dataservice.get_generation_record(record_id)
        async with dataservice_client() as client:
            return await client.get_generation_record(record_id)

    async def list_by_workspace(
        self,
        workspace_id: str,
        skill_name: str | None = None,
        status: str | None = None,
        since: datetime | None = None,
        limit: int = 100,
    ) -> list[GenerationRecordPayload]:
        if self._dataservice is not None:
            return await self._dataservice.list_generation_records(
                workspace_id=workspace_id,
                skill_name=skill_name,
                status=status,
                since=since,
                limit=limit,
            )
        async with dataservice_client() as client:
            return await client.list_generation_records(
                workspace_id=workspace_id,
                skill_name=skill_name,
                status=status,
                since=since,
                limit=limit,
            )

    async def list_by_thread(
        self,
        thread_id: str,
    ) -> list[GenerationRecordPayload]:
        if self._dataservice is not None:
            return await self._dataservice.list_generation_records_by_thread(thread_id)
        async with dataservice_client() as client:
            return await client.list_generation_records_by_thread(thread_id)

    async def get_usage_stats(
        self,
        workspace_id: str,
        since: datetime | None = None,
    ) -> dict[str, Any]:
        if self._dataservice is not None:
            return await self._dataservice.get_generation_usage_stats(
                workspace_id=workspace_id,
                since=since,
            )
        async with dataservice_client() as client:
            return await client.get_generation_usage_stats(
                workspace_id=workspace_id,
                since=since,
            )

    async def cleanup_old_records(
        self,
        days_old: int = 90,
        workspace_id: str | None = None,
    ) -> int:
        if self._dataservice is not None:
            return await self._dataservice.cleanup_old_generation_records(
                days_old=days_old,
                workspace_id=workspace_id,
            )
        async with dataservice_client() as client:
            return await client.cleanup_old_generation_records(
                days_old=days_old,
                workspace_id=workspace_id,
            )
