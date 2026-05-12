"""Test that execution records store and return display_name."""
import pytest
from unittest.mock import AsyncMock

from src.services.execution_service import ExecutionService


@pytest.mark.asyncio
async def test_create_execution_stores_display_name():
    """create_execution persists display_name onto the record."""
    db = AsyncMock()
    db.flush = AsyncMock()
    db.add = AsyncMock()
    service = ExecutionService(db)

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
