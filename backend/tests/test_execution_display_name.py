"""Test that execution records store and return display_name."""
from types import SimpleNamespace

import pytest

from src.services.execution_service import ExecutionService


class _FakeDataServiceClient:
    def __init__(self) -> None:
        self.command = None

    async def create_execution(self, command):
        self.command = command
        return SimpleNamespace(
            id="exec-1",
            display_name=command.display_name,
            workspace_type=command.workspace_type,
        )


@pytest.mark.asyncio
async def test_create_execution_stores_display_name():
    """create_execution persists display_name onto the record."""
    dataservice = _FakeDataServiceClient()
    service = ExecutionService(dataservice=dataservice)

    record = await service.create_execution(
        execution_type="capability",
        user_id="user-1",
        workspace_id="ws-1",
        feature_id="lit_review",
        display_name="文献检索",
        workspace_type="sci",
        commit=False,
    )
    assert record.display_name == "文献检索"
    assert record.workspace_type == "sci"
    assert dataservice.command.capability_id == "lit_review"
