"""SkillResolver — runtime DB lookup with in-memory cache and EventBus invalidation."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

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
    ) -> None:
        self.session_factory = session_factory
        self._model = model
        self._cache: dict[str, object] = {}
        if event_bus is not None:
            event_bus.subscribe(self.INVALIDATE_CHANNEL, self._on_invalidate)

    async def resolve(self, skill_id: str):
        if skill_id in self._cache:
            return self._cache[skill_id]
        session = self.session_factory()
        if hasattr(session, "__aenter__"):
            async with session as s:
                if self._model is not None:
                    from sqlalchemy import select

                    skill = await s.scalar(
                        select(self._model).where(self._model.id == skill_id)
                    )
                else:
                    from src.dataservice.catalog_api import CatalogDataService

                    skill = await CatalogDataService(s, autocommit=False).get_skill(skill_id)
        elif self._model is not None:
            from sqlalchemy import select

            skill = await session.scalar(
                select(self._model).where(self._model.id == skill_id)
            )
        else:
            from src.dataservice.catalog_api import CatalogDataService

            skill = await CatalogDataService(session, autocommit=False).get_skill(skill_id)
        if skill is not None:
            self._cache[skill_id] = skill
        return skill

    async def list_all_enabled(self) -> list:
        session = self.session_factory()
        if hasattr(session, "__aenter__"):
            async with session as s:
                if self._model is not None:
                    from sqlalchemy import select

                    result = await s.execute(
                        select(self._model).where(self._model.enabled.is_(True))
                    )
                    return list(result.scalars().all())
                from src.dataservice.catalog_api import CatalogDataService

                return await CatalogDataService(s, autocommit=False).list_skills(enabled_only=True)
        if self._model is not None:
            from sqlalchemy import select

            result = await session.execute(
                select(self._model).where(self._model.enabled.is_(True))
            )
            return list(result.scalars().all())
        from src.dataservice.catalog_api import CatalogDataService

        return await CatalogDataService(session, autocommit=False).list_skills(enabled_only=True)

    async def _on_invalidate(self, event: dict[str, Any]) -> None:
        skill_id = event.get("skill_id")
        if skill_id:
            self._cache.pop(skill_id, None)
            logger.debug("Skill cache invalidated for %s", skill_id)
