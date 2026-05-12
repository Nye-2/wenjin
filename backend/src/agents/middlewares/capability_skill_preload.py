"""Capability/skill catalog preload middleware.

Loads the workspace's enabled capabilities and the global enabled skills from
the database and injects flat dict snapshots into ThreadState so the chat
prompt can render them synchronously.

Runs after WorkspaceContextMiddleware (needs workspace_type in state).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from langchain_core.runnables import RunnableConfig
from sqlalchemy import select

from src.agents.middlewares.base import Middleware
from src.agents.thread_state import ThreadState

logger = logging.getLogger(__name__)


class CapabilitySkillPreloadMiddleware(Middleware):
    """Inject available capabilities + skills into state before each model call.

    Output shape (both lists of dicts):

        state["available_capabilities"] = [
            {"id": str, "display_name": str, "description": str,
             "intent_description": str, "trigger_phrases": list[str]},
            ...
        ]
        state["available_skills"] = [
            {"id": str, "display_name": str, "description": str,
             "subagent_type": str},
            ...
        ]

    On DB failure the state stays untouched (empty lists), so callers MUST
    treat absence as "no catalog available" rather than "no capabilities exist".
    """

    def __init__(self, timeout: float = 5.0) -> None:
        self._timeout = timeout

    async def before_model(
        self,
        state: ThreadState,
        config: RunnableConfig,
    ) -> dict[str, Any]:
        workspace_type = state.get("workspace_type")
        if not workspace_type:
            return {}

        try:
            caps, skills = await asyncio.wait_for(
                self._fetch(workspace_type),
                timeout=self._timeout,
            )
        except TimeoutError:
            logger.warning(
                "CapabilitySkillPreloadMiddleware: timed out loading catalog "
                "for workspace_type=%s (%.1fs)",
                workspace_type,
                self._timeout,
            )
            return {}
        except Exception:
            logger.exception(
                "CapabilitySkillPreloadMiddleware: failed loading catalog "
                "for workspace_type=%s",
                workspace_type,
            )
            return {}

        return {
            "available_capabilities": caps,
            "available_skills": skills,
        }

    @staticmethod
    async def _fetch(
        workspace_type: str,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        from src.database.models.capability import Capability
        from src.database.models.capability_skill import CapabilitySkill
        from src.database.session import get_db_session

        async with get_db_session() as db:
            cap_rows = (
                await db.execute(
                    select(Capability).where(
                        Capability.workspace_type == workspace_type,
                        Capability.enabled.is_(True),
                    )
                )
            ).scalars().all()
            skill_rows = (
                await db.execute(
                    select(CapabilitySkill).where(CapabilitySkill.enabled.is_(True))
                )
            ).scalars().all()

        caps = [
            {
                "id": c.id,
                "display_name": c.display_name,
                "description": c.description or "",
                "intent_description": c.intent_description or "",
                "trigger_phrases": list(c.trigger_phrases or []),
            }
            for c in cap_rows
        ]
        skills = [
            {
                "id": s.id,
                "display_name": s.display_name,
                "description": s.description or "",
                "subagent_type": s.subagent_type,
            }
            for s in skill_rows
        ]
        return caps, skills
