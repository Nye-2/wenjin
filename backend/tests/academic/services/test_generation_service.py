"""GenerationService DataService facade tests."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from src.academic.services.generation_service import GenerationService
from src.dataservice_client.contracts.execution import GenerationRecordPayload


class FakeDataServiceClient:
    def __init__(self) -> None:
        self.created_command = None
        self.records = [
            GenerationRecordPayload(
                id="generation-1",
                workspace_id="ws-1",
                thread_id="thread-1",
                skill_name="idea_to_manuscript",
                model_name="gpt-x",
                duration_ms=100,
                token_usage={"total": 10},
                status="success",
                metadata={"source": "test"},
                created_at=datetime(2026, 5, 21, tzinfo=UTC),
            )
        ]

    async def create_generation_record(self, command) -> GenerationRecordPayload:
        self.created_command = command
        return self.records[0]

    async def get_generation_record(
        self,
        record_id: str,
    ) -> GenerationRecordPayload | None:
        return self.records[0] if record_id == self.records[0].id else None

    async def list_generation_records(self, **kwargs: Any) -> list[GenerationRecordPayload]:
        _ = kwargs
        return self.records

    async def list_generation_records_by_thread(
        self,
        thread_id: str,
    ) -> list[GenerationRecordPayload]:
        return [record for record in self.records if record.thread_id == thread_id]

    async def get_generation_usage_stats(self, **kwargs: Any) -> dict[str, Any]:
        _ = kwargs
        return {"total_executions": len(self.records), "total_tokens": 10}

    async def cleanup_old_generation_records(self, **kwargs: Any) -> int:
        _ = kwargs
        return 1


@pytest.mark.asyncio
async def test_generation_service_delegates_to_dataservice_client() -> None:
    fake = FakeDataServiceClient()
    service = GenerationService(object(), dataservice=fake)  # type: ignore[arg-type]
    created = await service.create(
        workspace_id="ws-1",
        skill_name="idea_to_manuscript",
        thread_id="thread-1",
        metadata={"source": "test"},
    )
    fetched = await service.get("generation-1")
    listed = await service.list_by_thread("thread-1")
    stats = await service.get_usage_stats("ws-1")
    deleted = await service.cleanup_old_records(days_old=30, workspace_id="ws-1")

    assert created.id == "generation-1"
    assert fetched == created
    assert listed == [created]
    assert stats == {"total_executions": 1, "total_tokens": 10}
    assert deleted == 1
    assert fake.created_command.workspace_id == "ws-1"
    assert fake.created_command.skill_name == "idea_to_manuscript"
    assert fake.created_command.thread_id == "thread-1"
    assert fake.created_command.metadata == {"source": "test"}
