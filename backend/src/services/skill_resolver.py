"""SkillResolver — runtime DB lookup with in-memory cache and EventBus invalidation."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.models.capability_skill import CapabilitySkill

logger = logging.getLogger(__name__)


class SkillResolver:
    """Resolve skills from DB with in-memory cache.

    Subscribes to EventBus channel 'skill.invalidated' for cache clear.
    Event payload: {"skill_id": "<id>"}
    """

    INVALIDATE_CHANNEL = "skill.invalidated"

    def __init__(
        self,
        *,
        session_factory: Callable[[], AsyncSession],
        event_bus: Any | None = None,
    ) -> None:
        self.session_factory = session_factory
        self._cache: dict[str, CapabilitySkill] = {}
        if event_bus is not None:
            event_bus.subscribe(self.INVALIDATE_CHANNEL, self._on_invalidate)

    async def resolve(self, skill_id: str) -> CapabilitySkill | None:
        if skill_id in self._cache:
            return self._cache[skill_id]
        session = self.session_factory()
        if hasattr(session, "__aenter__"):
            async with session as s:
                skill = await s.scalar(
                    select(CapabilitySkill).where(CapabilitySkill.id == skill_id)
                )
        else:
            skill = await session.scalar(
                select(CapabilitySkill).where(CapabilitySkill.id == skill_id)
            )
        if skill is not None:
            self._cache[skill_id] = skill
        return skill

    async def list_all_enabled(self) -> list[CapabilitySkill]:
        session = self.session_factory()
        if hasattr(session, "__aenter__"):
            async with session as s:
                result = await s.execute(
                    select(CapabilitySkill).where(CapabilitySkill.enabled.is_(True))
                )
                return list(result.scalars().all())
        result = await session.execute(
            select(CapabilitySkill).where(CapabilitySkill.enabled.is_(True))
        )
        return list(result.scalars().all())

    async def _on_invalidate(self, event: dict[str, Any]) -> None:
        skill_id = event.get("skill_id")
        if skill_id:
            self._cache.pop(skill_id, None)
            logger.debug("Skill cache invalidated for %s", skill_id)
