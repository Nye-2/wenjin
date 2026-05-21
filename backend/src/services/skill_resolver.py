"""SkillResolver — runtime DB lookup with in-memory cache and EventBus invalidation."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from src.dataservice_client import AsyncDataServiceClient
from src.dataservice_client.provider import dataservice_client

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
        model: Any | None = None,
        dataservice: AsyncDataServiceClient | None = None,
    ) -> None:
        self.session_factory = session_factory
        self._model = model
        self._dataservice = dataservice
        self._cache: dict[str, object] = {}
        if event_bus is not None:
            event_bus.subscribe(self.INVALIDATE_CHANNEL, self._on_invalidate)

    async def _get_catalog_skill(self, skill_id: str):
        if self._dataservice is not None:
            return await self._dataservice.get_catalog_skill(skill_id)
        async with dataservice_client() as client:
            return await client.get_catalog_skill(skill_id)

    async def _list_enabled_catalog_skills(self) -> list:
        if self._dataservice is not None:
            return await self._dataservice.list_catalog_skills(enabled_only=True)
        async with dataservice_client() as client:
            return await client.list_catalog_skills(enabled_only=True)

    async def resolve(self, skill_id: str):
        if skill_id in self._cache:
            return self._cache[skill_id]
        if self._model is None:
            skill = await self._get_catalog_skill(skill_id)
            if skill is not None:
                self._cache[skill_id] = skill
            return skill

        session = self.session_factory()
        if hasattr(session, "__aenter__"):
            async with session as s:
                from sqlalchemy import select

                skill = await s.scalar(
                    select(self._model).where(self._model.id == skill_id)
                )
        else:
            from sqlalchemy import select

            skill = await session.scalar(
                select(self._model).where(self._model.id == skill_id)
            )
        if skill is not None:
            self._cache[skill_id] = skill
        return skill

    async def list_all_enabled(self) -> list:
        if self._model is None:
            return await self._list_enabled_catalog_skills()

        session = self.session_factory()
        if hasattr(session, "__aenter__"):
            async with session as s:
                from sqlalchemy import select

                result = await s.execute(
                    select(self._model).where(self._model.enabled.is_(True))
                )
                return list(result.scalars().all())
        else:
            from sqlalchemy import select

            result = await session.execute(
                select(self._model).where(self._model.enabled.is_(True))
            )
            return list(result.scalars().all())

    async def _on_invalidate(self, event: dict[str, Any]) -> None:
        skill_id = event.get("skill_id")
        if skill_id:
            self._cache.pop(skill_id, None)
            logger.debug("Skill cache invalidated for %s", skill_id)
