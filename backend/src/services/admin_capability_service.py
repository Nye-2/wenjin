"""Admin service for capability mutations. Full CRUD in Phase 3."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from src.services.event_bus import EventBus


class AdminCapabilityService:
    """Service for admin-level capability mutations.

    Currently supports publishing cache-invalidation events.
    Full CRUD operations will be added in Phase 3.
    """

    def __init__(self, db: AsyncSession, event_bus: EventBus) -> None:
        self.db = db
        self.event_bus = event_bus

    async def publish_invalidation(self, capability_id: str, workspace_type: str) -> None:
        """Publish a capability.invalidated event to clear caches."""
        await self.event_bus.publish(
            "capability.invalidated",
            {"id": capability_id, "workspace_type": workspace_type},
        )
