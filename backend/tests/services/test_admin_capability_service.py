"""Tests for admin_capability_service invalidate-event publishing."""
from unittest.mock import AsyncMock

import pytest

from src.services.admin_capability_service import AdminCapabilityService


@pytest.mark.asyncio
async def test_publish_invalidate_event_includes_id_and_type():
    bus = AsyncMock()
    service = AdminCapabilityService(db=AsyncMock(), event_bus=bus)
    await service.publish_invalidation("deep_research", "thesis")
    bus.publish.assert_awaited_once_with(
        "capability.invalidated",
        {"id": "deep_research", "workspace_type": "thesis"},
    )
